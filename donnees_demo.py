
import random
from datetime import date, datetime, timedelta
from backend import etablissement, modules
from backend.auth import creer_utilisateur
from backend.database import valeur,initialiser_base,connexion
from backend.roles import ROLE_PLATEFORME

ROLES = [
    "Gérant",
    "Caissier",
    "Gestionnaire de stock",
    "Serveur",
    "Serveur bar",
    "Serveur restaurant",
    ROLE_PLATEFORME,
]

ETABLISSEMENT = ("", "", "")


# Un second établissement, sans données, pour que la console plateforme montre
# ce qu'elle sait faire : deux maquis dans la même base, chacun chez soi.
ETABLISSEMENT_VOISIN = ("", "", "")

UTILISATEURS = [
    ("Konan Divix", "admin@divixmaquis.ci", "admin123", "Gérant"),
]

# Le compte de l'éditeur : aucun établissement, donc aucune donnée de service.
PLATEFORME = ("", "", "")

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
    ("Foutou sauce claire", "Plats & Sauces", 2000, 1100, 0, 0, 0),
    ("Kedjenou de poulet", "Plats & Sauces", 3000, 1700, 0, 0, 0),
    ("Attiéké", "Accompagnements", 500, 200, 0, 0, 0),
    ("Alloco", "Accompagnements", 1000, 400, 0, 0, 0),
    ("Bière Guinness 33cl", "Bières", 1500, 1000, 1, 48, 12),
    ("Bière Despé 33cl", "Bières", 2000, 1300, 1, 18, 12),
    ("Coca-Cola 50cl", "Sucreries", 700, 400, 1, 120, 24),
    ("Fanta Orange 50cl", "Sucreries", 700, 400, 1, 84, 24),
    ("Jus de bissap 1L", "Eaux & Jus", 1500, 700, 1, 0, 6),
    ("Jus de gingembre 1L", "Eaux & Jus", 1500, 700, 1, 14, 6),
]

TABLES = [
    ("", "", ),
    
]

DEPENSES = [
    ("", "", "", ""),
    
]

MODES = ["Espèces", "Espèces", "Espèces", "Orange Money", "MTN MoMo", "Wave"]
PRENOMS = [
   
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
        conn.commit()

    ets = etablissement.creer(*ETABLISSEMENT)["id_etablissement"]
    voisin = etablissement.creer(*ETABLISSEMENT_VOISIN)["id_etablissement"]
    etablissement.definir(ets)

    with connexion() as conn:
        conn.executemany(
            "INSERT INTO categories (id_etablissement, nom, type) VALUES (%s, %s, %s)",
            [(ets, *categorie) for categorie in CATEGORIES],
        )
        conn.executemany(
            """INSERT INTO tables_salle (id_etablissement, numero, zone, places)
               VALUES (%s, %s, %s, %s)""",
            [(ets, *table) for table in TABLES],
        )
        conn.commit()

    with connexion() as conn:
        roles_par_nom = {
            ligne["nom"]: ligne["id"]
            for ligne in conn.execute("SELECT id, nom FROM roles")
        }

    for nom, email, mot_de_passe, role in UTILISATEURS:
        creer_utilisateur(nom, email, mot_de_passe, roles_par_nom[role], ets)
    creer_utilisateur(*PLATEFORME, roles_par_nom[ROLE_PLATEFORME], None)
    creer_utilisateur(
        "Tantie Adjoua",
        "adjoua@divixmaquis.ci",
        "adjoua123",
        roles_par_nom["Gérant"],
        voisin,
    )

    with connexion() as conn:
        categories = {
            ligne["nom"]: ligne["id"]
            for ligne in conn.execute(
                "SELECT id, nom FROM categories WHERE id_etablissement = %s", (ets,)
            )
        }

        for index, (nom, categorie, prix, cout, gere_stock, stock, seuil) in enumerate(
            ARTICLES, start=1
        ):
            conn.execute(
                """INSERT INTO articles (id_etablissement, reference, nom, id_categorie,
                                         prix, cout_revient, gere_stock, stock,
                                         seuil_alerte, disponible, id_utilisateur)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1)""",
                (
                    ets,
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
                "SELECT id, prix, gere_stock FROM articles WHERE id_etablissement = %s",
                (ets,),
            ).fetchall()
        ]
        tables = [
            ligne["id"]
            for ligne in conn.execute(
                "SELECT id FROM tables_salle WHERE id_etablissement = %s", (ets,)
            ).fetchall()
        ]

        _generer_historique(conn, ets, articles, tables)
        _generer_mouvements(conn, ets)
        _generer_depenses(conn, ets)
        conn.commit()

    modules.invalider_cache()
    print("Base de démonstration créée.")
    print("Connexion : admin@divixmaquis.ci / admin123")
    print("Console plateforme : plateforme@divix.ci / plateforme123")


def _generer_historique(conn, ets, articles, tables, nb_jours=21):
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
            id_table = random.choice(tables)
            couverts = random.randint(1, 6)

            lignes = random.sample(articles, random.randint(2, 5))
            montant_total = 0
            id_commande = conn.execute(
                """INSERT INTO commandes (id_etablissement, reference, id_table,
                                          type_service, nom_client, couverts, statut,
                                          montant_total, id_utilisateur,
                                          date_commande, date_cloture)
                   VALUES (%s, %s, %s, 'Sur place', %s, %s, 'Payée', 0, %s, %s, %s)""",
                (
                    ets,
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
                """INSERT INTO paiements (id_etablissement, reference, id_commande,
                                          montant, mode, id_utilisateur, date_paiement)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    ets,
                    f"PAI-{numero_paiement:04d}",
                    id_commande,
                    montant_total,
                    random.choice(MODES),
                    random.randint(1, 2),
                    horodatage.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    # Quelques tickets encore ouverts pour que la salle ne soit pas vide.
    for index, id_table in enumerate([tables[1], tables[4], tables[10]], start=1):
        numero_commande += 1
        reference = f"CMD-{numero_commande:04d}"
        lignes = random.sample(articles, 3)
        montant_total = 0
        id_commande = conn.execute(
            """INSERT INTO commandes (id_etablissement, reference, id_table,
                                      type_service, nom_client, couverts, statut,
                                      montant_total, id_utilisateur)
               VALUES (%s, %s, %s, 'Sur place', %s, %s, %s, 0, 1)""",
            (
                ets,
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


def _generer_mouvements(conn, ets):
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
          AND c.id_etablissement = %s
        ORDER BY c.date_commande, l.id
        """,
        (ets,),
    ):
        ventes.setdefault(ligne["id_article"], []).append(ligne)

    articles = conn.execute(
        "SELECT id, stock FROM articles WHERE gere_stock = 1 AND id_etablissement = %s",
        (ets,),
    ).fetchall()

    debut = (date.today() - timedelta(days=22)).strftime("%Y-%m-%d 08:00:00")

    for article in articles:
        lignes_vendues = ventes.get(article["id"], [])
        total_vendu = sum(ligne["quantite"] for ligne in lignes_vendues)
        approvisionnement = article["stock"] + total_vendu

        conn.execute(
            """INSERT INTO mouvements_stock
               (id_etablissement, id_article, type_mouvement, quantite, stock_apres,
                motif, id_utilisateur, date_mouvement)
               VALUES (%s, %s, 'Entrée', %s, %s, 'Approvisionnement initial', 1, %s)""",
            (ets, article["id"], approvisionnement, approvisionnement, debut),
        )

        stock_courant = approvisionnement
        for ligne in lignes_vendues:
            stock_courant -= ligne["quantite"]
            conn.execute(
                """INSERT INTO mouvements_stock
                   (id_etablissement, id_article, type_mouvement, quantite,
                    stock_apres, motif, id_utilisateur, date_mouvement)
                   VALUES (%s, %s, 'Sortie', %s, %s, %s, 1, %s)""",
                (
                    ets,
                    article["id"],
                    ligne["quantite"],
                    stock_courant,
                    f"Commande {ligne['reference']}",
                    ligne["date_commande"],
                ),
            )


def _generer_depenses(conn, ets):
    for index, (libelle, categorie, montant, fournisseur) in enumerate(
        DEPENSES, start=1
    ):
        jour = date.today() - timedelta(days=random.randint(0, 20))
        conn.execute(
            """INSERT INTO depenses (id_etablissement, reference, libelle, categorie,
                                     montant, fournisseur, mode_paiement,
                                     id_utilisateur, date_depense)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)""",
            (
                ets,
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
