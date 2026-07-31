import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_TEST = "divix_maquis_test"


def _decharger_modules():
    """Force la relecture de la configuration MySQL au prochain import."""
    for module in list(sys.modules):
        if module == "app" or module.startswith("backend"):
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

    from Divix_Maquis.donnees_demo import peupler

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

    apres = client_connecte.get("/menu/list").get_json()["data"]
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
