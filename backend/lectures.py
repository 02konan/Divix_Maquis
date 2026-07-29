"""Toutes les lectures : listes affichées dans l'interface et indicateurs du dashboard."""

from datetime import date, timedelta

from backend.database import lire_tout, lire_un, valeur

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
        ORDER BY t.zone, CAST(t.numero AS INTEGER), t.numero
        """
    )


def compteurs_salle():
    return {
        "total_tables": valeur("SELECT COUNT(*) FROM tables_salle"),
        "tables_occupees": valeur(
            "SELECT COUNT(*) FROM tables_salle WHERE statut = 'Occupée'"
        ),
        "tables_libres": valeur(
            "SELECT COUNT(*) FROM tables_salle WHERE statut = 'Libre'"
        ),
    }


def table_par_id(id_table):
    return lire_un("SELECT * FROM tables_salle WHERE id = ?", (id_table,))


# ----------------------------------------------------------------------------
# MENU
# ----------------------------------------------------------------------------


def liste_categories():
    return lire_tout("SELECT id, nom, type FROM categories ORDER BY type, nom")


def liste_articles():
    return lire_tout(
        """
        SELECT a.id, a.reference, a.nom, a.prix, a.cout_revient, a.gere_stock,
               a.stock, a.seuil_alerte, a.disponible, a.image, a.date_creation,
               COALESCE(c.nom, 'Sans catégorie') AS categorie,
               COALESCE(c.type, 'Cuisine') AS type_categorie
        FROM articles a
        LEFT JOIN categories c ON a.id_categorie = c.id
        ORDER BY a.date_creation DESC, a.id DESC
        """
    )


def articles_disponibles():
    """Articles proposables à la commande (disponibles et en stock si géré)."""
    return lire_tout(
        """
        SELECT a.id, a.reference, a.nom, a.prix, a.gere_stock, a.stock,
               COALESCE(c.nom, 'Sans catégorie') AS categorie
        FROM articles a
        LEFT JOIN categories c ON a.id_categorie = c.id
        WHERE a.disponible = 1 AND (a.gere_stock = 0 OR a.stock > 0)
        ORDER BY c.nom, a.nom
        """
    )


def compteurs_menu():
    return {
        "total_articles": valeur("SELECT COUNT(*) FROM articles"),
        "indisponibles": valeur(
            """SELECT COUNT(*) FROM articles
               WHERE disponible = 0 OR (gere_stock = 1 AND stock <= 0)"""
        ),
        "stock_faible": valeur(
            """SELECT COUNT(*) FROM articles
               WHERE gere_stock = 1 AND stock > 0 AND stock <= seuil_alerte"""
        ),
    }


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
    return {
        "articles_suivis": valeur("SELECT COUNT(*) FROM articles WHERE gere_stock = 1"),
        "ruptures": valeur(
            "SELECT COUNT(*) FROM articles WHERE gere_stock = 1 AND stock <= 0"
        ),
        "valeur_stock": round(
            valeur(
                "SELECT SUM(stock * cout_revient) FROM articles WHERE gere_stock = 1"
            ),
            2,
        ),
    }


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
        LIMIT ?
        """,
        (limite,),
    )


# ----------------------------------------------------------------------------
# COMMANDES
# ----------------------------------------------------------------------------


def liste_commandes(limite=200):
    commandes = lire_tout(
        """
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
        ORDER BY c.id DESC
        LIMIT ?
        """,
        (limite,),
    )
    for commande in commandes:
        commande["reste_a_payer"] = round(
            max(commande["montant_total"] - commande["total_paye"], 0), 2
        )
        commande["articles"] = resume_articles(commande["id"])
    return commandes


def resume_articles(id_commande):
    lignes = lire_tout(
        """
        SELECT a.nom, l.quantite
        FROM lignes_commande l
        JOIN articles a ON l.id_article = a.id
        WHERE l.id_commande = ?
        ORDER BY l.id
        """,
        (id_commande,),
    )
    return ", ".join(f"{ligne['quantite']}x {ligne['nom']}" for ligne in lignes)


def detail_commande(reference):
    commande = lire_un(
        """
        SELECT c.*, COALESCE(t.numero, '—') AS table_numero,
               COALESCE(u.nom, '—') AS serveur,
               COALESCE((SELECT SUM(montant) FROM paiements p
                         WHERE p.id_commande = c.id), 0) AS total_paye
        FROM commandes c
        LEFT JOIN tables_salle t ON c.id_table = t.id
        LEFT JOIN utilisateurs u ON c.id_utilisateur = u.id
        WHERE c.reference = ?
        """,
        (reference,),
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
        WHERE l.id_commande = ?
        ORDER BY l.id
        """,
        (commande["id"],),
    )
    commande["paiements"] = lire_tout(
        """
        SELECT reference, montant, mode, date_paiement
        FROM paiements WHERE id_commande = ? ORDER BY id
        """,
        (commande["id"],),
    )
    return commande


def compteurs_commandes():
    return {
        "commandes_jour": valeur(
            "SELECT COUNT(*) FROM commandes WHERE date(date_commande) = date('now', 'localtime')"
        ),
        "commandes_en_cours": valeur(
            "SELECT COUNT(*) FROM commandes WHERE statut IN ('En cours', 'Servie')"
        ),
        "montant_impaye": round(
            valeur(
                """
                SELECT SUM(c.montant_total - COALESCE(
                    (SELECT SUM(p.montant) FROM paiements p WHERE p.id_commande = c.id), 0))
                FROM commandes c
                WHERE c.statut IN ('En cours', 'Servie')
                """
            ),
            2,
        ),
    }


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
        LIMIT ?
        """,
        (limite,),
    )


def compteurs_caisse():
    return {
        "encaisse_jour": round(
            valeur(
                """SELECT SUM(montant) FROM paiements
                   WHERE date(date_paiement) = date('now', 'localtime')"""
            ),
            2,
        ),
        "encaisse_total": round(valeur("SELECT SUM(montant) FROM paiements"), 2),
        "nb_paiements_jour": valeur(
            """SELECT COUNT(*) FROM paiements
               WHERE date(date_paiement) = date('now', 'localtime')"""
        ),
    }


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
        WHERE date(date_paiement) = date('now', 'localtime')
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
        LIMIT ?
        """,
        (limite,),
    )


def compteurs_depenses():
    return {
        "depenses_jour": round(
            valeur(
                "SELECT SUM(montant) FROM depenses WHERE date_depense = date('now', 'localtime')"
            ),
            2,
        ),
        "depenses_mois": round(
            valeur(
                """SELECT SUM(montant) FROM depenses
                   WHERE strftime('%Y-%m', date_depense) = strftime('%Y-%m', 'now', 'localtime')"""
            ),
            2,
        ),
        "nb_depenses_mois": valeur(
            """SELECT COUNT(*) FROM depenses
               WHERE strftime('%Y-%m', date_depense) = strftime('%Y-%m', 'now', 'localtime')"""
        ),
    }


# ----------------------------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------------------------


def chiffre_affaires_jour():
    return round(
        valeur(
            """SELECT SUM(montant) FROM paiements
               WHERE date(date_paiement) = date('now', 'localtime')"""
        ),
        2,
    )


def chiffre_affaires_total():
    return round(valeur("SELECT SUM(montant) FROM paiements"), 2)


def ticket_moyen_jour():
    total = valeur(
        """SELECT SUM(montant_total) FROM commandes
           WHERE date(date_commande) = date('now', 'localtime') AND statut != 'Annulée'"""
    )
    nombre = valeur(
        """SELECT COUNT(*) FROM commandes
           WHERE date(date_commande) = date('now', 'localtime') AND statut != 'Annulée'"""
    )
    return round(total / nombre, 2) if nombre else 0


def couverts_jour():
    return valeur(
        """SELECT SUM(couverts) FROM commandes
           WHERE date(date_commande) = date('now', 'localtime') AND statut != 'Annulée'"""
    )


def ca_par_jour(nb_jours=7):
    """Chiffre d'affaires et nombre de commandes des N derniers jours, trous compris."""
    debut = date.today() - timedelta(days=nb_jours - 1)
    lignes = lire_tout(
        """
        SELECT date(date_paiement) AS jour, SUM(montant) AS revenu
        FROM paiements
        WHERE date(date_paiement) >= ?
        GROUP BY jour
        """,
        (debut.isoformat(),),
    )
    revenus = {ligne["jour"]: ligne["revenu"] for ligne in lignes}

    lignes_commandes = lire_tout(
        """
        SELECT date(date_commande) AS jour, COUNT(*) AS nombre
        FROM commandes
        WHERE date(date_commande) >= ? AND statut != 'Annulée'
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
          AND date(c.date_commande) >= date('now', 'localtime', ?)
        GROUP BY a.id
        ORDER BY quantite DESC
        LIMIT ?
        """,
        (f"-{nb_jours} days", limite),
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
        LIMIT ?
        """,
        (limite,),
    )


def _somme_periode(table, colonne_date, colonne_montant, debut, fin):
    return valeur(
        f"""SELECT SUM({colonne_montant}) FROM {table}
            WHERE date({colonne_date}) >= ? AND date({colonne_date}) < ?""",
        (debut, fin),
    )


def _bornes_mois(decalage=0):
    """Premier jour du mois courant (decalage=0) ou du mois précédent (decalage=-1)."""
    premier_du_mois = date.today().replace(day=1)
    if decalage == 0:
        suivant = (premier_du_mois + timedelta(days=32)).replace(day=1)
        return premier_du_mois.isoformat(), suivant.isoformat()
    precedent = (premier_du_mois - timedelta(days=1)).replace(day=1)
    return precedent.isoformat(), premier_du_mois.isoformat()


def evolution(table, colonne_date, colonne_montant="montant"):
    """Variation en pourcentage entre le mois en cours et le mois précédent."""
    debut_courant, fin_courant = _bornes_mois(0)
    debut_precedent, fin_precedent = _bornes_mois(-1)
    courant = _somme_periode(
        table, colonne_date, colonne_montant, debut_courant, fin_courant
    )
    precedent = _somme_periode(
        table, colonne_date, colonne_montant, debut_precedent, fin_precedent
    )
    return calculer_pourcentage(courant, precedent)


def evolution_nombre(table, colonne_date, condition="1 = 1"):
    """Variation en pourcentage du nombre de lignes entre ce mois et le précédent."""
    debut_courant, fin_courant = _bornes_mois(0)
    debut_precedent, fin_precedent = _bornes_mois(-1)
    requete = f"""SELECT COUNT(*) FROM {table}
                  WHERE {condition}
                    AND date({colonne_date}) >= ? AND date({colonne_date}) < ?"""
    courant = valeur(requete, (debut_courant, fin_courant))
    precedent = valeur(requete, (debut_precedent, fin_precedent))
    return calculer_pourcentage(courant, precedent)


def calculer_pourcentage(courant, precedent):
    courant = courant or 0
    precedent = precedent or 0
    if precedent == 0:
        return 100 if courant > 0 else 0
    return round(((courant - precedent) / precedent) * 100, 1)
