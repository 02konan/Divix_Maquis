import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_TEST = "divix_maquis_test"


MODULES_APPLICATIFS = ("app", "donnees_demo")


def _decharger_modules():
    """Force la relecture de la configuration MySQL au prochain import.

    `donnees_demo` doit en faire partie : sinon il garde une référence vers un
    ancien module `backend.database`, dont la connexion pointe sur une base que
    le test précédent a supprimée.
    """
    for module in list(sys.modules):
        if module in MODULES_APPLICATIFS or module.startswith("backend"):
            del sys.modules[module]


def _supprimer_base():
    import pymysql

    from backend.database import nom_base, parametres_connexion

    conn = pymysql.connect(**parametres_connexion(avec_base=False))
    try:
        with conn.cursor() as curseur:
            curseur.execute(f"DROP DATABASE IF EXISTS `{nom_base()}`")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def app_maquis():
    """Application branchée sur une base MySQL de test remplie de données."""
    os.environ["DATABASE"] = BASE_TEST
    _decharger_modules()

    import pymysql

    from backend.database import parametres_connexion

    try:
        pymysql.connect(**parametres_connexion(avec_base=False)).close()
    except pymysql.MySQLError as erreur:
        pytest.skip(f"Serveur MySQL indisponible : {erreur}")

    _supprimer_base()

    from donnees_demo import peupler

    peupler()

    from app import app

    app.config.update(TESTING=True, SECRET_KEY="test")
    yield app

    from backend.database import fermer_connexion

    fermer_connexion()
    _supprimer_base()
    os.environ.pop("DATABASE", None)


@pytest.fixture()
def client(app_maquis):
    return app_maquis.test_client()


@pytest.fixture()
def client_connecte(client):
    reponse = client.post(
        "/login",
        data={"email": "admin@divixmaquis.ci", "password": "admin123"},
    )
    assert reponse.get_json()["success"] is True
    return client


def test_page_publique_redirige_vers_login(client):
    reponse = client.get("/")
    assert reponse.status_code == 302
    assert "/login" in reponse.headers["Location"]


def test_login_refuse_mauvais_mot_de_passe(client):
    reponse = client.post(
        "/login", data={"email": "admin@divixmaquis.ci", "password": "mauvais"}
    )
    assert reponse.status_code == 401
    assert reponse.get_json()["success"] is False


@pytest.mark.parametrize(
    "url",
    ["/", "/salle", "/commande", "/menu", "/stock", "/caisse", "/depense"],
)
def test_pages_accessibles_une_fois_connecte(client_connecte, url):
    assert client_connecte.get(url).status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "/dashboard/data",
        "/salle/list",
        "/menu/list",
        "/stock/list",
        "/commande/list",
        "/caisse/list",
        "/depense/list",
    ],
)
def test_endpoints_json(client_connecte, url):
    reponse = client_connecte.get(url)
    assert reponse.status_code == 200
    assert reponse.get_json() is not None


def test_creation_commande_decremente_le_stock(client_connecte):
    articles = client_connecte.get("/menu/disponibles").get_json()["data"]
    boisson = next(article for article in articles if article["gere_stock"])
    stock_avant = boisson["stock"]

    reponse = client_connecte.post(
        "/commande/add",
        data={
            "id_table": "1",
            "type_service": "Sur place",
            "nom_client": "Client test",
            "couverts": "2",
            "articles": f'[{{"id_article": {boisson["id"]}, "quantite": 2}}]',
        },
    )
    resultat = reponse.get_json()
    assert resultat["success"] is True
    assert resultat["montant_total"] == boisson["prix"] * 2

    apres = client_connecte.get("/maquis/list").get_json()["data"]
    stock_apres = next(a["stock"] for a in apres if a["id"] == boisson["id"])
    assert stock_apres == stock_avant - 2


def test_commande_refusee_si_stock_insuffisant(client_connecte):
    articles = client_connecte.get("/menu/disponibles").get_json()["data"]
    boisson = next(article for article in articles if article["gere_stock"])

    reponse = client_connecte.post(
        "/commande/add",
        data={
            "type_service": "Sur place",
            "articles": f'[{{"id_article": {boisson["id"]}, "quantite": {boisson["stock"] + 50}}}]',
        },
    )
    assert reponse.status_code == 400
    assert "Stock insuffisant" in reponse.get_json()["error"]


def test_prix_ignore_la_valeur_envoyee_par_le_client(client_connecte):
    """Le montant vient toujours de la base, jamais du formulaire."""
    articles = client_connecte.get("/menu/disponibles").get_json()["data"]
    article = articles[0]

    reponse = client_connecte.post(
        "/commande/add",
        data={
            "type_service": "À emporter",
            "articles": f'[{{"id_article": {article["id"]}, "quantite": 1, "prix_unitaire": 1}}]',
        },
    )
    assert reponse.get_json()["montant_total"] == article["prix"]


def test_encaissement_solde_la_commande(client_connecte):
    articles = client_connecte.get("/menu/disponibles").get_json()["data"]
    article = articles[0]

    creation = client_connecte.post(
        "/commande/add",
        data={
            "id_table": "3",
            "type_service": "Sur place",
            "articles": f'[{{"id_article": {article["id"]}, "quantite": 1}}]',
        },
    ).get_json()
    reference = creation["reference"]
    montant = creation["montant_total"]

    partiel = client_connecte.post(
        "/caisse/add",
        data={"reference": reference, "montant": montant / 2, "mode": "Espèces"},
    ).get_json()
    assert partiel["success"] is True
    assert partiel["reste_a_payer"] == montant / 2

    solde = client_connecte.post(
        "/caisse/add",
        data={"reference": reference, "montant": montant / 2, "mode": "Wave"},
    ).get_json()
    assert solde["reste_a_payer"] == 0

    detail = client_connecte.get(f"/commande/{reference}").get_json()["data"]
    assert detail["statut"] == "Payée"

    # La table est libérée dès que le ticket est soldé.
    tables = client_connecte.get("/salle/list").get_json()["data"]
    assert next(t["statut"] for t in tables if t["numero"] == "3") == "Libre"


def test_encaissement_refuse_un_montant_superieur_au_reste(client_connecte):
    articles = client_connecte.get("/menu/disponibles").get_json()["data"]
    creation = client_connecte.post(
        "/commande/add",
        data={
            "type_service": "Sur place",
            "articles": f'[{{"id_article": {articles[0]["id"]}, "quantite": 1}}]',
        },
    ).get_json()

    reponse = client_connecte.post(
        "/caisse/add",
        data={
            "reference": creation["reference"],
            "montant": creation["montant_total"] + 1000,
            "mode": "Espèces",
        },
    )
    assert reponse.status_code == 400
    assert "supérieur au reste" in reponse.get_json()["error"]


def test_mouvement_de_stock_entree(client_connecte):
    stock = client_connecte.get("/stock/list").get_json()["data"]
    article = stock[0]

    reponse = client_connecte.post(
        "/stock/mouvement",
        data={
            "id_article": article["id"],
            "type_mouvement": "Entrée",
            "quantite": 24,
            "motif": "Livraison test",
        },
    ).get_json()

    assert reponse["success"] is True
    assert reponse["stock_apres"] == article["stock"] + 24


def test_ajout_depense(client_connecte):
    reponse = client_connecte.post(
        "/depense/add",
        data={
            "libelle": "Achat charbon",
            "categorie": "Approvisionnement",
            "montant": "12000",
        },
    ).get_json()
    assert reponse["success"] is True

    depenses = client_connecte.get("/depense/list").get_json()["data"]
    assert any(d["libelle"] == "Achat charbon" for d in depenses)


def _en_parallele(action, nb_fils):
    """Lance `action` dans plusieurs fils libérés au même instant."""
    import threading

    resultats = []
    verrou = threading.Lock()
    depart = threading.Barrier(nb_fils)

    def executer_action():
        depart.wait()
        resultat = action()
        with verrou:
            resultats.append(resultat)

    fils = [threading.Thread(target=executer_action) for _ in range(nb_fils)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()
    return resultats


def test_references_uniques_en_simultane(app_maquis):
    """Deux commandes prises au même instant ne peuvent pas porter la même référence."""
    from backend.database import generer_reference

    references = _en_parallele(lambda: generer_reference("CMD", "commandes"), 20)

    assert len(references) == 20
    assert len(set(references)) == 20


def test_stock_sans_mise_a_jour_perdue(app_maquis):
    """Des mouvements de stock simultanés s'additionnent tous, aucun n'est écrasé."""
    from backend import ecritures
    from backend.database import valeur

    id_article = 13
    avant = valeur("SELECT stock FROM articles WHERE id = %s", (id_article,))

    resultats = _en_parallele(
        lambda: ecritures.enregistrer_mouvement(id_article, "Entrée", 1, "test", 1), 20
    )

    assert all(resultat["success"] for resultat in resultats)
    assert valeur("SELECT stock FROM articles WHERE id = %s", (id_article,)) == avant + 20
    assert valeur("SELECT COUNT(*) FROM mouvements_stock WHERE motif = 'test'") == 20


def test_ajout_article_au_menu(client_connecte):
    reponse = client_connecte.post(
        "/menu/add",
        data={
            "nom": "Poisson braisé test",
            "categorie": "1",
            "prix": "5000",
            "gere_stock": "0",
        },
    ).get_json()
    assert reponse["success"] is True

    menu = client_connecte.get("/menu/list").get_json()["data"]
    assert any(a["nom"] == "Poisson braisé test" for a in menu)


# ----------------------------------------------------------------------------
# DROITS PAR RÔLE
# ----------------------------------------------------------------------------

COMPTES = {
    "Gérant": ("admin@divixmaquis.ci", "admin123"),
    "Caissier": ("caisse@divixmaquis.ci", "caisse123"),
    "Serveur": ("serveur@divixmaquis.ci", "serveur123"),
    "Serveur bar": ("bar@divixmaquis.ci", "bar123"),
    "Serveur restaurant": ("resto@divixmaquis.ci", "resto123"),
}


def _connecte_en(app_maquis, role):
    client = app_maquis.test_client()
    email, mot_de_passe = COMPTES[role]
    reponse = client.post("/login", data={"email": email, "password": mot_de_passe})
    assert reponse.get_json()["success"] is True
    return client


@pytest.mark.parametrize(
    "role, autorisees, interdites",
    [
        ("Gérant", ["/", "/salle", "/commande", "/menu", "/stock", "/caisse", "/depense"], []),
        ("Caissier", ["/salle", "/commande", "/caisse"], ["/", "/menu", "/stock", "/depense"]),
        ("Serveur", ["/salle", "/commande", "/menu"], ["/", "/stock", "/caisse", "/depense"]),
    ],
)
def test_pages_visibles_selon_le_role(app_maquis, role, autorisees, interdites):
    client = _connecte_en(app_maquis, role)
    for url in autorisees:
        assert client.get(url).status_code == 200, url
    for url in interdites:
        # Une page interdite renvoie sur la page d'accueil du rôle.
        assert client.get(url).status_code == 302, url


@pytest.mark.parametrize(
    "role, url",
    [
        ("Caissier", "/dashboard/data"),
        ("Caissier", "/stock/list"),
        ("Caissier", "/depense/list"),
        ("Serveur", "/caisse/list"),
        ("Serveur", "/caisse/encaissables"),
        ("Serveur", "/dashboard/data"),
    ],
)
def test_donnees_interdites_repondent_403(app_maquis, role, url):
    """Masquer une page ne suffit pas : ses endpoints JSON doivent refuser aussi."""
    reponse = _connecte_en(app_maquis, role).get(url)
    assert reponse.status_code == 403
    assert reponse.get_json()["success"] is False


def test_serveur_consulte_le_menu_sans_le_modifier(app_maquis):
    client = _connecte_en(app_maquis, "Serveur")
    assert client.get("/menu/list").status_code == 200

    refus = client.post(
        "/menu/add", data={"nom": "X", "categorie": "1", "prix": "500", "gere_stock": "0"}
    )
    assert refus.status_code == 403
    assert client.post("/menu/categorie/add", data={"nom": "Y"}).status_code == 403
    assert client.post("/menu/1/disponibilite", data={"disponible": "0"}).status_code == 403


def test_serveur_prend_une_commande(app_maquis):
    """Le sélecteur d'articles reste accessible : sans lui, pas de prise de commande."""
    client = _connecte_en(app_maquis, "Serveur")
    articles = client.get("/menu/disponibles").get_json()["data"]

    resultat = client.post(
        "/commande/add",
        data={
            "type_service": "Sur place",
            "articles": f'[{{"id_article": {articles[0]["id"]}, "quantite": 1}}]',
        },
    ).get_json()
    assert resultat["success"] is True


def test_caissier_encaisse_mais_ne_touche_pas_aux_depenses(app_maquis):
    client = _connecte_en(app_maquis, "Caissier")
    assert client.get("/caisse/encaissables").status_code == 200

    refus = client.post(
        "/depense/add",
        data={"libelle": "Achat", "categorie": "Divers", "montant": "1000"},
    )
    assert refus.status_code == 403


def test_menu_affiche_ne_contient_que_les_pages_autorisees(app_maquis):
    from backend import roles

    for role, pages in roles.PAGES_PAR_ROLE.items():
        client = _connecte_en(app_maquis, role)
        html = client.get(roles.page_accueil(role)).get_data(as_text=True)
        for page in roles.PAGES:
            lien = f'href="{page["url"]}"'
            if page["cle"] in pages:
                assert lien in html, (role, page["cle"])


def test_tout_endpoint_est_classe(app_maquis):
    """Un endpoint oublié serait inaccessible : la classification doit être complète."""
    from backend import roles

    connus = (
        set(roles.PAGE_PAR_ENDPOINT)
        | roles.ENDPOINTS_PUBLICS
        | roles.ENDPOINTS_TOUJOURS_AUTORISES
    )
    declares = {regle.endpoint for regle in app_maquis.url_map.iter_rules()}
    assert declares - connus == set()


def test_role_inconnu_n_a_acces_a_rien(app_maquis):
    from backend import roles

    assert roles.pages_autorisees("Plongeur") == set()
    assert roles.acces_autorise("Plongeur", "dashboard") is False
    assert roles.acces_autorise("Plongeur", "logout") is True


# ----------------------------------------------------------------------------
# FONCTIONNALITÉS ACTIVABLES
# ----------------------------------------------------------------------------


def _desactiver(client, cle):
    reponse = client.post(
        "/administration/modules", data={"cle": cle, "actif": "0"}
    ).get_json()
    assert reponse["success"] is True
    return reponse


def test_administration_reservee_au_gerant(app_maquis):
    assert _connecte_en(app_maquis, "Gérant").get("/administration").status_code == 200

    for role in ("Caissier", "Serveur"):
        client = _connecte_en(app_maquis, role)
        assert client.get("/administration").status_code == 302
        refus = client.post(
            "/administration/modules", data={"cle": "salle", "actif": "0"}
        )
        assert refus.status_code == 403


def test_salle_desactivee_ferme_pages_et_donnees(app_maquis):
    client = _connecte_en(app_maquis, "Gérant")
    _desactiver(client, "salle")

    assert client.get("/salle").status_code == 302
    refus = client.get("/salle/list")
    assert refus.status_code == 403
    assert refus.get_json()["error"] == "Fonctionnalité désactivée"
    assert client.post("/salle/add", data={"numero": "99"}).status_code == 403

    # Elle disparaît du menu, y compris pour les autres utilisateurs.
    for role in ("Gérant", "Serveur"):
        html = _connecte_en(app_maquis, role).get("/commande").get_data(as_text=True)
        assert 'href="/salle"' not in html


def test_salle_desactivee_retire_le_choix_de_table(app_maquis):
    client = _connecte_en(app_maquis, "Gérant")
    assert 'id="idTable"' in client.get("/commande").get_data(as_text=True)

    _desactiver(client, "salle")
    assert 'id="idTable"' not in client.get("/commande").get_data(as_text=True)


def test_salle_desactivee_ignore_la_table_envoyee(app_maquis):
    """Un formulaire forgé ne doit pas rattacher une commande à une table."""
    client = _connecte_en(app_maquis, "Gérant")
    _desactiver(client, "salle")

    article = client.get("/menu/disponibles").get_json()["data"][0]
    creation = client.post(
        "/commande/add",
        data={
            "type_service": "À emporter",
            "id_table": "2",
            "articles": f'[{{"id_article": {article["id"]}, "quantite": 1}}]',
        },
    ).get_json()
    assert creation["success"] is True

    detail = client.get(f"/commande/{creation['reference']}").get_json()["data"]
    assert detail["id_table"] is None


def test_module_indispensable_reste_actif(app_maquis):
    from backend import modules

    client = _connecte_en(app_maquis, "Gérant")
    for cle in modules.OBLIGATOIRES:
        refus = client.post(
            "/administration/modules", data={"cle": cle, "actif": "0"}
        )
        assert refus.status_code == 400
        assert "ne peut pas être désactivé" in refus.get_json()["error"]
        assert client.get("/caisse").status_code == 200


def test_module_inconnu_refuse(app_maquis):
    refus = _connecte_en(app_maquis, "Gérant").post(
        "/administration/modules", data={"cle": "karaoke", "actif": "1"}
    )
    assert refus.status_code == 400


def test_reactivation_reouvre_la_fonctionnalite(app_maquis):
    client = _connecte_en(app_maquis, "Gérant")
    _desactiver(client, "stock")
    assert client.get("/stock/list").status_code == 403

    client.post("/administration/modules", data={"cle": "stock", "actif": "1"})
    assert client.get("/stock/list").status_code == 200
    assert 'href="/stock"' in client.get("/stock").get_data(as_text=True)


def test_module_absent_de_la_base_garde_sa_valeur_par_defaut(app_maquis):
    """Une fonctionnalité ajoutée plus tard fonctionne avant sa création en base."""
    from backend import modules
    from backend.database import executer

    executer("DELETE FROM modules WHERE cle = %s", ("depense",))
    modules.invalider_cache()
    assert modules.actif("depense") is True

    modules.initialiser()
    assert modules.actif("depense") is True


def test_carte_affichee_en_cartes_plats(app_maquis):
    """La carte s'affiche en grille de cartes, filtrable par catégorie."""
    html = _connecte_en(app_maquis, "Gérant").get("/menu").get_data(as_text=True)

    assert 'id="grille-menu"' in html
    assert 'class="chip-categorie' in html
    assert 'data-categorie="Grillades"' in html
    assert 'id="tbody-menu"' not in html


def test_boutons_de_creation_caches_pour_la_lecture_seule(app_maquis):
    gerant = _connecte_en(app_maquis, "Gérant").get("/menu").get_data(as_text=True)
    assert 'data-bs-target="#articleModal"' in gerant
    assert 'data-modifiable="1"' in gerant

    serveur = _connecte_en(app_maquis, "Serveur").get("/menu").get_data(as_text=True)
    assert 'data-bs-target="#articleModal"' not in serveur
    assert 'data-bs-target="#categorieModal"' not in serveur
    assert 'data-modifiable="0"' in serveur


# ----------------------------------------------------------------------------
# PAGINATION ET ACTIONS DES CARTES
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, barre",
    [
        ("/commande", "pagination-commandes"),
        ("/caisse", "pagination-caisse"),
        ("/depense", "pagination-depenses"),
        ("/stock", "pagination-stock"),
        ("/stock", "pagination-mouvements"),
        ("/menu", "pagination-menu"),
    ],
)
def test_barre_de_pagination_presente(client_connecte, url, barre):
    assert f'id="{barre}"' in client_connecte.get(url).get_data(as_text=True)


def test_action_des_cartes_selon_le_role(app_maquis):
    """Le gérant gère la carte, le serveur commande depuis la carte."""
    gerant = _connecte_en(app_maquis, "Gérant").get("/menu").get_data(as_text=True)
    assert 'data-modifiable="1"' in gerant
    assert 'id="barre-panier"' not in gerant

    serveur = _connecte_en(app_maquis, "Serveur").get("/menu").get_data(as_text=True)
    assert 'data-modifiable="0"' in serveur
    assert 'data-commandable="1"' in serveur
    assert 'id="barre-panier"' in serveur


def test_montants_en_decimal_ou_en_double(app_maquis):
    """Les écritures doivent tenir quel que soit le type des colonnes monétaires.

    Une base créée hors de l'application (reprise, import) peut typer les
    montants en DOUBLE là où le schéma pose du DECIMAL. Mélanger les deux dans
    un calcul lève `unsupported operand type(s) for -`.
    """
    from backend.database import executer

    for table, colonne in [
        ("articles", "prix"),
        ("commandes", "montant_total"),
        ("paiements", "montant"),
    ]:
        executer(f"ALTER TABLE {table} MODIFY {colonne} DOUBLE NOT NULL DEFAULT 0")

    client = _connecte_en(app_maquis, "Gérant")
    article = client.get("/menu/disponibles").get_json()["data"][0]

    creation = client.post(
        "/commande/add",
        data={
            "type_service": "Sur place",
            "remise": "500",
            "articles": f'[{{"id_article": {article["id"]}, "quantite": 2}}]',
        },
    ).get_json()
    assert creation["success"] is True, creation
    assert creation["montant_total"] == article["prix"] * 2 - 500

    partiel = client.post(
        "/caisse/add",
        data={"reference": creation["reference"], "montant": 500, "mode": "Espèces"},
    ).get_json()
    assert partiel["success"] is True, partiel
    assert partiel["reste_a_payer"] == creation["montant_total"] - 500

    solde = client.post(
        "/caisse/add",
        data={
            "reference": creation["reference"],
            "montant": creation["montant_total"] - 500,
            "mode": "Wave",
        },
    ).get_json()
    assert solde["reste_a_payer"] == 0

    detail = client.get(f"/commande/{creation['reference']}").get_json()["data"]
    assert detail["statut"] == "Payée"


def test_conversion_des_types_mysql():
    """Decimal et dates sont ramenés aux types que manipule le reste du code."""
    from decimal import Decimal

    from backend.database import _convertir

    assert _convertir(Decimal("3000.00")) == 3000
    assert isinstance(_convertir(Decimal("3000.00")), int)
    assert _convertir(Decimal("1500.50")) == 1500.5
    assert isinstance(_convertir(Decimal("1500.50")), float)
    assert _convertir(None) is None


def test_categorie_disparue_le_dit_clairement(app_maquis):
    """Un message générique obligeait à deviner quelle référence manquait."""
    refus = _connecte_en(app_maquis, "Gérant").post(
        "/menu/add",
        data={"nom": "Plat", "categorie": "9999", "prix": "1000", "gere_stock": "0"},
    ).get_json()

    assert refus["success"] is False
    assert "catégorie" in refus["error"]


def test_session_pointant_un_utilisateur_disparu(app_maquis):
    """Une base recréée laisse des sessions périmées : elles doivent se fermer."""
    client = _connecte_en(app_maquis, "Gérant")
    with client.session_transaction() as session:
        session["user_id"] = 4242
        session["verifie_le"] = 0

    refus = client.post(
        "/menu/add",
        data={"nom": "Plat", "categorie": "1", "prix": "1000", "gere_stock": "0"},
    )
    assert refus.status_code == 403
    assert "Session expirée" in refus.get_json()["error"]

    # La session est vidée : la page suivante renvoie à la connexion.
    reponse = client.get("/menu")
    assert reponse.status_code == 302
    assert "/login" in reponse.headers["Location"]


def test_messages_des_contraintes_de_base():
    """Chaque clé étrangère nomme ce qui manque, sans exposer le SQL."""
    from pymysql.err import IntegrityError

    from backend.database import message_erreur

    doublon = IntegrityError(1062, "Duplicate entry 'Grillades' for key 'nom'")
    assert message_erreur(doublon) == "« Grillades » existe déjà."

    for colonne, extrait in [
        ("id_categorie", "catégorie"),
        ("id_utilisateur", "session"),
        ("id_article", "article"),
    ]:
        erreur = IntegrityError(
            1452,
            "Cannot add or update a child row: a foreign key constraint fails "
            f"(`base`.`articles`, CONSTRAINT `fk` FOREIGN KEY (`{colonne}`) "
            "REFERENCES `autre` (`id`))",
        )
        assert extrait in message_erreur(erreur).lower()


# ----------------------------------------------------------------------------
# SERVEURS DU BAR ET DU RESTAURANT
# ----------------------------------------------------------------------------


def _premier_article(client):
    return client.get("/menu/disponibles").get_json()["data"][0]


def _ouvrir_ticket(client, article, id_table="5"):
    return client.post(
        "/commande/add",
        data={
            "id_table": id_table,
            "type_service": "Sur place",
            "articles": f'[{{"id_article": {article["id"]}, "quantite": 1}}]',
        },
    ).get_json()


@pytest.mark.parametrize(
    "role, page, type_attendu, page_interdite",
    [
        ("Serveur bar", "maquis", "Bar", "menu"),
        ("Serveur restaurant", "menu", "Cuisine", "maquis"),
    ],
)
def test_chaque_serveur_ne_voit_que_sa_carte(
    app_maquis, role, page, type_attendu, page_interdite
):
    client = _connecte_en(app_maquis, role)

    carte = client.get(f"/{page}/list").get_json()
    types = {article["type_categorie"] for article in carte["data"]}
    assert types == {type_attendu}
    assert carte["counter"]["total_articles"] == len(carte["data"])

    # L'autre carte lui est fermée, page comme données.
    assert client.get(f"/{page_interdite}").status_code == 302
    assert client.get(f"/{page_interdite}/list").status_code == 403

    # Le sélecteur de la prise de commande suit le même partage.
    proposables = client.get("/menu/disponibles").get_json()["data"]
    assert proposables
    categories_de_la_carte = {article["categorie"] for article in carte["data"]}
    assert {article["categorie"] for article in proposables} <= categories_de_la_carte


def test_commande_hors_domaine_refusee(app_maquis):
    """Le contrôle est côté serveur : un formulaire forgé ne doit pas passer."""
    bar = _connecte_en(app_maquis, "Serveur bar")
    plat = _premier_article(_connecte_en(app_maquis, "Serveur restaurant"))

    refus = bar.post(
        "/commande/add",
        data={
            "type_service": "Sur place",
            "articles": f'[{{"id_article": {plat["id"]}, "quantite": 1}}]',
        },
    )
    assert refus.status_code == 400
    assert "ne fait pas partie de votre carte" in refus.get_json()["error"]


def test_tickets_separes_entre_bar_et_restaurant(app_maquis):
    """Une même table porte deux tickets, chacun cloisonné à son serveur."""
    bar = _connecte_en(app_maquis, "Serveur bar")
    resto = _connecte_en(app_maquis, "Serveur restaurant")

    ticket_bar = _ouvrir_ticket(bar, _premier_article(bar))
    ticket_resto = _ouvrir_ticket(resto, _premier_article(resto))
    assert ticket_bar["success"] and ticket_resto["success"]
    assert ticket_bar["reference"] != ticket_resto["reference"]

    # Chacun consulte le sien et pas celui de l'autre.
    assert bar.get(f"/commande/{ticket_bar['reference']}").status_code == 200
    assert bar.get(f"/commande/{ticket_resto['reference']}").status_code == 404
    assert resto.get(f"/commande/{ticket_bar['reference']}").status_code == 404

    refus = bar.post(
        f"/commande/{ticket_resto['reference']}/statut", data={"statut": "Servie"}
    )
    assert refus.status_code == 400
    assert "pas le vôtre" in refus.get_json()["error"]

    # La caisse, elle, encaisse les deux.
    caisse = _connecte_en(app_maquis, "Caissier")
    encaissables = {
        commande["reference"]
        for commande in caisse.get("/caisse/encaissables").get_json()["data"]
    }
    assert {ticket_bar["reference"], ticket_resto["reference"]} <= encaissables


# ----------------------------------------------------------------------------
# GESTION DES COMPTES
# ----------------------------------------------------------------------------


def test_roles_declares_presents_en_base(app_maquis):
    """Une base déjà en service doit recevoir les rôles ajoutés depuis."""
    from backend import lectures, roles

    en_base = {role["nom"] for role in lectures.liste_roles()}
    assert set(roles.PAGES_PAR_ROLE) <= en_base


def test_le_gerant_cree_un_compte_utilisable(app_maquis):
    from backend import lectures

    gerant = _connecte_en(app_maquis, "Gérant")
    id_role_bar = next(
        role["id"] for role in lectures.liste_roles() if role["nom"] == "Serveur bar"
    )

    creation = gerant.post(
        "/administration/utilisateurs",
        data={
            "nom": "Koffi",
            "email": "koffi@maquis.ci",
            "mot_de_passe": "koffi123",
            "id_role": id_role_bar,
        },
    ).get_json()
    assert creation["success"] is True

    nouveau = app_maquis.test_client()
    connexion = nouveau.post(
        "/login", data={"email": "koffi@maquis.ci", "password": "koffi123"}
    ).get_json()
    assert connexion["success"] is True

    carte = nouveau.get("/maquis/list").get_json()["data"]
    assert {article["type_categorie"] for article in carte} == {"Bar"}


def test_creation_de_compte_verifie_les_saisies(app_maquis):
    gerant = _connecte_en(app_maquis, "Gérant")

    court = gerant.post(
        "/administration/utilisateurs",
        data={"nom": "X", "email": "x@maquis.ci", "mot_de_passe": "123", "id_role": "1"},
    )
    assert court.status_code == 400
    assert "6 caractères" in court.get_json()["error"]

    doublon = gerant.post(
        "/administration/utilisateurs",
        data={
            "nom": "Bis",
            "email": "admin@divixmaquis.ci",
            "mot_de_passe": "motdepasse",
            "id_role": "1",
        },
    )
    assert doublon.status_code == 400
    assert "existe déjà" in doublon.get_json()["error"]


def test_le_gerant_ne_peut_pas_se_verrouiller(app_maquis):
    from backend import lectures

    gerant = _connecte_en(app_maquis, "Gérant")
    moi = next(
        utilisateur["id"]
        for utilisateur in lectures.liste_utilisateurs()
        if utilisateur["email"] == "admin@divixmaquis.ci"
    )

    assert gerant.post(
        f"/administration/utilisateurs/{moi}/actif", data={"actif": "0"}
    ).status_code == 400
    assert gerant.post(
        f"/administration/utilisateurs/{moi}/role", data={"id_role": "3"}
    ).status_code == 400


def test_compte_desactive_ne_se_connecte_plus(app_maquis):
    from backend import lectures

    gerant = _connecte_en(app_maquis, "Gérant")
    serveur = next(
        utilisateur["id"]
        for utilisateur in lectures.liste_utilisateurs()
        if utilisateur["email"] == "serveur@divixmaquis.ci"
    )

    assert gerant.post(
        f"/administration/utilisateurs/{serveur}/actif", data={"actif": "0"}
    ).get_json()["success"] is True

    refus = app_maquis.test_client().post(
        "/login", data={"email": "serveur@divixmaquis.ci", "password": "serveur123"}
    )
    assert refus.status_code == 401


def test_gestion_des_comptes_reservee_au_gerant(app_maquis):
    for role in ("Serveur bar", "Caissier"):
        client = _connecte_en(app_maquis, role)
        assert client.get("/administration").status_code == 302
        assert client.post(
            "/administration/utilisateurs",
            data={"nom": "Z", "email": "z@z.ci", "mot_de_passe": "zzzzzz", "id_role": "1"},
        ).status_code == 403


# ----------------------------------------------------------------------------
# RESSOURCES SERVIES LOCALEMENT
# ----------------------------------------------------------------------------


def _fichiers_front():
    sources = list((RACINE / "templates").rglob("*.html"))
    sources += list((RACINE / "static/js").glob("*.js"))
    sources += [RACINE / "backend/roles.py"]
    return sources


def test_aucune_ressource_chargee_depuis_un_cdn():
    """Le maquis doit rester utilisable avec une connexion instable."""
    import re

    motif = re.compile(r"""(?:src|href)=["']https?://([^/"']+)""")
    externes = set()
    for fichier in (RACINE / "templates").rglob("*.html"):
        externes.update(motif.findall(fichier.read_text(encoding="utf-8")))

    assert externes == set(), f"ressources externes : {sorted(externes)}"


def test_toutes_les_icones_utilisees_sont_embarquees():
    """Une icône absente de la feuille ne s'affiche pas — sans rien signaler."""
    import re

    feuille = (RACINE / "static/vendor/boxicons/boxicons.css").read_text(encoding="utf-8")
    motif = re.compile(r"\b(bxf|bx|bxb) (bx-[a-z0-9-]+)")

    utilisees = set()
    for fichier in _fichiers_front():
        utilisees.update(motif.findall(fichier.read_text(encoding="utf-8")))

    assert utilisees, "aucune icône relevée : le motif de détection est cassé"
    absentes = [
        f"{prefixe} {classe}"
        for prefixe, classe in sorted(utilisees)
        if f".{prefixe}.{classe} {{" not in feuille
    ]
    assert not absentes, (
        f"icônes sans règle : {absentes} — relancer outils/generer_icones.py"
    )


def test_fichiers_embarques_presents():
    attendus = [
        "vendor/bootstrap/bootstrap.min.css",
        "vendor/bootstrap/bootstrap.bundle.min.js",
        "vendor/sweetalert2/sweetalert2.all.min.js",
        "vendor/chartjs/chart.umd.js",
        "vendor/boxicons/boxicons.css",
        "vendor/outfit/outfit.css",
        "vendor/outfit/files/outfit-latin-wght-normal.woff2",
    ]
    for chemin in attendus:
        fichier = RACINE / "static" / chemin
        assert fichier.exists(), f"manquant : {chemin}"
        assert fichier.stat().st_size > 0


def test_modification_d_un_article(app_maquis):
    """Un article ajouté doit pouvoir être corrigé — prix, nom, seuil."""
    gerant = _connecte_en(app_maquis, "Gérant")
    article = gerant.get("/maquis/list").get_json()["data"][0]
    categorie = next(
        c["id"]
        for c in __import__("backend.lectures", fromlist=["x"]).liste_categories(("Bar",))
    )

    modification = gerant.post(
        f"/maquis/{article['id']}/modifier",
        data={
            "nom": "Nom corrigé",
            "categorie": categorie,
            "prix": "1750",
            "cout_revient": "900",
            "gere_stock": "1",
            "seuil_alerte": "18",
            "disponible": "1",
        },
    ).get_json()
    assert modification["success"] is True

    apres = next(
        a for a in gerant.get("/maquis/list").get_json()["data"] if a["id"] == article["id"]
    )
    assert apres["nom"] == "Nom corrigé"
    assert apres["prix"] == 1750
    assert apres["seuil_alerte"] == 18
    # La quantité en stock ne se corrige que par un mouvement d'inventaire.
    assert apres["stock"] == article["stock"]


def test_une_carte_ne_touche_pas_a_l_autre(app_maquis):
    gerant = _connecte_en(app_maquis, "Gérant")
    plat = gerant.get("/menu/list").get_json()["data"][0]

    hors_carte = gerant.post(
        f"/maquis/{plat['id']}/modifier",
        data={"nom": "X", "categorie": "1", "prix": "100"},
    )
    assert hors_carte.status_code == 404

    mauvaise_categorie = gerant.post(
        "/maquis/add", data={"nom": "X", "categorie": "1", "prix": "100"}
    )
    assert mauvaise_categorie.status_code == 400
    assert "pas sur cette carte" in mauvaise_categorie.get_json()["error"]


def test_boutons_masques_pour_qui_ne_peut_pas_agir(app_maquis):
    """Masquer ne suffit pas : l'action reste refusée si la requête est forgée."""
    serveur = _connecte_en(app_maquis, "Serveur bar")
    gerant = _connecte_en(app_maquis, "Gérant")

    assert 'data-bs-target="#tableModal"' in gerant.get("/salle").get_data(as_text=True)
    assert 'data-bs-target="#tableModal"' not in serveur.get("/salle").get_data(as_text=True)
    assert serveur.post("/salle/add", data={"numero": "99"}).status_code == 403

    carte = serveur.get("/maquis").get_data(as_text=True)
    assert 'data-bs-target="#articleModal"' not in carte
    assert 'data-bs-target="#categorieModal"' not in carte


def test_bouton_commander_sur_la_caisse(app_maquis):
    """Sans serveurs connectés, le caissier prend la commande lui-même."""
    caisse = _connecte_en(app_maquis, "Caissier").get("/caisse").get_data(as_text=True)
    assert "?nouvelle=1" in caisse
    assert "Commander" in caisse

