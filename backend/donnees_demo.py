"""Initialise la base et y injecte un jeu de données de démonstration.

Utilisation : python -m backend.donnees_demo
"""

import random
from datetime import date, datetime, timedelta

from backend.auth import creer_utilisateur
from backend.database import connexion, initialiser_base, valeur

ROLES = ["Gérant", "Caissier", "Serveur"]

UTILISATEURS = [
    ("Konan Divix", "admin@divixmaquis.ci", "admin123", 1),
    ("Awa Traoré", "caisse@divixmaquis.ci", "caisse123", 2),
    ("Yao Serge", "serveur@divixmaquis.ci", "serveur123", 3),
]

CATEGORIES = [
    ("Grillades", "Cuisine"),
    ("Plats & Sauces", "Cuisine"),
    ("Accompagnements", "Cuisine"),
    ("Bières", "Bar"),
    ("Sucreries", "Bar"),
    ("Eaux & Jus", "Bar"),
]

# (nom, catégorie, prix, coût de revient, gère un stock, stock, seuil)
ARTICLES = [
    ("Poulet braisé entier", "Grillades", 6000, 3500, 0, 0, 0),
    ("Demi-poulet braisé", "Grillades", 3500, 2000, 0, 0, 0),
    ("Poisson braisé (Bar)", "Grillades", 5000, 3000, 0, 0, 0),
    ("Brochettes de bœuf", "Grillades", 1500, 800, 0, 0, 0),
    ("Choukouya de mouton", "Grillades", 4000, 2400, 0, 0, 0),
    ("Garba", "Plats & Sauces", 1000, 500, 0, 0, 0),
    ("Riz sauce graine", "Plats & Sauces", 1500, 800, 0, 0, 0),
    ("Foutou sauce claire", "Plats & Sauces", 2000, 1100, 0, 0, 0),
    ("Kedjenou de poulet", "Plats & Sauces", 3000, 1700, 0, 0, 0),
    ("Attiéké", "Accompagnements", 500, 200, 0, 0, 0),
    ("Alloco", "Accompagnements", 1000, 400, 0, 0, 0),
    ("Frites", "Accompagnements", 1000, 450, 0, 0, 0),
    ("Bière Flag 66cl", "Bières", 1500, 900, 1, 96, 24),
    ("Bière Bock 66cl", "Bières", 1500, 900, 1, 72, 24),
    ("Bière Guinness 33cl", "Bières", 1500, 1000, 1, 48, 12),
    ("Bière Despé 33cl", "Bières", 2000, 1300, 1, 18, 12),
    ("Coca-Cola 50cl", "Sucreries", 700, 400, 1, 120, 24),
    ("Fanta Orange 50cl", "Sucreries", 700, 400, 1, 84, 24),
    ("Sprite 50cl", "Sucreries", 700, 400, 1, 8, 24),
    ("Eau minérale 1,5L", "Eaux & Jus", 500, 250, 1, 150, 30),
    ("Jus de bissap 1L", "Eaux & Jus", 1500, 700, 1, 0, 6),
    ("Jus de gingembre 1L", "Eaux & Jus", 1500, 700, 1, 14, 6),
]

TABLES = [
    ("1", "Salle", 4),
    ("2", "Salle", 4),
    ("3", "Salle", 6),
    ("4", "Salle", 2),
    ("5", "Terrasse", 6),
    ("6", "Terrasse", 6),
    ("7", "Terrasse", 4),
    ("8", "Terrasse", 8),
    ("9", "Bar", 2),
    ("10", "Bar", 2),
    ("11", "VIP", 8),
    ("12", "VIP", 10),
]

DEPENSES = [
    ("Achat casiers de bière", "Approvisionnement", 180000, "Brassivoire"),
    ("Achat poulets & poissons", "Approvisionnement", 95000, "Marché de Cocody"),
    ("Charbon de bois", "Approvisionnement", 15000, "Fournisseur local"),
    ("Salaire serveurs (quinzaine)", "Salaire", 120000, None),
    ("Loyer du mois", "Loyer", 150000, "Propriétaire"),
    ("Facture CIE", "Électricité & Eau", 48000, "CIE"),
    ("Facture SODECI", "Électricité & Eau", 22000, "SODECI"),
    ("Transport marché", "Transport", 8000, None),
    ("Réparation congélateur", "Entretien", 35000, "Atelier Kouassi"),
]

MODES = ["Espèces", "Espèces", "Espèces", "Orange Money", "MTN MoMo", "Wave"]
PRENOMS = [
    "Client comptoir",
    "M. Kouassi",
    "Mme Aya",
    "Patron Diallo",
    "Tante Adjoua",
    "Frère Ismaël",
    "Sœur Mariam",
    "M. Bamba",
]


def base_deja_remplie():
    return valeur("SELECT COUNT(*) FROM utilisateurs") > 0


def peupler():
    initialiser_base()

    if base_deja_remplie():
        print("La base contient déjà des données — rien à faire.")
        return

    with connexion() as conn:
        conn.executemany("INSERT INTO roles (nom) VALUES (%s)", [(r,) for r in ROLES])
        conn.executemany(
            "INSERT INTO categories (nom, type) VALUES (%s, %s)", CATEGORIES
        )
        conn.executemany(
            "INSERT INTO tables_salle (numero, zone, places) VALUES (%s, %s, %s)",
            TABLES,
        )
        conn.commit()

    for nom, email, mot_de_passe, id_role in UTILISATEURS:
        creer_utilisateur(nom, email, mot_de_passe, id_role)

    with connexion() as conn:
        categories = {
            ligne["nom"]: ligne["id"]
            for ligne in conn.execute("SELECT id, nom FROM categories")
        }

        for index, (nom, categorie, prix, cout, gere_stock, stock, seuil) in enumerate(
            ARTICLES, start=1
        ):
            conn.execute(
                """INSERT INTO articles (reference, nom, id_categorie, prix, cout_revient,
                                         gere_stock, stock, seuil_alerte, disponible,
                                         id_utilisateur)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 1)""",
                (
                    f"ART-{index:04d}",
                    nom,
                    categories[categorie],
                    prix,
                    cout,
                    gere_stock,
                    stock,
                    seuil,
                ),
            )
        conn.commit()

        articles = [
            dict(ligne)
            for ligne in conn.execute(
                "SELECT id, prix, gere_stock FROM articles"
            ).fetchall()
        ]

        _generer_historique(conn, articles)
        _generer_mouvements(conn)
        _generer_depenses(conn)
        conn.commit()

    print("Base de démonstration créée.")
    print("Connexion : admin@divixmaquis.ci / admin123")


def _generer_historique(conn, articles, nb_jours=21):
    """Crée des commandes et encaissements réalistes sur les trois dernières semaines."""
    random.seed(42)
    numero_commande = 0
    numero_paiement = 0

    for decalage in range(nb_jours, -1, -1):
        jour = date.today() - timedelta(days=decalage)
        # Le maquis tourne davantage le week-end.
        nb_commandes = random.randint(8, 16) if jour.weekday() >= 4 else random.randint(4, 10)

        for _ in range(nb_commandes):
            numero_commande += 1
            reference = f"CMD-{numero_commande:04d}"
            heure = random.randint(11, 23)
            horodatage = datetime.combine(jour, datetime.min.time()).replace(
                hour=heure, minute=random.randint(0, 59)
            )
            id_table = random.randint(1, len(TABLES))
            couverts = random.randint(1, 6)

            lignes = random.sample(articles, random.randint(2, 5))
            montant_total = 0
            id_commande = conn.execute(
                """INSERT INTO commandes (reference, id_table, type_service, nom_client,
                                          couverts, statut, montant_total, id_utilisateur,
                                          date_commande, date_cloture)
                   VALUES (%s, %s, 'Sur place', %s, %s, 'Payée', 0, %s, %s, %s)""",
                (
                    reference,
                    id_table,
                    random.choice(PRENOMS),
                    couverts,
                    random.randint(1, 3),
                    horodatage.strftime("%Y-%m-%d %H:%M:%S"),
                    horodatage.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            ).lastrowid

            for article in lignes:
                quantite = random.randint(1, 4)
                total = article["prix"] * quantite
                montant_total += total
                conn.execute(
                    """INSERT INTO lignes_commande
                       (id_commande, id_article, quantite, prix_unitaire, total)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (id_commande, article["id"], quantite, article["prix"], total),
                )

            conn.execute(
                "UPDATE commandes SET montant_total = %s WHERE id = %s",
                (montant_total, id_commande),
            )

            numero_paiement += 1
            conn.execute(
                """INSERT INTO paiements (reference, id_commande, montant, mode,
                                          id_utilisateur, date_paiement)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    f"PAI-{numero_paiement:04d}",
                    id_commande,
                    montant_total,
                    random.choice(MODES),
                    random.randint(1, 2),
                    horodatage.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    # Quelques tickets encore ouverts pour que la salle ne soit pas vide.
    for index, id_table in enumerate([2, 5, 11], start=1):
        numero_commande += 1
        reference = f"CMD-{numero_commande:04d}"
        lignes = random.sample(articles, 3)
        montant_total = 0
        id_commande = conn.execute(
            """INSERT INTO commandes (reference, id_table, type_service, nom_client,
                                      couverts, statut, montant_total, id_utilisateur)
               VALUES (%s, %s, 'Sur place', %s, %s, %s, 0, 1)""",
            (
                reference,
                id_table,
                random.choice(PRENOMS),
                random.randint(2, 6),
                "En cours" if index < 3 else "Servie",
            ),
        ).lastrowid

        for article in lignes:
            quantite = random.randint(1, 3)
            total = article["prix"] * quantite
            montant_total += total
            conn.execute(
                """INSERT INTO lignes_commande
                   (id_commande, id_article, quantite, prix_unitaire, total)
                   VALUES (%s, %s, %s, %s, %s)""",
                (id_commande, article["id"], quantite, article["prix"], total),
            )

        conn.execute(
            "UPDATE commandes SET montant_total = %s WHERE id = %s",
            (montant_total, id_commande),
        )
        conn.execute(
            "UPDATE tables_salle SET statut = 'Occupée' WHERE id = %s", (id_table,)
        )


def _generer_mouvements(conn):
    """Rejoue les ventes de boissons pour reconstituer un journal de stock cohérent.

    Le stock déclaré dans ARTICLES est le stock *final* voulu : on remonte donc à
    l'approvisionnement de départ en y ajoutant tout ce qui a été vendu depuis.
    """
    ventes = {}
    for ligne in conn.execute(
        """
        SELECT l.id_article, l.quantite, c.date_commande, c.reference
        FROM lignes_commande l
        JOIN commandes c ON l.id_commande = c.id
        JOIN articles a ON a.id = l.id_article
        WHERE a.gere_stock = 1 AND c.statut != 'Annulée'
        ORDER BY c.date_commande, l.id
        """
    ):
        ventes.setdefault(ligne["id_article"], []).append(ligne)

    articles = conn.execute(
        "SELECT id, stock FROM articles WHERE gere_stock = 1"
    ).fetchall()

    debut = (date.today() - timedelta(days=22)).strftime("%Y-%m-%d 08:00:00")

    for article in articles:
        lignes_vendues = ventes.get(article["id"], [])
        total_vendu = sum(ligne["quantite"] for ligne in lignes_vendues)
        approvisionnement = article["stock"] + total_vendu

        conn.execute(
            """INSERT INTO mouvements_stock
               (id_article, type_mouvement, quantite, stock_apres, motif,
                id_utilisateur, date_mouvement)
               VALUES (%s, 'Entrée', %s, %s, 'Approvisionnement initial', 1, %s)""",
            (article["id"], approvisionnement, approvisionnement, debut),
        )

        stock_courant = approvisionnement
        for ligne in lignes_vendues:
            stock_courant -= ligne["quantite"]
            conn.execute(
                """INSERT INTO mouvements_stock
                   (id_article, type_mouvement, quantite, stock_apres, motif,
                    id_utilisateur, date_mouvement)
                   VALUES (%s, 'Sortie', %s, %s, %s, 1, %s)""",
                (
                    article["id"],
                    ligne["quantite"],
                    stock_courant,
                    f"Commande {ligne['reference']}",
                    ligne["date_commande"],
                ),
            )


def _generer_depenses(conn):
    for index, (libelle, categorie, montant, fournisseur) in enumerate(
        DEPENSES, start=1
    ):
        jour = date.today() - timedelta(days=random.randint(0, 20))
        conn.execute(
            """INSERT INTO depenses (reference, libelle, categorie, montant, fournisseur,
                                     mode_paiement, id_utilisateur, date_depense)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s)""",
            (
                f"DEP-{index:04d}",
                libelle,
                categorie,
                montant,
                fournisseur,
                random.choice(MODES),
                jour.isoformat(),
            ),
        )


if __name__ == "__main__":
    peupler()
