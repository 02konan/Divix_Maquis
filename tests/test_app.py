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

    # Les tests qui appellent `lectures`/`ecritures` sans passer par une requête
    # HTTP ont besoin du même contexte que `before_request` pose en service.
    from backend import etablissement

    etablissement.definir(etablissement.liste()[0]["id"])

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

    from backend import etablissement

    # Un fil neuf démarre sur un contexte vide : l'établissement doit y être
    # reposé, comme le fait `before_request` pour chaque requête servie.
    id_etablissement = etablissement.courant()
    resultats = []
    verrou = threading.Lock()
    depart = threading.Barrier(nb_fils)

    def executer_action():
        etablissement.definir(id_etablissement)
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
    "Gestionnaire de stock": ("stock@divixmaquis.ci", "stock123"),
    "Serveur": ("serveur@divixmaquis.ci", "serveur123"),
    "Serveur bar": ("bar@divixmaquis.ci", "bar123"),
    "Serveur restaurant": ("resto@divixmaquis.ci", "resto123"),
    "Administrateur plateforme": ("plateforme@divix.ci", "plateforme123"),
}


def _cadrer():
    """Repose l'établissement de démonstration dans le contexte du test.

    Toute requête HTTP y pose celui de sa session — donc rien quand elle est
    anonyme, comme le POST de connexion. Un test qui appelle ensuite `lectures`
    ou `ecritures` directement doit le reposer, exactement comme le ferait la
    requête suivante.
    """
    from backend import etablissement

    id_etablissement = etablissement.liste()[0]["id"]
    etablissement.definir(id_etablissement)
    return id_etablissement


def _connecte_en(app_maquis, role):
    client = app_maquis.test_client()
    email, mot_de_passe = COMPTES[role]
    reponse = client.post("/login", data={"email": email, "password": mot_de_passe})
    assert reponse.get_json()["success"] is True
    _cadrer()
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
    from backend import roles
    from backend.database import lire_tout

    en_base = {ligne["nom"] for ligne in lire_tout("SELECT nom FROM roles")}
    assert set(roles.PAGES_PAR_ROLE) <= en_base


def test_le_role_plateforme_n_est_pas_attribuable_dans_un_maquis(app_maquis):
    """Le gérant ne doit pas pouvoir se hisser au niveau de l'éditeur."""
    from backend import ecritures, lectures, roles
    from backend.database import lire_un

    _cadrer()
    assert roles.ROLE_PLATEFORME not in {r["nom"] for r in lectures.liste_roles()}

    id_plateforme = lire_un(
        "SELECT id FROM roles WHERE nom = %s", (roles.ROLE_PLATEFORME,)
    )["id"]
    refus = ecritures.creer_compte("X", "x@x.ci", "xxxxxx", id_plateforme)
    assert refus["success"] is False
    assert "réservé à l'éditeur" in refus["error"]


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


def test_bouton_encaisser_sur_les_commandes(app_maquis):
    """Symétrique de « Commander » : le raccourci ouvre le formulaire de caisse."""
    commandes = (
        _connecte_en(app_maquis, "Caissier").get("/commande").get_data(as_text=True)
    )
    assert "/caisse?encaisser=1" in commandes
    assert "Encaisser" in commandes


def test_raccourci_encaisser_masque_pour_le_serveur(app_maquis):
    """Un serveur n'encaisse pas : le raccourci ne doit pas le mener sur un 403."""
    commandes = (
        _connecte_en(app_maquis, "Serveur bar").get("/commande").get_data(as_text=True)
    )
    assert "encaisser=1" not in commandes
    assert _connecte_en(app_maquis, "Serveur bar").get("/caisse").status_code == 302


def test_la_barre_de_panier_ouvre_le_formulaire_de_commande(app_maquis):
    """Le panier constitué sur une carte n'a d'intérêt qu'une fois validé."""
    script = (RACINE / "static" / "js" / "carte.js").read_text(encoding="utf-8")
    assert "'/commande?nouvelle=1'" in script



# ----------------------------------------------------------------------------
# PLUSIEURS ÉTABLISSEMENTS DANS LA MÊME BASE
# ----------------------------------------------------------------------------

# Tout ce que crée le maquis voisin porte ce mot : une lecture qui le laisse
# passer a oublié son filtre d'établissement.
MARQUE_VOISIN = "VOISIN"


def _peupler_voisin():
    """Un second maquis complet, dont chaque ligne est reconnaissable."""
    from backend import ecritures, etablissement
    from backend.auth import creer_utilisateur
    from backend.database import lire_un

    voisin = etablissement.creer(f"Maquis {MARQUE_VOISIN}", MARQUE_VOISIN)[
        "id_etablissement"
    ]
    etablissement.definir(voisin)

    id_role = lire_un("SELECT id FROM roles WHERE nom = 'Gérant'")["id"]
    id_gerant = creer_utilisateur(
        f"Gérant {MARQUE_VOISIN}", "voisin@maquis.ci", "voisin123", id_role, voisin
    )

    id_categorie = ecritures.creer_categorie(f"Bières {MARQUE_VOISIN}", "Bar")[
        "id_categorie"
    ]
    article = ecritures.creer_article(
        nom=f"Bière {MARQUE_VOISIN}",
        id_categorie=id_categorie,
        prix=999,
        cout_revient=500,
        gere_stock=1,
        stock=50,
        seuil_alerte=5,
        disponible=1,
        image=None,
        id_utilisateur=id_gerant,
    )
    id_table = ecritures.creer_table(f"T-{MARQUE_VOISIN}", MARQUE_VOISIN, 4)["id_table"]

    commande = ecritures.creer_commande(
        id_utilisateur=id_gerant,
        id_table=id_table,
        type_service="Sur place",
        nom_client=f"Client {MARQUE_VOISIN}",
        telephone_client=None,
        couverts=2,
        remise=0,
        commentaire=MARQUE_VOISIN,
        articles=[{"id_article": article["id_article"], "quantite": 1}],
    )
    assert commande["success"] is True
    paiement = ecritures.encaisser(
        id_gerant, commande["reference"], 999, "Espèces", MARQUE_VOISIN
    )
    assert paiement["success"] is True
    ecritures.creer_depense(
        id_gerant, f"Charbon {MARQUE_VOISIN}", "Divers", 4242, None, "Espèces", None, None
    )
    ecritures.enregistrer_mouvement(
        article["id_article"], "Entrée", 3, f"Appro {MARQUE_VOISIN}", id_gerant
    )

    return {
        "id": voisin,
        "id_article": article["id_article"],
        "id_categorie": id_categorie,
        "id_table": id_table,
        "id_commande": commande["id_commande"],
        "reference": commande["reference"],
    }


def _lectures_sans_argument():
    """Fonctions publiques de `lectures` appelables sans rien fournir."""
    import inspect

    from backend import lectures

    for nom, fonction in inspect.getmembers(lectures, inspect.isfunction):
        if nom.startswith("_") or fonction.__module__ != "backend.lectures":
            continue
        parametres = inspect.signature(fonction).parameters.values()
        if all(p.default is not inspect.Parameter.empty for p in parametres):
            yield nom, fonction


def test_aucune_lecture_ne_laisse_passer_l_autre_etablissement(app_maquis):
    """Le filtre d'établissement est vérifié sur toutes les lectures, pas sur un échantillon.

    Un filtre oublié dans une seule requête montrerait les données d'un maquis
    à un autre : le test parcourt donc tout `backend.lectures`.
    """
    import json

    from backend import etablissement

    maison = _cadrer()
    _peupler_voisin()
    etablissement.definir(maison)

    fuites = []
    for nom, fonction in _lectures_sans_argument():
        rendu = json.dumps(fonction(), ensure_ascii=False, default=str)
        if MARQUE_VOISIN in rendu:
            fuites.append(nom)

    assert fuites == []


def test_les_compteurs_ignorent_l_autre_etablissement(app_maquis):
    """Une fuite chiffrée ne se voit pas dans un nom : on compare avant et après."""
    from backend import etablissement, lectures

    maison = _cadrer()
    mesures = [
        lectures.compteurs_salle,
        lectures.compteurs_menu,
        lectures.compteurs_stock,
        lectures.compteurs_commandes,
        lectures.compteurs_caisse,
        lectures.compteurs_depenses,
        lectures.indicateurs_jour,
    ]
    avant = {mesure.__name__: mesure() for mesure in mesures}

    _peupler_voisin()
    etablissement.definir(maison)

    assert {mesure.__name__: mesure() for mesure in mesures} == avant


def test_les_lectures_par_identifiant_ne_traversent_pas(app_maquis):
    """Un identifiant deviné ne doit pas ouvrir la fiche du maquis d'à côté."""
    from backend import etablissement, lectures

    maison = _cadrer()
    voisin = _peupler_voisin()
    etablissement.definir(maison)

    assert lectures.article_par_id(voisin["id_article"]) is None
    assert lectures.categorie_du_domaine(voisin["id_categorie"]) is None
    assert lectures.table_par_id(voisin["id_table"]) is None
    assert lectures.resumes_articles([voisin["id_commande"]]) == {}


def test_une_reference_partagee_rend_le_ticket_de_chacun(app_maquis):
    """Les deux maquis ont un CMD-0001 : chacun doit tomber sur le sien.

    C'est le cas qui distingue un vrai cloisonnement d'un filtre approximatif —
    la référence ne suffit plus à désigner une commande.
    """
    from backend import etablissement, lectures

    maison = _cadrer()
    voisin = _peupler_voisin()
    assert voisin["reference"] == "CMD-0001"

    chez_le_voisin = lectures.detail_commande(voisin["reference"])
    assert chez_le_voisin["id"] == voisin["id_commande"]
    assert chez_le_voisin["nom_client"] == f"Client {MARQUE_VOISIN}"

    etablissement.definir(maison)
    chez_nous = lectures.detail_commande(voisin["reference"])
    assert chez_nous["id"] != voisin["id_commande"]
    assert MARQUE_VOISIN not in str(chez_nous)


def test_les_ecritures_par_identifiant_ne_traversent_pas(app_maquis):
    """Même chose côté écriture : rien ne doit changer chez le voisin."""
    from backend import ecritures, etablissement
    from backend.database import lire_un

    maison = _cadrer()
    voisin = _peupler_voisin()
    etablissement.definir(maison)

    ecritures.modifier_article(
        voisin["id_article"], "Détourné", None, 1, 0, 0, 0, 1, None
    )
    ecritures.basculer_disponibilite(voisin["id_article"], False)
    ecritures.changer_statut_table(voisin["id_table"], "Réservée")
    mouvement = ecritures.enregistrer_mouvement(
        voisin["id_article"], "Sortie", 10, "Détournement", 1
    )

    article = lire_un(
        "SELECT nom, disponible, stock FROM articles WHERE id = %s",
        (voisin["id_article"],),
    )
    assert article["nom"] == f"Bière {MARQUE_VOISIN}"
    assert article["disponible"] == 1
    assert article["stock"] == 52  # 50 à la création − 1 vendu + 3 d'appro
    assert mouvement["success"] is False
    assert (
        lire_un("SELECT statut FROM tables_salle WHERE id = %s", (voisin["id_table"],))[
            "statut"
        ]
        # Libérée par son propre encaissement, et pas « Réservée » par nous.
        == "Libre"
    )


def test_les_references_repartent_de_un_dans_chaque_etablissement(app_maquis):
    """Deux maquis peuvent avoir chacun leur CMD-0001 : la numérotation leur est propre."""
    _cadrer()
    voisin = _peupler_voisin()
    assert voisin["reference"] == "CMD-0001"


def test_un_gerant_ne_voit_que_son_etablissement(app_maquis):
    """Le cloisonnement tient aussi de bout en bout, à travers l'interface."""
    from backend import etablissement

    maison = _cadrer()
    _peupler_voisin()
    etablissement.definir(maison)

    voisin = app_maquis.test_client()
    assert voisin.post(
        "/login", data={"email": "voisin@maquis.ci", "password": "voisin123"}
    ).get_json()["success"] is True

    articles = voisin.get("/maquis/list").get_json()["data"]
    assert [article["nom"] for article in articles] == [f"Bière {MARQUE_VOISIN}"]

    maison_client = _connecte_en(app_maquis, "Gérant")
    noms = {a["nom"] for a in maison_client.get("/maquis/list").get_json()["data"]}
    assert f"Bière {MARQUE_VOISIN}" not in noms
    assert "Bière Flag 66cl" in noms


def test_inscription_ouvre_un_etablissement_et_son_gerant(app_maquis):
    client = app_maquis.test_client()
    reponse = client.post(
        "/inscription",
        data={
            "etablissement": "Chez Awa",
            "ville": "Yamoussoukro",
            "nom": "Awa",
            "email": "awa@chezawa.ci",
            "mot_de_passe": "awa12345",
        },
    )
    assert reponse.get_json()["success"] is True

    nouveau = app_maquis.test_client()
    assert nouveau.post(
        "/login", data={"email": "awa@chezawa.ci", "password": "awa12345"}
    ).get_json()["success"] is True

    # Un établissement neuf démarre vide, et avec toutes ses fonctionnalités.
    assert nouveau.get("/menu/list").get_json()["data"] == []
    assert nouveau.get("/administration").status_code == 200


def test_inscription_refuse_un_formulaire_incomplet(app_maquis):
    from backend import etablissement

    avant = len(etablissement.liste())
    client = app_maquis.test_client()
    assert client.post("/inscription", data={"etablissement": "Sans gérant"}).status_code == 400
    # Aucun établissement orphelin ne doit rester derrière un refus.
    assert len(etablissement.liste()) == avant


def test_console_plateforme_reservee_a_l_editeur(app_maquis):
    assert _connecte_en(app_maquis, "Gérant").get("/plateforme").status_code == 302
    assert _connecte_en(app_maquis, "Caissier").get("/plateforme/list").status_code == 403

    editeur = _connecte_en(app_maquis, "Administrateur plateforme")
    donnees = editeur.get("/plateforme/list").get_json()
    assert donnees["counter"]["total_etablissements"] >= 1
    # L'éditeur n'a pas de maquis : les pages de service lui sont fermées.
    assert editeur.get("/caisse").status_code == 302


def test_etablissement_suspendu_ferme_la_porte(app_maquis):
    from backend import etablissement

    maison = _cadrer()
    editeur = _connecte_en(app_maquis, "Administrateur plateforme")
    assert editeur.post(
        f"/plateforme/{maison}/actif", data={"actif": "0"}
    ).get_json()["success"] is True

    refus = app_maquis.test_client().post(
        "/login", data={"email": "admin@divixmaquis.ci", "password": "admin123"}
    )
    assert refus.status_code == 403
    assert "suspendu" in refus.get_json()["error"]

    assert editeur.post(
        f"/plateforme/{maison}/actif", data={"actif": "1"}
    ).get_json()["success"] is True
    assert app_maquis.test_client().post(
        "/login", data={"email": "admin@divixmaquis.ci", "password": "admin123"}
    ).get_json()["success"] is True


# ----------------------------------------------------------------------------
# FONCTIONNALITÉ « SERVEURS »
# ----------------------------------------------------------------------------


def _couper_les_serveurs(app_maquis):
    gerant = _connecte_en(app_maquis, "Gérant")
    reponse = gerant.post(
        "/administration/modules", data={"cle": "serveur", "actif": "0"}
    )
    assert reponse.get_json()["success"] is True
    _cadrer()
    return gerant


def test_serveurs_coupes_refusent_la_connexion(app_maquis):
    """Un maquis où le caissier saisit tout n'a pas de serveur qui se connecte."""
    _couper_les_serveurs(app_maquis)

    refus = app_maquis.test_client().post(
        "/login", data={"email": "bar@divixmaquis.ci", "password": "bar123"}
    )
    assert refus.status_code == 403
    assert "serveurs connectés" in refus.get_json()["error"]

    # Le caissier et le gérant, eux, continuent d'entrer.
    assert app_maquis.test_client().post(
        "/login", data={"email": "caisse@divixmaquis.ci", "password": "caisse123"}
    ).get_json()["success"] is True


def test_serveurs_coupes_retirent_les_roles_de_la_liste(app_maquis):
    from backend import ecritures, lectures, roles

    _couper_les_serveurs(app_maquis)

    proposes = {role["nom"] for role in lectures.liste_roles(serveurs_actifs=False)}
    assert not (proposes & roles.ROLES_SERVEUR)

    # Masquer ne suffit pas : le rôle doit aussi être refusé au serveur.
    id_bar = next(
        role["id"]
        for role in lectures.liste_roles()
        if role["nom"] == "Serveur bar"
    )
    refus = ecritures.creer_compte("Koffi", "koffi@x.ci", "koffi123", id_bar)
    assert refus["success"] is False
    assert "serveurs connectés" in refus["error"]


def test_serveurs_rendus_rouvrent_les_comptes(app_maquis):
    """Rien n'est supprimé : réactiver la fonctionnalité rend l'accès tel quel."""
    gerant = _couper_les_serveurs(app_maquis)
    assert gerant.post(
        "/administration/modules", data={"cle": "serveur", "actif": "1"}
    ).get_json()["success"] is True

    assert app_maquis.test_client().post(
        "/login", data={"email": "bar@divixmaquis.ci", "password": "bar123"}
    ).get_json()["success"] is True


def test_serveur_deja_connecte_est_mis_dehors(app_maquis):
    """Couper la fonctionnalité ne doit pas laisser les sessions ouvertes vivre leur vie."""
    serveur = _connecte_en(app_maquis, "Serveur bar")
    assert serveur.get("/commande").status_code == 200

    _couper_les_serveurs(app_maquis)

    # La session est revérifiée de loin en loin : on avance l'horloge. Chaque
    # requête part d'une session encore ouverte, puisque le refus la vide.
    with serveur.session_transaction() as session:
        session["verifie_le"] = 0
    appel = serveur.get("/commande/list")
    assert appel.status_code == 403
    assert "reconnectez-vous" in appel.get_json()["error"]

    with serveur.session_transaction() as session:
        session.update(
            connecte=True, user_id=4, user_role="Serveur bar", verifie_le=0,
            id_etablissement=_cadrer(),
        )
    assert serveur.get("/commande").status_code == 302


def test_stock_initial_compte_une_seule_fois(app_maquis):
    """Un article créé avec 50 bouteilles en a 50, pas 100.

    Le stock était posé à l'insertion *et* par le mouvement « Stock initial »
    qui suit : il doublait, et le journal ne collait plus au stock affiché.
    """
    from backend import ecritures, lectures

    _cadrer()
    cree = ecritures.creer_article(
        nom="Bière témoin",
        id_categorie=None,
        prix=1000,
        cout_revient=500,
        gere_stock=1,
        stock=50,
        seuil_alerte=5,
        disponible=1,
        image=None,
        id_utilisateur=1,
    )
    assert cree["success"] is True

    article = lectures.article_par_id(cree["id_article"])
    assert article["stock"] == 50

    mouvements = [
        mouvement
        for mouvement in lectures.derniers_mouvements()
        if mouvement["reference"] == cree["reference"]
    ]
    assert [m["type_mouvement"] for m in mouvements] == ["Entrée"]
    assert mouvements[0]["quantite"] == 50
    assert mouvements[0]["stock_apres"] == 50


def test_une_commande_ne_peut_pas_occuper_la_table_du_voisin(app_maquis):
    """Le numéro de table vient du formulaire : un identifiant deviné doit échouer."""
    from backend import ecritures, etablissement, lectures
    from backend.database import lire_un

    maison = _cadrer()
    voisin = _peupler_voisin()
    etablissement.definir(maison)

    article = lectures.articles_disponibles()[0]
    refus = ecritures.creer_commande(
        id_utilisateur=1,
        id_table=voisin["id_table"],
        type_service="Sur place",
        nom_client="Intrus",
        telephone_client=None,
        couverts=1,
        remise=0,
        commentaire=None,
        articles=[{"id_article": article["id"], "quantite": 1}],
    )
    assert refus["success"] is False
    assert "n'existe pas ici" in refus["error"]
    assert (
        lire_un("SELECT statut FROM tables_salle WHERE id = %s", (voisin["id_table"],))[
            "statut"
        ]
        == "Libre"
    )


# ----------------------------------------------------------------------------
# JOURNAL DES ACTIONS
# ----------------------------------------------------------------------------


def test_le_journal_enregistre_qui_a_fait_quoi(app_maquis):
    from backend import journal

    gerant = _connecte_en(app_maquis, "Gérant")
    creation = gerant.post(
        "/maquis/add",
        data={"nom": "Sucrerie témoin", "categorie": "5", "prix": "800",
              "gere_stock": "0"},
    ).get_json()
    assert creation["success"] is True

    _cadrer()
    ligne = journal.liste()[0]
    assert ligne["libelle"] == "Article ajouté au maquis"
    assert ligne["nom_utilisateur"] == "Konan Divix"
    assert ligne["role_utilisateur"] == "Gérant"
    assert ligne["cible"] == creation["reference"]
    assert "Sucrerie témoin" in ligne["details"]

    # La connexion elle-même laisse une trace.
    assert any(action["libelle"] == "Connexion" for action in journal.liste())


def test_le_journal_ignore_les_echecs_et_les_consultations(app_maquis):
    """Un formulaire refusé n'est pas une action, une lecture non plus."""
    from backend import journal

    gerant = _connecte_en(app_maquis, "Gérant")
    _cadrer()
    avant = len(journal.liste())

    assert gerant.post("/maquis/add", data={"nom": "Sans prix"}).status_code == 400
    gerant.get("/maquis/list")
    gerant.get("/caisse/list")

    _cadrer()
    assert len(journal.liste()) == avant


def test_le_journal_ne_recopie_aucun_mot_de_passe(app_maquis):
    """Un journal consultable ne doit pas devenir une liste de secrets."""
    from backend import journal

    gerant = _connecte_en(app_maquis, "Gérant")
    assert gerant.post(
        "/administration/utilisateurs",
        data={"nom": "Koffi", "email": "koffi@x.ci", "mot_de_passe": "secret-koffi",
              "id_role": "2"},
    ).get_json()["success"] is True

    _cadrer()
    tout = " ".join(str(action["details"]) for action in journal.liste())
    assert "secret-koffi" not in tout
    assert "admin123" not in tout
    assert "koffi@x.ci" in tout  # le reste du formulaire, lui, est bien tracé


def test_le_journal_est_propre_a_chaque_etablissement(app_maquis):
    from backend import etablissement, journal

    maison = _cadrer()
    _connecte_en(app_maquis, "Gérant")
    _peupler_voisin()
    voisin_actions = journal.liste()

    etablissement.definir(maison)
    assert MARQUE_VOISIN not in str(journal.liste())
    assert voisin_actions == []  # rien n'a été journalisé chez le voisin


def test_le_journal_est_reserve_au_gerant(app_maquis):
    for role in ("Caissier", "Serveur bar", "Gestionnaire de stock"):
        client = _connecte_en(app_maquis, role)
        assert client.get("/journal").status_code == 302
        assert client.get("/journal/list").status_code == 403

    assert _connecte_en(app_maquis, "Gérant").get("/journal").status_code == 200


def test_toute_ecriture_declaree_a_un_libelle(app_maquis):
    """Une écriture ajoutée au logiciel doit être journalisée, ou l'être sciemment.

    Le test liste les endpoints d'écriture et vérifie qu'aucun n'a été oublié
    sans qu'on l'ait décidé : sans lui, une nouvelle route passerait sous les
    radars du journal en silence.
    """
    from backend import journal

    # Actions de la console plateforme : elles ne sont dans le journal d'aucun
    # maquis, puisqu'elles n'appartiennent à aucun.
    hors_journal = {"plateforme_add", "plateforme_actif", "inscription"}

    ecritures_declarees = {
        regle.endpoint
        for regle in app_maquis.url_map.iter_rules()
        if "POST" in regle.methods
    }
    assert ecritures_declarees - set(journal.LIBELLES) == hors_journal


# ----------------------------------------------------------------------------
# GESTIONNAIRE DE STOCK
# ----------------------------------------------------------------------------


def test_le_gestionnaire_de_stock_tient_le_stock_et_les_depenses(app_maquis):
    from backend import lectures

    gestionnaire = _connecte_en(app_maquis, "Gestionnaire de stock")
    assert gestionnaire.get("/stock").status_code == 200
    assert gestionnaire.get("/depense").status_code == 200

    _cadrer()
    article = next(a for a in lectures.liste_stock())
    mouvement = gestionnaire.post(
        "/stock/mouvement",
        data={"id_article": article["id"], "type_mouvement": "Entrée",
              "quantite": "5", "motif": "Livraison"},
    ).get_json()
    assert mouvement["success"] is True
    assert mouvement["stock_apres"] == article["stock"] + 5

    depense = gestionnaire.post(
        "/depense/add",
        data={"libelle": "Casiers", "categorie": "Approvisionnement",
              "montant": "90000"},
    ).get_json()
    assert depense["success"] is True


def test_le_gestionnaire_de_stock_ne_touche_a_rien_d_autre(app_maquis):
    gestionnaire = _connecte_en(app_maquis, "Gestionnaire de stock")

    for page in ("/", "/caisse", "/maquis", "/menu", "/commande", "/salle",
                 "/administration"):
        assert gestionnaire.get(page).status_code == 302, page

    assert gestionnaire.post(
        "/commande/add", data={"type_service": "Sur place", "articles": "[]"}
    ).status_code == 403
    assert gestionnaire.post(
        "/caisse/add", data={"reference": "CMD-0001", "montant": "1", "mode": "Espèces"}
    ).status_code == 403


# ----------------------------------------------------------------------------
# CHAMPS MASQUÉS
# ----------------------------------------------------------------------------


def test_les_champs_couverts_et_cout_sont_masques(app_maquis):
    gerant = _connecte_en(app_maquis, "Gérant")
    assert 'name="couverts"' not in gerant.get("/commande").get_data(as_text=True)
    assert 'name="cout_revient"' not in gerant.get("/maquis").get_data(as_text=True)


def test_une_commande_sans_couverts_en_compte_un(app_maquis):
    gerant = _connecte_en(app_maquis, "Gérant")
    article = gerant.get("/menu/disponibles").get_json()["data"][0]
    creation = gerant.post(
        "/commande/add",
        data={"type_service": "Sur place",
              "articles": f'[{{"id_article": {article["id"]}, "quantite": 1}}]'},
    ).get_json()

    detail = gerant.get(f"/commande/{creation['reference']}").get_json()["data"]
    assert detail["couverts"] == 1


def test_modifier_un_article_ne_remet_pas_le_cout_a_zero(app_maquis):
    """Le champ masqué vaut « ne pas y toucher », pas « zéro »."""
    from backend import lectures

    gerant = _connecte_en(app_maquis, "Gérant")
    _cadrer()
    article = next(a for a in lectures.liste_articles(("Bar",)) if a["cout_revient"] > 0)

    modification = gerant.post(
        f"/maquis/{article['id']}/modifier",
        data={"nom": article["nom"] + " (retouché)", "categorie": "5",
              "prix": article["prix"], "gere_stock": "1" if article["gere_stock"] else "0",
              "seuil_alerte": article["seuil_alerte"], "disponible": "1"},
    ).get_json()
    assert modification["success"] is True

    _cadrer()
    apres = lectures.article_par_id(article["id"])
    assert apres["cout_revient"] == article["cout_revient"]
    assert apres["nom"].endswith("(retouché)")
