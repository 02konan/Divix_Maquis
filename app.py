
import json
import os
import time
from datetime import timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_cors import CORS
from flask_login import LoginManager, current_user
from werkzeug.utils import secure_filename

from backend import ecritures, etablissement, journal, lectures, modules, roles
from backend.auth import authentifier, utilisateur_par_id
from backend.database import initialiser_base
from backend.models import User

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "divix-maquis-dev")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

EXTENSIONS_AUTORISEES = {"png", "jpg", "jpeg", "webp"}
# Une base recréée laisse des sessions qui pointent un utilisateur disparu :
# toute écriture échoue alors sur la clé étrangère id_utilisateur. On revérifie
# de loin en loin plutôt qu'à chaque requête, qui coûterait un aller-retour.
DELAI_VERIFICATION_SESSION = 300
ROUTES_PUBLIQUES = roles.ENDPOINTS_PUBLICS

initialiser_base()
roles.initialiser()
modules.initialiser()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def charger_utilisateur(id_utilisateur):
    return User.depuis_ligne(utilisateur_par_id(int(id_utilisateur)))


@app.before_request
def restreindre_acces():
    # Posé pour toute requête, y compris publique : le contexte est porté par le
    # thread, qui en sert plusieurs à la suite. Sans cette remise à jour
    # systématique, une requête anonyme hériterait de l'établissement du visiteur
    # précédent.
    etablissement.definir(session.get("id_etablissement"))

    if request.endpoint is None or request.endpoint in ROUTES_PUBLIQUES:
        return None

    connecte = current_user.is_authenticated or session.get("connecte")
    if not connecte:
        return redirect(url_for("login"))

    if not session_valide():
        session.clear()
        if request.endpoint in roles.ENDPOINTS_HTML and request.method == "GET":
            return redirect(url_for("login"))
        return jsonify(
            {"success": False, "error": "Session expirée : reconnectez-vous"}
        ), 403

    role = session.get("user_role")
    page = roles.PAGE_PAR_ENDPOINT.get(request.endpoint)
    autorise = roles.acces_autorise(role, request.endpoint, request.method)
    if autorise and modules.actif(page):
        return None

    # Une page interdite ou désactivée renvoie l'utilisateur chez lui ; un appel
    # de données répond en JSON, comme le reste de l'API.
    if request.endpoint in roles.ENDPOINTS_HTML and request.method == "GET":
        return redirect(page_accueil(role))
    message = (
        "Accès non autorisé" if autorise is False else "Fonctionnalité désactivée"
    )
    return jsonify({"success": False, "error": message}), 403


@app.after_request
def journaliser(reponse):
    """Laisse une trace de chaque écriture réussie, sans que les routes s'en occupent.

    Le crochet est ici plutôt que dans chaque route : une écriture ajoutée au
    logiciel se journalise alors d'office, il suffit de lui donner un libellé
    dans `backend/journal.py`. Seules les réponses effectivement réussies sont
    tracées — un formulaire refusé n'est pas une action.
    """
    if request.method != "POST" or not journal.journalisable(request.endpoint):
        return reponse
    if reponse.status_code >= 400:
        return reponse
    if reponse.is_json and reponse.get_json(silent=True) is not None:
        if not reponse.get_json(silent=True).get("success", True):
            return reponse

    journal.enregistrer(
        action=request.endpoint,
        utilisateur={
            "id": session.get("user_id"),
            "nom": session.get("user_name"),
            "role": session.get("user_role"),
        },
        cible=cible_journalisee(reponse),
        details=journal.resumer(request.form),
        # Une route peut désigner l'établissement qu'elle a touché quand ce
        # n'est pas le sien : c'est le cas de l'éditeur, qui n'en a aucun.
        id_etablissement=g.get("journal_etablissement"),
    )
    return reponse


CLES_CIBLE = ("reference", "id_article", "id_utilisateur", "id_table", "cle")


def cible_journalisee(reponse):
    """Ce que l'action a touché : la référence rendue, sinon l'objet désigné."""
    donnees = reponse.get_json(silent=True) if reponse.is_json else None
    if isinstance(donnees, dict) and donnees.get("reference"):
        return donnees["reference"]
    for source in (request.view_args or {}, request.form):
        for cle in CLES_CIBLE:
            if cle in source:
                return source[cle]
    return None


@app.context_processor
def injecter_contexte():
    """Menu, fonctionnalités actives et droits, pour tous les gabarits."""
    role = session.get("user_role")
    actifs = modules.actifs()

    def peut(endpoint, methode="POST"):
        """Le rôle peut-il déclencher cette action ? Sert à masquer les boutons.

        S'appuie sur le même contrôle que le serveur : un bouton visible mène
        toujours à une action permise, et un bouton masqué reste refusé si
        quelqu'un forge la requête.
        """
        page = roles.PAGE_PAR_ENDPOINT.get(endpoint)
        return roles.acces_autorise(role, endpoint, methode) and modules.actif(page)

    return {
        "nav_items": [
            page
            for page in roles.menu(role)
            if page["cle"] not in modules.CLES or page["cle"] in actifs
        ],
        "modules_actifs": actifs,
        "peut": peut,
    }


def session_valide():
    """L'utilisateur de la session a-t-il toujours le droit d'être là ?

    Revérifie aussi ce que la connexion avait vérifié : un établissement
    suspendu ou une fonctionnalité « Serveurs » coupée depuis doivent finir par
    fermer la porte, pas seulement aux prochains à se connecter.
    """
    if time.time() - session.get("verifie_le", 0) < DELAI_VERIFICATION_SESSION:
        return True
    utilisateur = utilisateur_par_id(session.get("user_id"))
    if utilisateur is None or refuser_connexion(utilisateur):
        return False
    session["verifie_le"] = time.time()
    return True


def page_accueil(role):
    """Première page à la fois autorisée pour le rôle et activée."""
    for page in roles.menu(role):
        if modules.actif(page["cle"]):
            return page["url"]
    return "/logout"


def extension_autorisee(nom_fichier):
    return (
        "." in nom_fichier
        and nom_fichier.rsplit(".", 1)[1].lower() in EXTENSIONS_AUTORISEES
    )


def enregistrer_image(champ="image"):
    fichier = request.files.get(champ)
    if not fichier or not fichier.filename or not extension_autorisee(fichier.filename):
        return None
    nom_fichier = secure_filename(fichier.filename)
    fichier.save(os.path.join(app.config["UPLOAD_FOLDER"], nom_fichier))
    return nom_fichier

def utilisateur_courant():
    return session.get("user_id")

def domaines_courants():
    """Types de catégories du rôle connecté ; None quand il voit toute la carte."""
    return roles.domaines(session.get("user_role"))

def nombre(valeur_brute, defaut=0):
    try:
        return float(valeur_brute)
    except (TypeError, ValueError):
        return defaut


# ============================== AUTHENTIFICATION ==============================


def refuser_connexion(utilisateur):
    """Motif de refus après un mot de passe pourtant juste, ou None.

    L'établissement du compte est posé dans le contexte au passage : la requête
    de connexion est anonyme, donc `before_request` n'y a rien mis, et la suite
    — état des fonctionnalités, page d'accueil — en a besoin.
    """
    etablissement.definir(utilisateur["id_etablissement"])

    if not utilisateur["etablissement_actif"]:
        return "Cet établissement est suspendu. Contactez l'éditeur du logiciel."
    if utilisateur["nom_role"] in roles.ROLES_SERVEUR and not modules.actif("serveur"):
        return (
            "Cet établissement ne fonctionne pas avec des serveurs connectés. "
            "Voyez avec votre gérant."
        )
    return None


@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    """Ouvre un établissement et son compte gérant, en une fois."""
    if request.method == "GET":
        if session.get("connecte"):
            return redirect(page_accueil(session.get("user_role")))
        return render_template("inscription.html")

    nom_etablissement = (request.form.get("etablissement") or "").strip()
    nom = (request.form.get("nom") or "").strip()
    email = (request.form.get("email") or "").strip()
    mot_de_passe = request.form.get("mot_de_passe") or ""

    if not nom_etablissement or not nom or not email or not mot_de_passe:
        return jsonify(
            {"success": False, "error": "Tous les champs sont obligatoires"}
        ), 400

    resultat = etablissement.creer(
        nom_etablissement,
        request.form.get("ville"),
        request.form.get("telephone"),
    )
    if not resultat["success"]:
        return jsonify(resultat), 400

    # Le gérant est créé dans son établissement, donc dans son contexte.
    etablissement.definir(resultat["id_etablissement"])
    id_role = next(
        role["id"] for role in lectures.liste_roles() if role["nom"] == "Gérant"
    )
    compte = ecritures.creer_compte(nom, email, mot_de_passe, id_role)
    if not compte["success"]:
        # L'établissement resterait sans personne pour y entrer.
        etablissement.basculer(resultat["id_etablissement"], False)
        return jsonify(compte), 400

    return jsonify(
        {
            "success": True,
            "message": "Établissement créé ! Connectez-vous pour commencer.",
            "redirect": url_for("login"),
        }
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        mot_de_passe = request.form.get("password")
        se_souvenir = request.form.get("remember")

        if not email or not mot_de_passe:
            return jsonify(
                {"success": False, "error": "Veuillez remplir tous les champs"}
            ), 400

        utilisateur = authentifier(email, mot_de_passe)
        if not utilisateur:
            return jsonify(
                {"success": False, "error": "Email ou mot de passe incorrect"}
            ), 401

        refus = refuser_connexion(utilisateur)
        if refus:
            return jsonify({"success": False, "error": refus}), 403

        session["connecte"] = True
        session["user_id"] = utilisateur["id"]
        session["user_name"] = utilisateur["nom"]
        session["user_email"] = utilisateur["email"]
        session["user_role"] = utilisateur["nom_role"]
        session["id_etablissement"] = utilisateur["id_etablissement"]
        session["nom_etablissement"] = utilisateur["nom_etablissement"]
        session["verifie_le"] = time.time()
        session.permanent = True
        app.permanent_session_lifetime = (
            timedelta(days=30) if se_souvenir else timedelta(hours=2)
        )

        return jsonify(
            {
                "success": True,
                "message": "Connexion réussie! Redirection...",
                "redirect": page_accueil(utilisateur["nom_role"]),
            }
        )

    if session.get("connecte"):
        return redirect(page_accueil(session.get("user_role")))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================================= DASHBOARD =================================


@app.route("/")
def dashboard():
    return render_template("dashboard.html", active_page="dashboard")


@app.route("/dashboard/data")
def dashboard_data():
    try:
        salle_active = modules.actif("salle")
        compteurs_salle = (
            lectures.compteurs_salle()
            if salle_active
            else {"tables_occupees": 0, "total_tables": 0}
        )
        compteurs_commandes = lectures.compteurs_commandes()
        indicateurs = lectures.indicateurs_jour()

        dernieres = [
            {
                "reference": commande["reference"],
                "client": commande["client"],
                "table": commande["table_numero"],
                "statut": commande["statut"],
                "montant": commande["montant_total"],
                "date": commande["date_commande"],
            }
            for commande in lectures.dernieres_commandes(6)
        ]

        return jsonify(
            {
                "success": True,
                "data": {
                    "ca_jour": indicateurs["ca_jour"],
                    "ca_total": indicateurs["ca_total"],
                    "commandes_jour": compteurs_commandes["commandes_jour"],
                    "ticket_moyen": indicateurs["ticket_moyen"],
                    "couverts_jour": indicateurs["couverts_jour"],
                    "tables_occupees": compteurs_salle["tables_occupees"],
                    "total_tables": compteurs_salle["total_tables"],
                    "montant_impaye": compteurs_commandes["montant_impaye"],
                    "salle_active": salle_active,
                    "ca_par_jour": lectures.ca_par_jour(7),
                    "top_articles": lectures.top_articles(5),
                    "dernieres_commandes": dernieres,
                    "pourcentages": {
                        "ca": lectures.evolution("paiements", "date_paiement"),
                        "commandes": lectures.evolution_nombre(
                            "commandes", "date_commande", "statut != 'Annulée'"
                        ),
                        "depenses": lectures.evolution("depenses", "date_depense"),
                    },
                },
            }
        )
    except Exception as erreur:
        return jsonify({"success": False, "error": str(erreur)}), 500


# =================================== SALLE ===================================


@app.route("/salle")
def salle():
    return render_template("salle.html", active_page="salle")


@app.route("/salle/list")
def salle_list():
    return jsonify(
        {"data": lectures.liste_tables(), "counter": lectures.compteurs_salle()}
    )


@app.route("/salle/add", methods=["POST"])
def salle_add():
    numero = request.form.get("numero")
    zone = request.form.get("zone") or "Salle"
    places = request.form.get("places") or 4

    if not numero:
        return jsonify({"success": False, "error": "Numéro de table obligatoire"}), 400

    resultat = ecritures.creer_table(numero, zone, places)
    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Table ajoutée avec succès"})


@app.route("/salle/<int:id_table>/statut", methods=["POST"])
def salle_statut(id_table):
    resultat = ecritures.changer_statut_table(id_table, request.form.get("statut"))
    return jsonify(resultat), 200 if resultat["success"] else 400


# ========================== CARTES : MAQUIS ET MENU ==========================
#
# Deux pages sur le même gabarit : le maquis sert la boisson, le menu la
# nourriture. Le domaine vient de la page, pas du rôle — un gérant voit les deux
# pages, un serveur du bar la sienne seulement.


def _carte(page):
    domaines = roles.domaine_page(page)
    role = session.get("user_role")
    return render_template(
        "carte.html",
        active_page=page,
        page_carte=page,
        type_carte=domaines[0],
        categories=lectures.liste_categories(domaines),
        # Un serveur consulte sans modifier : inutile de lui montrer des boutons
        # qui répondraient 403. En revanche il commande, donc c'est « Ajouter »
        # qui s'affiche sur les articles.
        peut_modifier=roles.acces_autorise(role, f"{page}_add", "POST"),
        peut_commander=roles.acces_autorise(role, "commande_add", "POST"),
    )


def _carte_list(page):
    domaines = roles.domaine_page(page)
    articles = lectures.liste_articles(domaines)
    for article in articles:
        article["statut"] = lectures.statut_stock(article)
    return jsonify({"data": articles, "counter": lectures.compteurs_menu(domaines)})


def _carte_add(page):
    nom = request.form.get("nom")
    id_categorie = request.form.get("categorie")
    prix = request.form.get("prix")

    if not nom or not id_categorie or not prix:
        return jsonify(
            {"success": False, "error": "Nom, catégorie et prix sont obligatoires"}
        ), 400

    domaines = roles.domaine_page(page)
    if not lectures.categorie_du_domaine(id_categorie, domaines):
        return jsonify(
            {"success": False, "error": "Cette catégorie n'est pas sur cette carte"}
        ), 400

    gere_stock = 1 if request.form.get("gere_stock") == "1" else 0
    resultat = ecritures.creer_article(
        nom=nom,
        id_categorie=id_categorie,
        prix=nombre(prix),
        cout_revient=nombre(request.form.get("cout_revient")),
        gere_stock=gere_stock,
        stock=int(nombre(request.form.get("stock"))) if gere_stock else 0,
        seuil_alerte=int(nombre(request.form.get("seuil_alerte"))) if gere_stock else 0,
        disponible=1 if request.form.get("disponible", "1") == "1" else 0,
        image=enregistrer_image(),
        id_utilisateur=utilisateur_courant(),
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Article ajouté"})


def _carte_modifier(page, id_article):
    domaines = roles.domaine_page(page)
    if not lectures.article_par_id(id_article, domaines):
        return jsonify(
            {"success": False, "error": "Cet article n'est pas sur cette carte"}
        ), 404

    nom = request.form.get("nom")
    id_categorie = request.form.get("categorie")
    prix = request.form.get("prix")
    if not nom or not id_categorie or not prix:
        return jsonify(
            {"success": False, "error": "Nom, catégorie et prix sont obligatoires"}
        ), 400
    if not lectures.categorie_du_domaine(id_categorie, domaines):
        return jsonify(
            {"success": False, "error": "Cette catégorie n'est pas sur cette carte"}
        ), 400

    gere_stock = 1 if request.form.get("gere_stock") == "1" else 0
    resultat = ecritures.modifier_article(
        id_article=id_article,
        nom=nom,
        id_categorie=id_categorie,
        prix=nombre(prix),
        # Le champ est masqué du formulaire : absent, il vaut « ne pas y
        # toucher ». L'interpréter comme zéro effacerait la marge à chaque
        # modification d'un article.
        cout_revient=(
            nombre(request.form["cout_revient"])
            if "cout_revient" in request.form
            else None
        ),
        gere_stock=gere_stock,
        seuil_alerte=int(nombre(request.form.get("seuil_alerte"))) if gere_stock else 0,
        disponible=1 if request.form.get("disponible", "1") == "1" else 0,
        image=enregistrer_image(),
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Article modifié"})


def _carte_disponibilite(page, id_article):
    if not lectures.article_par_id(id_article, roles.domaine_page(page)):
        return jsonify(
            {"success": False, "error": "Cet article n'est pas sur cette carte"}
        ), 404
    disponible = request.form.get("disponible") == "1"
    return jsonify(ecritures.basculer_disponibilite(id_article, disponible))


def _carte_categorie_add(page):
    nom = request.form.get("nom")
    if not nom:
        return jsonify({"success": False, "error": "Nom de catégorie obligatoire"}), 400

    # Le type ne se choisit pas : il découle de la page où l'on se trouve.
    resultat = ecritures.creer_categorie(nom, roles.domaine_page(page)[0])
    return jsonify(resultat), 200 if resultat["success"] else 400


@app.route("/maquis")
def maquis():
    return _carte("maquis")


@app.route("/maquis/list")
def maquis_list():
    return _carte_list("maquis")


@app.route("/maquis/add", methods=["POST"])
def maquis_add():
    return _carte_add("maquis")


@app.route("/maquis/<int:id_article>/modifier", methods=["POST"])
def maquis_modifier(id_article):
    return _carte_modifier("maquis", id_article)


@app.route("/maquis/<int:id_article>/disponibilite", methods=["POST"])
def maquis_disponibilite(id_article):
    return _carte_disponibilite("maquis", id_article)


@app.route("/maquis/categorie/add", methods=["POST"])
def maquis_categorie_add():
    return _carte_categorie_add("maquis")


@app.route("/menu")
def menu():
    return _carte("menu")


@app.route("/menu/list")
def menu_list():
    return _carte_list("menu")


@app.route("/menu/add", methods=["POST"])
def menu_add():
    return _carte_add("menu")


@app.route("/menu/<int:id_article>/modifier", methods=["POST"])
def menu_modifier(id_article):
    return _carte_modifier("menu", id_article)


@app.route("/menu/<int:id_article>/disponibilite", methods=["POST"])
def menu_disponibilite(id_article):
    return _carte_disponibilite("menu", id_article)


@app.route("/menu/categorie/add", methods=["POST"])
def menu_categorie_add():
    return _carte_categorie_add("menu")


@app.route("/menu/disponibles")
def menu_disponibles():
    """Sélecteur d'articles de la prise de commande : filtré par le rôle."""
    return jsonify({"data": lectures.articles_disponibles(domaines_courants())})


# =================================== STOCK ===================================


@app.route("/stock")
def stock():
    return render_template(
        "stock.html", active_page="stock", articles=lectures.liste_stock()
    )


@app.route("/stock/list")
def stock_list():
    return jsonify(
        {
            "data": lectures.liste_stock(),
            "counter": lectures.compteurs_stock(),
            "mouvements": lectures.derniers_mouvements(30),
        }
    )


@app.route("/stock/mouvement", methods=["POST"])
def stock_mouvement():
    id_article = request.form.get("id_article")
    type_mouvement = request.form.get("type_mouvement")
    quantite = request.form.get("quantite")

    if not id_article or not type_mouvement or not quantite:
        return jsonify(
            {"success": False, "error": "Article, type et quantité sont obligatoires"}
        ), 400

    if type_mouvement not in ("Entrée", "Sortie", "Perte", "Inventaire"):
        return jsonify({"success": False, "error": "Type de mouvement invalide"}), 400

    resultat = ecritures.enregistrer_mouvement(
        id_article=int(id_article),
        type_mouvement=type_mouvement,
        quantite=int(nombre(quantite)),
        motif=request.form.get("motif"),
        id_utilisateur=utilisateur_courant(),
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Mouvement de stock enregistré"})


# ================================= COMMANDES =================================


@app.route("/commande")
def commande():
    return render_template(
        "commandes.html",
        active_page="commande",
        tables=lectures.liste_tables() if modules.actif("salle") else [],
        types_service=ecritures.TYPES_SERVICE,
    )


@app.route("/commande/list")
def commande_list():
    domaines = domaines_courants()
    return jsonify(
        {
            "data": lectures.liste_commandes(domaines=domaines),
            "counter": lectures.compteurs_commandes(domaines),
        }
    )


@app.route("/commande/add", methods=["POST"])
def commande_add():
    try:
        articles = json.loads(request.form.get("articles", "[]"))
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Format des articles invalide"}), 400

    if not articles:
        return jsonify({"success": False, "error": "Aucun article sélectionné"}), 400

    for article in articles:
        if "id_article" not in article or "quantite" not in article:
            return jsonify({"success": False, "error": "Article invalide"}), 400

    resultat = ecritures.creer_commande(
        id_utilisateur=utilisateur_courant(),
        id_table=(request.form.get("id_table") or None)
        if modules.actif("salle")
        else None,
        type_service=request.form.get("type_service") or "Sur place",
        nom_client=request.form.get("nom_client"),
        telephone_client=request.form.get("telephone_client"),
        couverts=int(nombre(request.form.get("couverts"), 1)),
        remise=nombre(request.form.get("remise")),
        commentaire=request.form.get("commentaire"),
        articles=articles,
        domaines=domaines_courants(),
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Commande enregistrée avec succès"})


@app.route("/commande/<reference>")
def commande_detail(reference):
    detail = lectures.detail_commande(reference, domaines_courants())
    if not detail:
        return jsonify({"success": False, "error": "Commande introuvable"}), 404
    return jsonify({"success": True, "data": detail})


@app.route("/commande/<reference>/statut", methods=["POST"])
def commande_statut(reference):
    resultat = ecritures.changer_statut_commande(
        reference, request.form.get("statut"), domaines_courants()
    )
    return jsonify(resultat), 200 if resultat["success"] else 400


# =================================== CAISSE ===================================


@app.route("/caisse")
def caisse():
    return render_template(
        "caisse.html", active_page="caisse", modes=ecritures.MODES_PAIEMENT
    )


@app.route("/caisse/list")
def caisse_list():
    return jsonify(
        {
            "data": lectures.liste_paiements(),
            "counter": lectures.compteurs_caisse(),
            "modes": lectures.repartition_modes_paiement(),
        }
    )


@app.route("/caisse/encaissables")
def caisse_encaissables():
    commandes = lectures.commandes_a_encaisser()
    for commande_ouverte in commandes:
        commande_ouverte["reste_a_payer"] = round(
            max(
                commande_ouverte["montant_total"] - commande_ouverte["total_paye"], 0
            ),
            2,
        )
    return jsonify({"data": commandes})


@app.route("/caisse/add", methods=["POST"])
def caisse_add():
    reference = request.form.get("reference")
    montant = request.form.get("montant")
    mode = request.form.get("mode")

    if not reference or not montant or not mode:
        return jsonify(
            {"success": False, "error": "Commande, montant et mode sont obligatoires"}
        ), 400

    resultat = ecritures.encaisser(
        id_utilisateur=utilisateur_courant(),
        reference_commande=reference,
        montant=montant,
        mode=mode,
        commentaire=request.form.get("commentaire"),
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Encaissement enregistré"})


# ================================== DÉPENSES ==================================


@app.route("/depense")
def depense():
    return render_template(
        "depenses.html",
        active_page="depense",
        categories=ecritures.CATEGORIES_DEPENSE,
        modes=ecritures.MODES_PAIEMENT,
    )


@app.route("/depense/list")
def depense_list():
    return jsonify(
        {"data": lectures.liste_depenses(), "counter": lectures.compteurs_depenses()}
    )


@app.route("/depense/add", methods=["POST"])
def depense_add():
    libelle = request.form.get("libelle")
    categorie = request.form.get("categorie")
    montant = request.form.get("montant")

    if not libelle or not categorie or not montant:
        return jsonify(
            {"success": False, "error": "Libellé, catégorie et montant sont obligatoires"}
        ), 400

    resultat = ecritures.creer_depense(
        id_utilisateur=utilisateur_courant(),
        libelle=libelle,
        categorie=categorie,
        montant=montant,
        fournisseur=request.form.get("fournisseur"),
        mode_paiement=request.form.get("mode_paiement"),
        date_depense=request.form.get("date_depense"),
        commentaire=request.form.get("commentaire"),
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Dépense enregistrée"})


# =============================== ADMINISTRATION ===============================


@app.route("/administration")
def administration():
    return render_template(
        "administration.html",
        active_page="administration",
        utilisateurs=lectures.liste_utilisateurs(),
        roles_disponibles=lectures.liste_roles(modules.actif("serveur")),
        id_courant=utilisateur_courant(),
    )


@app.route("/administration/utilisateurs", methods=["POST"])
def administration_utilisateur_add():
    resultat = ecritures.creer_compte(
        nom=request.form.get("nom"),
        email=request.form.get("email"),
        mot_de_passe=request.form.get("mot_de_passe"),
        id_role=request.form.get("id_role"),
    )
    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Compte créé"})


@app.route("/administration/utilisateurs/<int:id_utilisateur>/actif", methods=["POST"])
def administration_utilisateur_actif(id_utilisateur):
    actif = request.form.get("actif") == "1"
    resultat = ecritures.basculer_compte(id_utilisateur, actif, utilisateur_courant())
    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Compte activé" if actif else "Compte désactivé"})


@app.route("/administration/utilisateurs/<int:id_utilisateur>/role", methods=["POST"])
def administration_utilisateur_role(id_utilisateur):
    resultat = ecritures.changer_role(
        id_utilisateur, request.form.get("id_role"), utilisateur_courant()
    )
    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Rôle modifié"})


@app.route("/administration/utilisateurs/<int:id_utilisateur>/motdepasse", methods=["POST"])
def administration_utilisateur_motdepasse(id_utilisateur):
    resultat = ecritures.reinitialiser_mot_de_passe(
        id_utilisateur, request.form.get("mot_de_passe")
    )
    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Mot de passe réinitialisé"})


# ================================== JOURNAL ===================================


# L'endpoint garde le nom de la page ; la fonction, non, pour ne pas masquer le
# module `journal` importé plus haut.
@app.route("/journal", endpoint="journal")
def journal_page():
    return render_template(
        "journal.html", active_page="journal", libelles=journal.libelles_utilises()
    )


@app.route("/journal/list")
def journal_list():
    return jsonify({"data": journal.liste(), "counter": journal.compteurs()})


# ================================= PLATEFORME =================================
# Réservée à l'éditeur : elle voit tous les établissements de la base, là où
# chaque gérant ne voit jamais que le sien.


@app.route("/plateforme")
def plateforme():
    return render_template("plateforme.html", active_page="plateforme")


@app.route("/plateforme/list")
def plateforme_list():
    etablissements = etablissement.liste()
    return jsonify(
        {
            "data": etablissements,
            "counter": {
                "total_etablissements": len(etablissements),
                "etablissements_actifs": sum(
                    1 for ligne in etablissements if ligne["actif"]
                ),
                "comptes_total": sum(ligne["comptes"] for ligne in etablissements),
            },
        }
    )


@app.route("/plateforme/add", methods=["POST"])
def plateforme_add():
    resultat = etablissement.creer(
        request.form.get("nom"),
        request.form.get("ville"),
        request.form.get("telephone"),
    )
    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Établissement créé"})


@app.route("/plateforme/<int:id_etablissement>/actif", methods=["POST"])
def plateforme_actif(id_etablissement):
    actif = request.form.get("actif") == "1"
    resultat = etablissement.basculer(id_etablissement, actif)
    if not resultat["success"]:
        return jsonify(resultat), 400
    message = "Établissement rouvert" if actif else "Établissement suspendu"
    return jsonify({**resultat, "message": message})


@app.route("/plateforme/<int:id_etablissement>/modules", methods=["GET", "POST"])
def plateforme_modules(id_etablissement):
    """Les fonctionnalités d'un établissement, décidées par l'éditeur.

    C'est ici et non sur la page Administration du maquis : ce que l'on souscrit
    ne se donne pas soi-même.
    """
    if not etablissement.par_id(id_etablissement):
        return jsonify({"success": False, "error": "Établissement introuvable"}), 404

    if request.method == "GET":
        return jsonify({"data": modules.liste(id_etablissement)})

    actif = request.form.get("actif") == "1"
    resultat = modules.basculer(request.form.get("cle"), actif, id_etablissement)
    if not resultat["success"]:
        return jsonify(resultat), 400

    # Le gérant doit pouvoir constater dans son journal pourquoi une page a
    # disparu de son menu : la trace va chez lui, pas chez l'éditeur.
    g.journal_etablissement = id_etablissement

    etat = "activée" if actif else "désactivée"
    return jsonify({**resultat, "message": f"Fonctionnalité {etat}"})


if __name__ == "__main__":
    # 0.0.0.0 et PORT : en conteneur, écouter sur 127.0.0.1 rend le service
    # invisible de l'extérieur et l'hébergeur ne détecte aucun port ouvert.
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG") == "1",
    )
