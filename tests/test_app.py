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


# ----------------------------------------------------------------------------
# DROITS PAR RÔLE
# ----------------------------------------------------------------------------

COMPTES = {
    "Gérant": ("admin@divixmaquis.ci", "admin123"),
    "Caissier": ("caisse@divixmaquis.ci", "caisse123"),
    "Serveur": ("serveur@divixmaquis.ci", "serveur123"),
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


def test_libelle_court_pour_la_barre_du_telephone(app_maquis):
    """Huit onglets ne tiennent pas sur un écran de téléphone avec les libellés longs."""
    from backend import roles

    html = _connecte_en(app_maquis, "Gérant").get("/menu").get_data(as_text=True)
    for page in roles.PAGES:
        if page.get("court"):
            assert f"<span>{page['court']}</span>" in html

