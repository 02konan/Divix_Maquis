"""Toutes les écritures : commandes, encaissements, menu, stock, dépenses.

Comme les lectures, chaque requête est cadrée sur l'établissement courant. Les
écritures le posent en colonne à l'insertion, et le vérifient en condition à la
mise à jour : sans cette condition, un identifiant deviné dans une URL laisserait
modifier l'article ou la table d'un autre maquis.
"""

from werkzeug.security import generate_password_hash

from backend.auth import creer_utilisateur
from backend.database import (
    connexion,
    executer,
    generer_reference,
    lire_un,
    message_erreur,
)
from backend.etablissement import courant

LONGUEUR_MOT_DE_PASSE = 6

MODES_PAIEMENT = ["Espèces", "Orange Money", "MTN MoMo", "Moov Money", "Wave", "Carte"]
TYPES_SERVICE = ["Sur place", "À emporter", "Livraison"]
STATUTS_COMMANDE = ["En cours", "Servie", "Payée", "Annulée"]
STATUTS_TABLE = ["Libre", "Occupée", "Réservée"]
CATEGORIES_DEPENSE = [
    "Approvisionnement",
    "Salaire",
    "Loyer",
    "Électricité & Eau",
    "Transport",
    "Entretien",
    "Divers",
]


# ----------------------------------------------------------------------------
# SALLE
# ----------------------------------------------------------------------------


def creer_table(numero, zone, places):
    try:
        id_table = executer(
            """INSERT INTO tables_salle (id_etablissement, numero, zone, places)
               VALUES (%s, %s, %s, %s)""",
            (courant(), numero, zone, int(places)),
        )
        return {"success": True, "id_table": id_table}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def changer_statut_table(id_table, statut):
    if statut not in STATUTS_TABLE:
        return {"success": False, "error": "Statut de table invalide"}
    try:
        executer(
            """UPDATE tables_salle SET statut = %s
               WHERE id = %s AND id_etablissement = %s""",
            (statut, id_table, courant()),
        )
        return {"success": True}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


# ----------------------------------------------------------------------------
# MENU
# ----------------------------------------------------------------------------


def creer_article(
    nom,
    id_categorie,
    prix,
    cout_revient,
    gere_stock,
    stock,
    seuil_alerte,
    disponible,
    image,
    id_utilisateur,
):
    stock_initial = int(stock or 0) if int(gere_stock) else 0

    try:
        reference = generer_reference("ART", "articles")
        id_article = executer(
            """
            INSERT INTO articles (id_etablissement, reference, nom, id_categorie,
                                  prix, cout_revient, gere_stock, stock,
                                  seuil_alerte, disponible, image, id_utilisateur)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s)
            """,
            (
                courant(),
                reference,
                nom,
                id_categorie,
                float(prix),
                float(cout_revient or 0),
                int(gere_stock),
                int(seuil_alerte or 0),
                int(disponible),
                image,
                id_utilisateur,
            ),
        )
        # L'article naît à zéro et le stock déclaré arrive par un mouvement : le
        # poser aussi à l'insertion le comptait deux fois, un article créé avec
        # 50 bouteilles en affichait 100 et le journal ne collait plus au stock.
        if stock_initial > 0:
            enregistrer_mouvement(
                id_article,
                "Entrée",
                stock_initial,
                "Stock initial",
                id_utilisateur,
            )
        return {"success": True, "id_article": id_article, "reference": reference}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def modifier_article(
    id_article,
    nom,
    id_categorie,
    prix,
    cout_revient,
    gere_stock,
    seuil_alerte,
    disponible,
    image,
):
    """Met à jour un article. La quantité en stock n'est pas touchée ici :
    elle se corrige par un mouvement d'inventaire, qui laisse une trace."""
    try:
        champs = [
            "nom = %s",
            "id_categorie = %s",
            "prix = %s",
            "gere_stock = %s",
            "seuil_alerte = %s",
            "disponible = %s",
        ]
        valeurs = [
            nom,
            id_categorie,
            float(prix),
            int(gere_stock),
            int(seuil_alerte or 0),
            int(disponible),
        ]
        # Une photo ou un coût absents du formulaire signifient « garder
        # l'actuel ». Les traiter comme zéro effacerait la marge d'un article
        # à chaque modification.
        if cout_revient is not None:
            champs.append("cout_revient = %s")
            valeurs.append(float(cout_revient))
        if image:
            champs.append("image = %s")
            valeurs.append(image)

        executer(
            f"""UPDATE articles SET {', '.join(champs)}
                WHERE id = %s AND id_etablissement = %s""",
            (*valeurs, int(id_article), courant()),
        )
        return {"success": True, "id_article": int(id_article)}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def basculer_disponibilite(id_article, disponible):
    try:
        executer(
            """UPDATE articles SET disponible = %s
               WHERE id = %s AND id_etablissement = %s""",
            (1 if disponible else 0, id_article, courant()),
        )
        return {"success": True}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def creer_categorie(nom, type_categorie):
    try:
        id_categorie = executer(
            "INSERT INTO categories (id_etablissement, nom, type) VALUES (%s, %s, %s)",
            (courant(), nom, type_categorie),
        )
        return {"success": True, "id_categorie": id_categorie}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


# ----------------------------------------------------------------------------
# STOCK
# ----------------------------------------------------------------------------


def enregistrer_mouvement(id_article, type_mouvement, quantite, motif, id_utilisateur):
    """Applique un mouvement de stock et journalise l'opération."""
    quantite = int(quantite)
    # Un inventaire saisit le stock réel constaté, qui peut légitimement être nul.
    if quantite < 0 or (quantite == 0 and type_mouvement != "Inventaire"):
        return {"success": False, "error": "La quantité doit être supérieure à zéro"}

    try:
        with connexion() as conn:
            # FOR UPDATE : sans verrou, deux mouvements simultanés lisent le même
            # stock de départ et l'un des deux écrase la mise à jour de l'autre.
            ligne = conn.execute(
                """SELECT stock, gere_stock FROM articles
                   WHERE id = %s AND id_etablissement = %s FOR UPDATE""",
                (id_article, courant()),
            ).fetchone()
            if not ligne:
                return {"success": False, "error": "Article introuvable"}
            if not ligne["gere_stock"]:
                return {"success": False, "error": "Cet article ne suit pas de stock"}

            if type_mouvement == "Entrée":
                stock_apres = ligne["stock"] + quantite
            elif type_mouvement == "Inventaire":
                stock_apres = quantite
            else:  # Sortie ou Perte
                stock_apres = ligne["stock"] - quantite
                if stock_apres < 0:
                    return {"success": False, "error": "Stock insuffisant"}

            conn.execute(
                "UPDATE articles SET stock = %s WHERE id = %s",
                (stock_apres, id_article),
            )
            conn.execute(
                """INSERT INTO mouvements_stock
                   (id_etablissement, id_article, type_mouvement, quantite,
                    stock_apres, motif, id_utilisateur)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    courant(),
                    id_article,
                    type_mouvement,
                    quantite,
                    stock_apres,
                    motif,
                    id_utilisateur,
                ),
            )
            conn.commit()
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}

    return {"success": True, "stock_apres": stock_apres}


# ----------------------------------------------------------------------------
# COMMANDES
# ----------------------------------------------------------------------------


def refuser_hors_domaine(conn, articles, domaines):
    """Un serveur du bar ne commande pas de nourriture, et réciproquement.

    Le contrôle est ici, et pas seulement dans la carte affichée : un
    formulaire forgé enverrait n'importe quel identifiant d'article.
    """
    if not domaines:
        return

    ids = sorted({int(article["id_article"]) for article in articles})
    marqueurs_ids = ", ".join(["%s"] * len(ids))
    marqueurs_domaines = ", ".join(["%s"] * len(domaines))
    intrus = conn.execute(
        f"""SELECT a.nom FROM articles a
            LEFT JOIN categories c ON a.id_categorie = c.id
            WHERE a.id IN ({marqueurs_ids}) AND a.id_etablissement = %s
              AND (c.type IS NULL OR c.type NOT IN ({marqueurs_domaines}))""",
        (*ids, courant(), *domaines),
    ).fetchall()

    if intrus:
        noms = ", ".join(ligne["nom"] for ligne in intrus)
        raise ValueError(f"{noms} ne fait pas partie de votre carte")


def table_du_meme_etablissement(id_table):
    return (
        lire_un(
            "SELECT id FROM tables_salle WHERE id = %s AND id_etablissement = %s",
            (id_table, courant()),
        )
        is not None
    )


def verrouiller_articles(conn, articles):
    """Verrouille les articles d'une commande, toujours dans l'ordre des id.

    Sans ordre stable, deux commandes portant sur les mêmes articles saisis dans
    un ordre différent peuvent se bloquer mutuellement (interblocage InnoDB).
    """
    ids = sorted({int(article["id_article"]) for article in articles})
    marqueurs = ", ".join(["%s"] * len(ids))
    conn.execute(
        f"""SELECT id FROM articles
            WHERE id IN ({marqueurs}) AND id_etablissement = %s
            ORDER BY id FOR UPDATE""",
        (*ids, courant()),
    )


def creer_commande(
    id_utilisateur,
    id_table,
    type_service,
    nom_client,
    telephone_client,
    couverts,
    remise,
    commentaire,
    articles,
    domaines=None,
):
    """Ouvre un ticket, décrémente le stock des boissons et occupe la table."""
    if not articles:
        return {"success": False, "error": "Aucun article dans la commande"}
    if type_service not in TYPES_SERVICE:
        return {"success": False, "error": "Type de service invalide"}

    # La table vient du formulaire : sans cette vérification, un identifiant
    # deviné occuperait une table du maquis d'à côté. Les articles, eux, sont
    # relus sous verrou dans l'établissement, plus bas.
    if id_table and not table_du_meme_etablissement(id_table):
        return {"success": False, "error": "Cette table n'existe pas ici"}

    reference = generer_reference("CMD", "commandes")

    try:
        with connexion() as conn:
            refuser_hors_domaine(conn, articles, domaines)
            verrouiller_articles(conn, articles)
            montant_total = 0
            lignes = []

            for article in articles:
                ligne = conn.execute(
                    """SELECT id, nom, prix, gere_stock, stock, disponible
                       FROM articles
                       WHERE id = %s AND id_etablissement = %s FOR UPDATE""",
                    (article["id_article"], courant()),
                ).fetchone()
                if not ligne:
                    raise ValueError(f"Article {article['id_article']} introuvable")
                if not ligne["disponible"]:
                    raise ValueError(f"{ligne['nom']} n'est plus disponible")

                quantite = int(article["quantite"])
                if quantite <= 0:
                    raise ValueError(f"Quantité invalide pour {ligne['nom']}")
                if ligne["gere_stock"] and ligne["stock"] < quantite:
                    raise ValueError(
                        f"Stock insuffisant pour {ligne['nom']} "
                        f"(restant : {ligne['stock']})"
                    )

                # Le prix vient toujours de la base, jamais du formulaire.
                total_ligne = round(ligne["prix"] * quantite, 2)
                montant_total += total_ligne
                lignes.append(
                    {
                        "id_article": ligne["id"],
                        "quantite": quantite,
                        "prix_unitaire": ligne["prix"],
                        "total": total_ligne,
                        "note": article.get("note"),
                        "gere_stock": ligne["gere_stock"],
                        "stock": ligne["stock"],
                    }
                )

            remise = float(remise or 0)
            if remise < 0 or remise > montant_total:
                raise ValueError("Remise invalide")
            montant_total = round(montant_total - remise, 2)

            id_commande = conn.execute(
                """
                INSERT INTO commandes (id_etablissement, reference, id_table,
                                       type_service, nom_client, telephone_client,
                                       couverts, montant_total, remise,
                                       commentaire, id_utilisateur)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    courant(),
                    reference,
                    id_table or None,
                    type_service,
                    nom_client,
                    telephone_client,
                    int(couverts or 1),
                    montant_total,
                    remise,
                    commentaire,
                    id_utilisateur,
                ),
            ).lastrowid

            for ligne in lignes:
                conn.execute(
                    """INSERT INTO lignes_commande
                       (id_commande, id_article, quantite, prix_unitaire, total, note)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        id_commande,
                        ligne["id_article"],
                        ligne["quantite"],
                        ligne["prix_unitaire"],
                        ligne["total"],
                        ligne["note"],
                    ),
                )

                if ligne["gere_stock"]:
                    stock_apres = ligne["stock"] - ligne["quantite"]
                    conn.execute(
                        "UPDATE articles SET stock = %s WHERE id = %s",
                        (stock_apres, ligne["id_article"]),
                    )
                    conn.execute(
                        """INSERT INTO mouvements_stock
                           (id_etablissement, id_article, type_mouvement, quantite,
                            stock_apres, motif, id_utilisateur)
                           VALUES (%s, %s, 'Sortie', %s, %s, %s, %s)""",
                        (
                            courant(),
                            ligne["id_article"],
                            ligne["quantite"],
                            stock_apres,
                            f"Commande {reference}",
                            id_utilisateur,
                        ),
                    )

            if id_table:
                conn.execute(
                    "UPDATE tables_salle SET statut = 'Occupée' WHERE id = %s",
                    (id_table,),
                )

            conn.commit()

        return {
            "success": True,
            "reference": reference,
            "id_commande": id_commande,
            "montant_total": montant_total,
        }
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def changer_statut_commande(reference, statut, domaines=None):
    if statut not in STATUTS_COMMANDE:
        return {"success": False, "error": "Statut de commande invalide"}

    try:
        with connexion() as conn:
            commande = conn.execute(
                """SELECT id, id_table FROM commandes
                   WHERE reference = %s AND id_etablissement = %s""",
                (reference, courant()),
            ).fetchone()
            if not commande:
                return {"success": False, "error": "Commande introuvable"}
            if not commande_du_domaine(conn, commande["id"], domaines):
                return {"success": False, "error": "Ce ticket n'est pas le vôtre"}

            if statut in ("Payée", "Annulée"):
                conn.execute(
                    """UPDATE commandes
                       SET statut = %s, date_cloture = NOW()
                       WHERE id = %s""",
                    (statut, commande["id"]),
                )
                liberer_table(conn, commande["id_table"])
            else:
                conn.execute(
                    "UPDATE commandes SET statut = %s WHERE id = %s",
                    (statut, commande["id"]),
                )
            conn.commit()
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}

    return {"success": True}


def commande_du_domaine(conn, id_commande, domaines):
    """Le ticket ne contient-il que des articles du domaine du rôle ?"""
    if not domaines:
        return True

    marqueurs = ", ".join(["%s"] * len(domaines))
    ligne = conn.execute(
        f"""SELECT COUNT(*) AS lignes FROM lignes_commande l
            JOIN articles a ON l.id_article = a.id
            JOIN categories c ON a.id_categorie = c.id
            WHERE l.id_commande = %s AND c.type IN ({marqueurs})""",
        (id_commande, *domaines),
    ).fetchone()
    return ligne["lignes"] > 0


def liberer_table(conn, id_table):
    """Repasse une table en 'Libre' si plus aucun ticket ne lui est rattaché."""
    if not id_table:
        return
    encore_ouverte = conn.execute(
        """SELECT COUNT(*) AS ouvertes FROM commandes
           WHERE id_table = %s AND statut IN ('En cours', 'Servie')""",
        (id_table,),
    ).fetchone()["ouvertes"]
    if not encore_ouverte:
        conn.execute(
            "UPDATE tables_salle SET statut = 'Libre' WHERE id = %s", (id_table,)
        )


# ----------------------------------------------------------------------------
# CAISSE
# ----------------------------------------------------------------------------


def encaisser(id_utilisateur, reference_commande, montant, mode, commentaire):
    """Enregistre un encaissement ; solde la commande dès que le total est atteint."""
    if mode not in MODES_PAIEMENT:
        return {"success": False, "error": "Mode de paiement invalide"}

    try:
        montant = round(float(montant), 2)
    except (TypeError, ValueError):
        return {"success": False, "error": "Montant invalide"}

    if montant <= 0:
        return {"success": False, "error": "Le montant doit être supérieur à zéro"}

    try:
        with connexion() as conn:
            # FOR UPDATE : deux encaissements simultanés sur le même ticket
            # liraient le même reste à payer et pourraient le dépasser.
            commande = conn.execute(
                """SELECT id, montant_total, statut FROM commandes
                   WHERE reference = %s AND id_etablissement = %s FOR UPDATE""",
                (reference_commande, courant()),
            ).fetchone()
            if not commande:
                return {"success": False, "error": "Commande introuvable"}
            if commande["statut"] == "Annulée":
                return {"success": False, "error": "Cette commande a été annulée"}

            deja_paye = (
                conn.execute(
                    "SELECT SUM(montant) AS total FROM paiements WHERE id_commande = %s",
                    (commande["id"],),
                ).fetchone()["total"]
                or 0
            )
            reste = round(commande["montant_total"] - deja_paye, 2)
            if reste <= 0:
                return {"success": False, "error": "Cette commande est déjà soldée"}
            if montant > reste:
                return {
                    "success": False,
                    "error": f"Montant supérieur au reste à payer ({reste:.0f} FCFA)",
                }

            reference = generer_reference("PAI", "paiements")
            conn.execute(
                """INSERT INTO paiements
                   (id_etablissement, reference, id_commande, montant, mode,
                    commentaire, id_utilisateur)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    courant(),
                    reference,
                    commande["id"],
                    montant,
                    mode,
                    commentaire,
                    id_utilisateur,
                ),
            )

            nouveau_reste = round(reste - montant, 2)
            if nouveau_reste <= 0:
                ligne = conn.execute(
                    "SELECT id_table FROM commandes WHERE id = %s", (commande["id"],)
                ).fetchone()
                conn.execute(
                    """UPDATE commandes
                       SET statut = 'Payée', date_cloture = NOW()
                       WHERE id = %s""",
                    (commande["id"],),
                )
                liberer_table(conn, ligne["id_table"])

            conn.commit()

        return {
            "success": True,
            "reference": reference,
            "reste_a_payer": max(nouveau_reste, 0),
        }
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


# ----------------------------------------------------------------------------
# DÉPENSES
# ----------------------------------------------------------------------------


def creer_depense(
    id_utilisateur,
    libelle,
    categorie,
    montant,
    fournisseur,
    mode_paiement,
    date_depense,
    commentaire,
):
    try:
        montant = round(float(montant), 2)
        if montant <= 0:
            return {"success": False, "error": "Le montant doit être supérieur à zéro"}

        reference = generer_reference("DEP", "depenses")
        parametres = [
            courant(),
            reference,
            libelle,
            categorie,
            montant,
            fournisseur,
            mode_paiement,
            commentaire,
            id_utilisateur,
        ]

        if date_depense:
            executer(
                """INSERT INTO depenses (id_etablissement, reference, libelle,
                                         categorie, montant, fournisseur,
                                         mode_paiement, commentaire,
                                         id_utilisateur, date_depense)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (*parametres, date_depense),
            )
        else:
            executer(
                """INSERT INTO depenses (id_etablissement, reference, libelle,
                                         categorie, montant, fournisseur,
                                         mode_paiement, commentaire,
                                         id_utilisateur)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                tuple(parametres),
            )

        return {"success": True, "reference": reference}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


# ----------------------------------------------------------------------------
# UTILISATEURS
# ----------------------------------------------------------------------------


def role_refuse(id_role):
    """Message expliquant pourquoi ce rôle ne peut pas être attribué ici, ou None.

    Le contrôle est ici et pas seulement dans la liste déroulante : un
    formulaire forgé enverrait n'importe quel identifiant de rôle.
    """
    from backend import modules, roles

    ligne = lire_un("SELECT nom FROM roles WHERE id = %s", (int(id_role),))
    if not ligne:
        return "Ce rôle n'existe pas."
    if ligne["nom"] == roles.ROLE_PLATEFORME:
        return "Ce rôle est réservé à l'éditeur du logiciel."
    if ligne["nom"] in roles.ROLES_SERVEUR and not modules.actif("serveur"):
        return (
            "Cet établissement ne fonctionne pas avec des serveurs connectés : "
            "activez la fonctionnalité « Serveurs » pour attribuer ce rôle."
        )
    return None


def creer_compte(nom, email, mot_de_passe, id_role):
    if not nom or not email or not mot_de_passe or not id_role:
        return {
            "success": False,
            "error": "Nom, email, mot de passe et rôle sont obligatoires",
        }
    if len(mot_de_passe) < LONGUEUR_MOT_DE_PASSE:
        return {
            "success": False,
            "error": f"Le mot de passe doit faire au moins {LONGUEUR_MOT_DE_PASSE} caractères",
        }

    try:
        refus = role_refuse(id_role)
        if refus:
            return {"success": False, "error": refus}
        id_utilisateur = creer_utilisateur(
            nom, email, mot_de_passe, int(id_role), courant()
        )
        return {"success": True, "id_utilisateur": id_utilisateur}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def basculer_compte(id_utilisateur, actif, id_courant):
    """Active ou désactive un compte, sans permettre de se verrouiller soi-même."""
    if not actif and int(id_utilisateur) == int(id_courant or 0):
        return {
            "success": False,
            "error": "Vous ne pouvez pas désactiver votre propre compte",
        }
    try:
        executer(
            """UPDATE utilisateurs SET actif = %s
               WHERE id = %s AND id_etablissement = %s""",
            (1 if actif else 0, int(id_utilisateur), courant()),
        )
        return {"success": True}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def changer_role(id_utilisateur, id_role, id_courant):
    """Le gérant ne peut pas se retirer à lui-même l'accès à l'administration."""
    if int(id_utilisateur) == int(id_courant or 0):
        return {
            "success": False,
            "error": "Vous ne pouvez pas changer votre propre rôle",
        }
    try:
        refus = role_refuse(id_role)
        if refus:
            return {"success": False, "error": refus}
        executer(
            """UPDATE utilisateurs SET id_role = %s
               WHERE id = %s AND id_etablissement = %s""",
            (int(id_role), int(id_utilisateur), courant()),
        )
        return {"success": True}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def reinitialiser_mot_de_passe(id_utilisateur, mot_de_passe):
    if not mot_de_passe or len(mot_de_passe) < LONGUEUR_MOT_DE_PASSE:
        return {
            "success": False,
            "error": f"Le mot de passe doit faire au moins {LONGUEUR_MOT_DE_PASSE} caractères",
        }
    try:
        executer(
            """UPDATE utilisateurs SET mot_de_passe = %s
               WHERE id = %s AND id_etablissement = %s""",
            (generate_password_hash(mot_de_passe), int(id_utilisateur), courant()),
        )
        return {"success": True}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}
