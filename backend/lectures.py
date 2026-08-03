"""Toutes les lectures : listes affichées dans l'interface et indicateurs du dashboard."""

from datetime import date, timedelta

from backend.database import lire_tout, lire_un


def _restriction(domaines, alias="c"):
    """Fragment SQL limitant aux types de catégories du rôle (« Bar », « Cuisine »).

    Renvoie une condition vide quand le rôle n'est pas cloisonné.
    """
    if not domaines:
        return "", ()
    marqueurs = ", ".join(["%s"] * len(domaines))
    return f" AND {alias}.type IN ({marqueurs})", tuple(domaines)

# ----------------------------------------------------------------------------
# SALLE
# ----------------------------------------------------------------------------


def liste_tables():
    return lire_tout(
        """
        SELECT t.id, t.numero, t.zone, t.places, t.statut,
               c.reference AS commande_en_cours,
               c.montant_total AS montant_en_cours,
               c.date_commande AS ouverte_depuis
        FROM tables_salle t
        LEFT JOIN commandes c
               ON c.id_table = t.id AND c.statut IN ('En cours', 'Servie')
        ORDER BY t.zone, CAST(t.numero AS UNSIGNED), t.numero
        """
    )


def compteurs_salle():
    return lire_un(
        """
        SELECT COUNT(*) AS total_tables,
               COALESCE(SUM(statut = 'Occupée'), 0) AS tables_occupees,
               COALESCE(SUM(statut = 'Libre'), 0) AS tables_libres
        FROM tables_salle
        """
    )


def table_par_id(id_table):
    return lire_un("SELECT * FROM tables_salle WHERE id = %s", (id_table,))


# ----------------------------------------------------------------------------
# MENU
# ----------------------------------------------------------------------------


def liste_categories(domaines=None):
    condition, params = _restriction(domaines, alias="categories")
    return lire_tout(
        f"SELECT id, nom, type FROM categories WHERE 1 = 1{condition}"
        " ORDER BY type, nom",
        params,
    )


def liste_articles(domaines=None):
    condition, params = _restriction(domaines)
    return lire_tout(
        f"""
        SELECT a.id, a.reference, a.nom, a.prix, a.cout_revient, a.gere_stock,
               a.stock, a.seuil_alerte, a.disponible, a.image, a.date_creation,
               COALESCE(c.nom, 'Sans catégorie') AS categorie,
               COALESCE(c.type, 'Cuisine') AS type_categorie
        FROM articles a
        LEFT JOIN categories c ON a.id_categorie = c.id
        WHERE 1 = 1{condition}
        ORDER BY a.date_creation DESC, a.id DESC
        """,
        params,
    )


def articles_disponibles(domaines=None):
    """Articles proposables à la commande (disponibles et en stock si géré)."""
    condition, params = _restriction(domaines)
    return lire_tout(
        f"""
        SELECT a.id, a.reference, a.nom, a.prix, a.gere_stock, a.stock,
               COALESCE(c.nom, 'Sans catégorie') AS categorie
        FROM articles a
        LEFT JOIN categories c ON a.id_categorie = c.id
        WHERE a.disponible = 1 AND (a.gere_stock = 0 OR a.stock > 0){condition}
        ORDER BY c.nom, a.nom
        """,
        params,
    )


def compteurs_menu(domaines=None):
    condition, params = _restriction(domaines)
    return lire_un(
        f"""
        SELECT COUNT(*) AS total_articles,
               COALESCE(SUM(a.disponible = 0 OR (a.gere_stock = 1 AND a.stock <= 0)), 0)
                   AS indisponibles,
               COALESCE(SUM(a.gere_stock = 1 AND a.stock > 0
                            AND a.stock <= a.seuil_alerte), 0) AS stock_faible
        FROM articles a
        LEFT JOIN categories c ON a.id_categorie = c.id
        WHERE 1 = 1{condition}
        """,
        params,
    )


def statut_stock(article):
    """Libellé de stock affiché dans les tableaux."""
    if not article["gere_stock"]:
        return "Préparé"
    if article["stock"] <= 0:
        return "Rupture"
    if article["stock"] <= article["seuil_alerte"]:
        return "Stock faible"
    return "En stock"


# ----------------------------------------------------------------------------
# STOCK
# ----------------------------------------------------------------------------


def liste_stock():
    articles = lire_tout(
        """
        SELECT a.id, a.reference, a.nom, a.stock, a.seuil_alerte, a.prix,
               a.cout_revient, COALESCE(c.nom, 'Sans catégorie') AS categorie
        FROM articles a
        LEFT JOIN categories c ON a.id_categorie = c.id
        WHERE a.gere_stock = 1
        ORDER BY a.stock ASC, a.nom
        """
    )
    for article in articles:
        article["gere_stock"] = 1
        article["statut"] = statut_stock(article)
        article["valeur_stock"] = round(article["stock"] * article["cout_revient"], 2)
    return articles


def compteurs_stock():
    compteurs = lire_un(
        """
        SELECT COUNT(*) AS articles_suivis,
               COALESCE(SUM(stock <= 0), 0) AS ruptures,
               COALESCE(SUM(stock * cout_revient), 0) AS valeur_stock
        FROM articles
        WHERE gere_stock = 1
        """
    )
    compteurs["valeur_stock"] = round(compteurs["valeur_stock"], 2)
    return compteurs


def derniers_mouvements(limite=50):
    return lire_tout(
        """
        SELECT m.id, m.type_mouvement, m.quantite, m.stock_apres, m.motif,
               m.date_mouvement, a.nom AS article, a.reference,
               COALESCE(u.nom, 'Système') AS utilisateur
        FROM mouvements_stock m
        JOIN articles a ON m.id_article = a.id
        LEFT JOIN utilisateurs u ON m.id_utilisateur = u.id
        ORDER BY m.date_mouvement DESC, m.id DESC
        LIMIT %s
        """,
        (limite,),
    )


# ----------------------------------------------------------------------------
# COMMANDES
# ----------------------------------------------------------------------------


def _commande_du_domaine(domaines, alias="c"):
    """Ticket ne contenant que des articles du domaine du rôle."""
    if not domaines:
        return "", ()
    marqueurs = ", ".join(["%s"] * len(domaines))
    return (
        f""" AND EXISTS (SELECT 1 FROM lignes_commande l
                          JOIN articles a ON l.id_article = a.id
                          JOIN categories cat ON a.id_categorie = cat.id
                         WHERE l.id_commande = {alias}.id
                           AND cat.type IN ({marqueurs}))""",
        tuple(domaines),
    )


def liste_commandes(limite=200, domaines=None):
    condition, params = _commande_du_domaine(domaines)
    commandes = lire_tout(
        f"""
        SELECT c.id, c.reference, c.type_service, c.nom_client, c.couverts,
               c.statut, c.montant_total, c.remise, c.commentaire,
               c.date_commande, c.date_cloture,
               COALESCE(t.numero, '—') AS table_numero,
               COALESCE(u.nom, '—') AS serveur,
               COALESCE((SELECT SUM(montant) FROM paiements p
                         WHERE p.id_commande = c.id), 0) AS total_paye
        FROM commandes c
        LEFT JOIN tables_salle t ON c.id_table = t.id
        LEFT JOIN utilisateurs u ON c.id_utilisateur = u.id
        WHERE 1 = 1{condition}
        ORDER BY c.id DESC
        LIMIT %s
        """,
        (*params, limite),
    )
    resumes = resumes_articles([commande["id"] for commande in commandes])
    for commande in commandes:
        commande["reste_a_payer"] = round(
            max(commande["montant_total"] - commande["total_paye"], 0), 2
        )
        commande["articles"] = resumes.get(commande["id"], "")
    return commandes


def resumes_articles(ids_commande):
    """Résumé « 2x Attiéké, 1x Alloco » de plusieurs commandes, en une seule requête."""
    if not ids_commande:
        return {}

    marqueurs = ", ".join(["%s"] * len(ids_commande))
    lignes = lire_tout(
        f"""
        SELECT l.id_commande, a.nom, l.quantite
        FROM lignes_commande l
        JOIN articles a ON l.id_article = a.id
        WHERE l.id_commande IN ({marqueurs})
        ORDER BY l.id
        """,
        tuple(ids_commande),
    )

    resumes = {}
    for ligne in lignes:
        resumes.setdefault(ligne["id_commande"], []).append(
            f"{ligne['quantite']}x {ligne['nom']}"
        )
    return {
        id_commande: ", ".join(articles) for id_commande, articles in resumes.items()
    }


def detail_commande(reference, domaines=None):
    condition, params = _commande_du_domaine(domaines)
    commande = lire_un(
        f"""
        SELECT c.*, COALESCE(t.numero, '—') AS table_numero,
               COALESCE(u.nom, '—') AS serveur,
               COALESCE((SELECT SUM(montant) FROM paiements p
                         WHERE p.id_commande = c.id), 0) AS total_paye
        FROM commandes c
        LEFT JOIN tables_salle t ON c.id_table = t.id
        LEFT JOIN utilisateurs u ON c.id_utilisateur = u.id
        WHERE c.reference = %s{condition}
        """,
        (reference, *params),
    )
    if not commande:
        return None

    commande["reste_a_payer"] = round(
        max(commande["montant_total"] - commande["total_paye"], 0), 2
    )
    commande["lignes"] = lire_tout(
        """
        SELECT a.nom AS article, a.reference, l.quantite, l.prix_unitaire,
               l.total, l.note
        FROM lignes_commande l
        JOIN articles a ON l.id_article = a.id
        WHERE l.id_commande = %s
        ORDER BY l.id
        """,
        (commande["id"],),
    )
    commande["paiements"] = lire_tout(
        """
        SELECT reference, montant, mode, date_paiement
        FROM paiements WHERE id_commande = %s ORDER BY id
        """,
        (commande["id"],),
    )
    return commande


def compteurs_commandes(domaines=None):
    condition, params = _commande_du_domaine(domaines)
    compteurs = lire_un(
        f"""
        SELECT
          (SELECT COUNT(*) FROM commandes c
            WHERE c.date_commande >= CURDATE()
              AND c.date_commande < CURDATE() + INTERVAL 1 DAY{condition}) AS commandes_jour,
          (SELECT COUNT(*) FROM commandes c
            WHERE c.statut IN ('En cours', 'Servie'){condition}) AS commandes_en_cours,
          (SELECT COALESCE(SUM(c.montant_total - COALESCE(
                    (SELECT SUM(p.montant) FROM paiements p
                      WHERE p.id_commande = c.id), 0)), 0)
             FROM commandes c
            WHERE c.statut IN ('En cours', 'Servie'){condition}) AS montant_impaye
        """,
        params * 3,
    )
    compteurs["montant_impaye"] = round(compteurs["montant_impaye"], 2)
    return compteurs


# ----------------------------------------------------------------------------
# CAISSE
# ----------------------------------------------------------------------------


def liste_paiements(limite=200):
    return lire_tout(
        """
        SELECT p.id, p.reference, p.montant, p.mode, p.commentaire, p.date_paiement,
               c.reference AS commande, c.montant_total, c.nom_client,
               COALESCE(t.numero, '—') AS table_numero,
               COALESCE(u.nom, '—') AS caissier
        FROM paiements p
        JOIN commandes c ON p.id_commande = c.id
        LEFT JOIN tables_salle t ON c.id_table = t.id
        LEFT JOIN utilisateurs u ON p.id_utilisateur = u.id
        ORDER BY p.id DESC
        LIMIT %s
        """,
        (limite,),
    )


def compteurs_caisse():
    compteurs = lire_un(
        """
        SELECT
          (SELECT COALESCE(SUM(montant), 0) FROM paiements
            WHERE date_paiement >= CURDATE()
              AND date_paiement < CURDATE() + INTERVAL 1 DAY) AS encaisse_jour,
          (SELECT COALESCE(SUM(montant), 0) FROM paiements) AS encaisse_total,
          (SELECT COUNT(*) FROM paiements
            WHERE date_paiement >= CURDATE()
              AND date_paiement < CURDATE() + INTERVAL 1 DAY) AS nb_paiements_jour
        """
    )
    compteurs["encaisse_jour"] = round(compteurs["encaisse_jour"], 2)
    compteurs["encaisse_total"] = round(compteurs["encaisse_total"], 2)
    return compteurs


def commandes_a_encaisser():
    return lire_tout(
        """
        SELECT c.id, c.reference, c.montant_total, c.nom_client,
               COALESCE(t.numero, '—') AS table_numero,
               COALESCE((SELECT SUM(p.montant) FROM paiements p
                         WHERE p.id_commande = c.id), 0) AS total_paye
        FROM commandes c
        LEFT JOIN tables_salle t ON c.id_table = t.id
        WHERE c.statut IN ('En cours', 'Servie')
        ORDER BY c.id DESC
        """
    )


def repartition_modes_paiement():
    return lire_tout(
        """
        SELECT mode, COUNT(*) AS nombre, SUM(montant) AS total
        FROM paiements
        WHERE DATE(date_paiement) = CURDATE()
        GROUP BY mode
        ORDER BY total DESC
        """
    )


# ----------------------------------------------------------------------------
# DÉPENSES
# ----------------------------------------------------------------------------


def liste_depenses(limite=200):
    return lire_tout(
        """
        SELECT d.id, d.reference, d.libelle, d.categorie, d.montant, d.fournisseur,
               d.mode_paiement, d.commentaire, d.date_depense,
               COALESCE(u.nom, '—') AS utilisateur
        FROM depenses d
        LEFT JOIN utilisateurs u ON d.id_utilisateur = u.id
        ORDER BY d.date_depense DESC, d.id DESC
        LIMIT %s
        """,
        (limite,),
    )


def compteurs_depenses():
    compteurs = lire_un(
        """
        SELECT COALESCE(SUM(CASE WHEN date_depense = CURDATE()
                                 THEN montant ELSE 0 END), 0) AS depenses_jour,
               COALESCE(SUM(CASE WHEN mois_courant THEN montant ELSE 0 END), 0)
                   AS depenses_mois,
               COALESCE(SUM(mois_courant), 0) AS nb_depenses_mois
        FROM (SELECT montant, date_depense,
                     YEAR(date_depense) = YEAR(CURDATE())
                     AND MONTH(date_depense) = MONTH(CURDATE()) AS mois_courant
              FROM depenses) d
        """
    )
    compteurs["depenses_jour"] = round(compteurs["depenses_jour"], 2)
    compteurs["depenses_mois"] = round(compteurs["depenses_mois"], 2)
    return compteurs


# ----------------------------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------------------------


def indicateurs_jour():
    """Recette du jour, recette totale, ticket moyen et couverts, en une requête."""
    paiements = lire_un(
        """
        SELECT
          (SELECT COALESCE(SUM(montant), 0) FROM paiements
            WHERE date_paiement >= CURDATE()
              AND date_paiement < CURDATE() + INTERVAL 1 DAY) AS ca_jour,
          (SELECT COALESCE(SUM(montant), 0) FROM paiements) AS ca_total
        """
    )
    commandes = lire_un(
        """
        SELECT COALESCE(SUM(montant_total), 0) AS total_jour,
               COUNT(*) AS nombre_jour,
               COALESCE(SUM(couverts), 0) AS couverts_jour
        FROM commandes
        WHERE date_commande >= CURDATE()
          AND date_commande < CURDATE() + INTERVAL 1 DAY
          AND statut != 'Annulée'
        """
    )
    nombre = commandes["nombre_jour"]
    return {
        "ca_jour": round(paiements["ca_jour"], 2),
        "ca_total": round(paiements["ca_total"], 2),
        "ticket_moyen": round(commandes["total_jour"] / nombre, 2) if nombre else 0,
        "couverts_jour": commandes["couverts_jour"],
    }


def ca_par_jour(nb_jours=7):
    """Chiffre d'affaires et nombre de commandes des N derniers jours, trous compris."""
    debut = date.today() - timedelta(days=nb_jours - 1)
    lignes = lire_tout(
        """
        SELECT DATE(date_paiement) AS jour, SUM(montant) AS revenu
        FROM paiements
        WHERE DATE(date_paiement) >= %s
        GROUP BY jour
        """,
        (debut.isoformat(),),
    )
    revenus = {ligne["jour"]: ligne["revenu"] for ligne in lignes}

    lignes_commandes = lire_tout(
        """
        SELECT DATE(date_commande) AS jour, COUNT(*) AS nombre
        FROM commandes
        WHERE DATE(date_commande) >= %s AND statut != 'Annulée'
        GROUP BY jour
        """,
        (debut.isoformat(),),
    )
    nombres = {ligne["jour"]: ligne["nombre"] for ligne in lignes_commandes}

    serie = []
    for decalage in range(nb_jours):
        jour = debut + timedelta(days=decalage)
        cle = jour.isoformat()
        serie.append(
            {
                "date": jour.strftime("%d/%m"),
                "nombre_commandes": nombres.get(cle, 0),
                "revenu": round(revenus.get(cle, 0), 2),
            }
        )
    return serie


def top_articles(limite=5, nb_jours=30):
    return lire_tout(
        """
        SELECT a.nom, SUM(l.quantite) AS quantite, SUM(l.total) AS revenu
        FROM lignes_commande l
        JOIN articles a ON l.id_article = a.id
        JOIN commandes c ON l.id_commande = c.id
        WHERE c.statut != 'Annulée'
          AND DATE(c.date_commande) >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY a.id, a.nom
        ORDER BY quantite DESC
        LIMIT %s
        """,
        (nb_jours, limite),
    )


def dernieres_commandes(limite=5):
    return lire_tout(
        """
        SELECT c.reference, c.statut, c.montant_total, c.date_commande,
               COALESCE(c.nom_client, 'Client comptoir') AS client,
               COALESCE(t.numero, '—') AS table_numero
        FROM commandes c
        LEFT JOIN tables_salle t ON c.id_table = t.id
        ORDER BY c.id DESC
        LIMIT %s
        """,
        (limite,),
    )


def _sommes_deux_mois(table, colonne_date, colonne_montant, bornes):
    """Somme du mois courant et du mois précédent en une seule requête."""
    return lire_un(
        f"""
        SELECT COALESCE(SUM(CASE WHEN DATE({colonne_date}) >= %s
                                  AND DATE({colonne_date}) < %s
                                 THEN {colonne_montant} ELSE 0 END), 0) AS courant,
               COALESCE(SUM(CASE WHEN DATE({colonne_date}) >= %s
                                  AND DATE({colonne_date}) < %s
                                 THEN {colonne_montant} ELSE 0 END), 0) AS precedent
        FROM {table}
        """,
        bornes,
    )


def _bornes_mois(decalage=0):
    """Premier jour du mois courant (decalage=0) ou du mois précédent (decalage=-1)."""
    premier_du_mois = date.today().replace(day=1)
    if decalage == 0:
        suivant = (premier_du_mois + timedelta(days=32)).replace(day=1)
        return premier_du_mois.isoformat(), suivant.isoformat()
    precedent = (premier_du_mois - timedelta(days=1)).replace(day=1)
    return precedent.isoformat(), premier_du_mois.isoformat()


def _bornes_deux_mois():
    debut_courant, fin_courant = _bornes_mois(0)
    debut_precedent, fin_precedent = _bornes_mois(-1)
    return (debut_courant, fin_courant, debut_precedent, fin_precedent)


def evolution(table, colonne_date, colonne_montant="montant"):
    """Variation en pourcentage entre le mois en cours et le mois précédent."""
    sommes = _sommes_deux_mois(
        table, colonne_date, colonne_montant, _bornes_deux_mois()
    )
    return calculer_pourcentage(sommes["courant"], sommes["precedent"])


def evolution_nombre(table, colonne_date, condition="1 = 1"):
    """Variation en pourcentage du nombre de lignes entre ce mois et le précédent."""
    sommes = lire_un(
        f"""
        SELECT COALESCE(SUM(DATE({colonne_date}) >= %s
                            AND DATE({colonne_date}) < %s), 0) AS courant,
               COALESCE(SUM(DATE({colonne_date}) >= %s
                            AND DATE({colonne_date}) < %s), 0) AS precedent
        FROM {table}
        WHERE {condition}
        """,
        _bornes_deux_mois(),
    )
    return calculer_pourcentage(sommes["courant"], sommes["precedent"])


def calculer_pourcentage(courant, precedent):
    courant = courant or 0
    precedent = precedent or 0
    if precedent == 0:
        return 100 if courant > 0 else 0
    return round(((courant - precedent) / precedent) * 100, 1)


# ----------------------------------------------------------------------------
# UTILISATEURS
# ----------------------------------------------------------------------------


def liste_utilisateurs():
    return lire_tout(
        """
        SELECT u.id, u.nom, u.email, u.actif, u.id_role, u.date_creation,
               r.nom AS role
        FROM utilisateurs u
        JOIN roles r ON u.id_role = r.id
        ORDER BY r.id, u.nom
        """
    )


def liste_roles():
    return lire_tout("SELECT id, nom FROM roles ORDER BY id")
