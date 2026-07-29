"""Toutes les écritures : commandes, encaissements, menu, stock, dépenses."""

from backend.database import connexion, executer, generer_reference

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
            "INSERT INTO tables_salle (numero, zone, places) VALUES (?, ?, ?)",
            (numero, zone, int(places)),
        )
        return {"success": True, "id_table": id_table}
    except Exception as erreur:
        return {"success": False, "error": str(erreur)}


def changer_statut_table(id_table, statut):
    if statut not in STATUTS_TABLE:
        return {"success": False, "error": "Statut de table invalide"}
    executer("UPDATE tables_salle SET statut = ? WHERE id = ?", (statut, id_table))
    return {"success": True}


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
    try:
        reference = generer_reference("ART", "articles")
        id_article = executer(
            """
            INSERT INTO articles (reference, nom, id_categorie, prix, cout_revient,
                                  gere_stock, stock, seuil_alerte, disponible,
                                  image, id_utilisateur)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reference,
                nom,
                id_categorie,
                float(prix),
                float(cout_revient or 0),
                int(gere_stock),
                int(stock or 0),
                int(seuil_alerte or 0),
                int(disponible),
                image,
                id_utilisateur,
            ),
        )
        if int(gere_stock) and int(stock or 0) > 0:
            enregistrer_mouvement(
                id_article,
                "Entrée",
                int(stock),
                "Stock initial",
                id_utilisateur,
            )
        return {"success": True, "id_article": id_article, "reference": reference}
    except Exception as erreur:
        return {"success": False, "error": str(erreur)}


def basculer_disponibilite(id_article, disponible):
    executer(
        "UPDATE articles SET disponible = ? WHERE id = ?",
        (1 if disponible else 0, id_article),
    )
    return {"success": True}


def creer_categorie(nom, type_categorie):
    try:
        id_categorie = executer(
            "INSERT INTO categories (nom, type) VALUES (?, ?)", (nom, type_categorie)
        )
        return {"success": True, "id_categorie": id_categorie}
    except Exception as erreur:
        return {"success": False, "error": str(erreur)}


# ----------------------------------------------------------------------------
# STOCK
# ----------------------------------------------------------------------------


def enregistrer_mouvement(id_article, type_mouvement, quantite, motif, id_utilisateur):
    """Applique un mouvement de stock et journalise l'opération."""
    quantite = int(quantite)
    # Un inventaire saisit le stock réel constaté, qui peut légitimement être nul.
    if quantite < 0 or (quantite == 0 and type_mouvement != "Inventaire"):
        return {"success": False, "error": "La quantité doit être supérieure à zéro"}

    with connexion() as conn:
        ligne = conn.execute(
            "SELECT stock, gere_stock FROM articles WHERE id = ?", (id_article,)
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
            "UPDATE articles SET stock = ? WHERE id = ?", (stock_apres, id_article)
        )
        conn.execute(
            """INSERT INTO mouvements_stock
               (id_article, type_mouvement, quantite, stock_apres, motif, id_utilisateur)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id_article, type_mouvement, quantite, stock_apres, motif, id_utilisateur),
        )
        conn.commit()

    return {"success": True, "stock_apres": stock_apres}


# ----------------------------------------------------------------------------
# COMMANDES
# ----------------------------------------------------------------------------


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
):
    """Ouvre un ticket, décrémente le stock des boissons et occupe la table."""
    if not articles:
        return {"success": False, "error": "Aucun article dans la commande"}
    if type_service not in TYPES_SERVICE:
        return {"success": False, "error": "Type de service invalide"}

    reference = generer_reference("CMD", "commandes")

    try:
        with connexion() as conn:
            montant_total = 0
            lignes = []

            for article in articles:
                ligne = conn.execute(
                    "SELECT id, nom, prix, gere_stock, stock, disponible FROM articles WHERE id = ?",
                    (article["id_article"],),
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
                INSERT INTO commandes (reference, id_table, type_service, nom_client,
                                       telephone_client, couverts, montant_total,
                                       remise, commentaire, id_utilisateur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
                       VALUES (?, ?, ?, ?, ?, ?)""",
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
                        "UPDATE articles SET stock = ? WHERE id = ?",
                        (stock_apres, ligne["id_article"]),
                    )
                    conn.execute(
                        """INSERT INTO mouvements_stock
                           (id_article, type_mouvement, quantite, stock_apres, motif, id_utilisateur)
                           VALUES (?, 'Sortie', ?, ?, ?, ?)""",
                        (
                            ligne["id_article"],
                            ligne["quantite"],
                            stock_apres,
                            f"Commande {reference}",
                            id_utilisateur,
                        ),
                    )

            if id_table:
                conn.execute(
                    "UPDATE tables_salle SET statut = 'Occupée' WHERE id = ?",
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
        return {"success": False, "error": str(erreur)}


def changer_statut_commande(reference, statut):
    if statut not in STATUTS_COMMANDE:
        return {"success": False, "error": "Statut de commande invalide"}

    with connexion() as conn:
        commande = conn.execute(
            "SELECT id, id_table FROM commandes WHERE reference = ?", (reference,)
        ).fetchone()
        if not commande:
            return {"success": False, "error": "Commande introuvable"}

        if statut in ("Payée", "Annulée"):
            conn.execute(
                """UPDATE commandes
                   SET statut = ?, date_cloture = datetime('now', 'localtime')
                   WHERE id = ?""",
                (statut, commande["id"]),
            )
            liberer_table(conn, commande["id_table"])
        else:
            conn.execute(
                "UPDATE commandes SET statut = ? WHERE id = ?", (statut, commande["id"])
            )
        conn.commit()

    return {"success": True}


def liberer_table(conn, id_table):
    """Repasse une table en 'Libre' si plus aucun ticket ne lui est rattaché."""
    if not id_table:
        return
    encore_ouverte = conn.execute(
        """SELECT COUNT(*) FROM commandes
           WHERE id_table = ? AND statut IN ('En cours', 'Servie')""",
        (id_table,),
    ).fetchone()[0]
    if not encore_ouverte:
        conn.execute(
            "UPDATE tables_salle SET statut = 'Libre' WHERE id = ?", (id_table,)
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
            commande = conn.execute(
                "SELECT id, montant_total, statut FROM commandes WHERE reference = ?",
                (reference_commande,),
            ).fetchone()
            if not commande:
                return {"success": False, "error": "Commande introuvable"}
            if commande["statut"] == "Annulée":
                return {"success": False, "error": "Cette commande a été annulée"}

            deja_paye = (
                conn.execute(
                    "SELECT SUM(montant) FROM paiements WHERE id_commande = ?",
                    (commande["id"],),
                ).fetchone()[0]
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
                   (reference, id_commande, montant, mode, commentaire, id_utilisateur)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
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
                    "SELECT id_table FROM commandes WHERE id = ?", (commande["id"],)
                ).fetchone()
                conn.execute(
                    """UPDATE commandes
                       SET statut = 'Payée', date_cloture = datetime('now', 'localtime')
                       WHERE id = ?""",
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
        return {"success": False, "error": str(erreur)}


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
                """INSERT INTO depenses (reference, libelle, categorie, montant,
                                         fournisseur, mode_paiement, commentaire,
                                         id_utilisateur, date_depense)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*parametres, date_depense),
            )
        else:
            executer(
                """INSERT INTO depenses (reference, libelle, categorie, montant,
                                         fournisseur, mode_paiement, commentaire,
                                         id_utilisateur)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(parametres),
            )

        return {"success": True, "reference": reference}
    except Exception as erreur:
        return {"success": False, "error": str(erreur)}
