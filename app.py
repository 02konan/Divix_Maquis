"""Divix Maquis — gestion de maquis et restaurant.

Reprend l'interface de Divix SysPaie sur un backend métier restauration.
"""

import json
import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
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

from backend import ecritures, lectures
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
ROUTES_PUBLIQUES = {"login", "static"}

initialiser_base()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def charger_utilisateur(id_utilisateur):
    return User.depuis_ligne(utilisateur_par_id(int(id_utilisateur)))


@app.before_request
def restreindre_acces():
    connecte = current_user.is_authenticated or session.get("connecte")
    if not connecte and request.endpoint not in ROUTES_PUBLIQUES:
        return redirect(url_for("login"))


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

def nombre(valeur_brute, defaut=0):
    try:
        return float(valeur_brute)
    except (TypeError, ValueError):
        return defaut


# ============================== AUTHENTIFICATION ==============================


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

        session["connecte"] = True
        session["user_id"] = utilisateur["id"]
        session["user_name"] = utilisateur["nom"]
        session["user_email"] = utilisateur["email"]
        session["user_role"] = utilisateur["nom_role"]
        session.permanent = True
        app.permanent_session_lifetime = (
            timedelta(days=30) if se_souvenir else timedelta(hours=2)
        )

        return jsonify(
            {
                "success": True,
                "message": "Connexion réussie! Redirection...",
                "redirect": "/",
            }
        )

    if session.get("connecte"):
        return redirect(url_for("dashboard"))
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
        compteurs_salle = lectures.compteurs_salle()
        compteurs_commandes = lectures.compteurs_commandes()

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
                    "ca_jour": lectures.chiffre_affaires_jour(),
                    "ca_total": lectures.chiffre_affaires_total(),
                    "commandes_jour": compteurs_commandes["commandes_jour"],
                    "ticket_moyen": lectures.ticket_moyen_jour(),
                    "couverts_jour": lectures.couverts_jour(),
                    "tables_occupees": compteurs_salle["tables_occupees"],
                    "total_tables": compteurs_salle["total_tables"],
                    "montant_impaye": compteurs_commandes["montant_impaye"],
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


# ==================================== MENU ====================================


@app.route("/menu")
def menu():
    return render_template(
        "menu.html", active_page="menu", categories=lectures.liste_categories()
    )


@app.route("/menu/list")
def menu_list():
    articles = lectures.liste_articles()
    for article in articles:
        article["statut"] = lectures.statut_stock(article)
    return jsonify({"data": articles, "counter": lectures.compteurs_menu()})


@app.route("/menu/disponibles")
def menu_disponibles():
    return jsonify({"data": lectures.articles_disponibles()})


@app.route("/menu/add", methods=["POST"])
def menu_add():
    nom = request.form.get("nom")
    id_categorie = request.form.get("categorie")
    prix = request.form.get("prix")

    if not nom or not id_categorie or not prix:
        return jsonify(
            {"success": False, "error": "Nom, catégorie et prix sont obligatoires"}
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
    return jsonify({**resultat, "message": "Article ajouté au menu"})


@app.route("/menu/<int:id_article>/disponibilite", methods=["POST"])
def menu_disponibilite(id_article):
    disponible = request.form.get("disponible") == "1"
    return jsonify(ecritures.basculer_disponibilite(id_article, disponible))


@app.route("/menu/categorie/add", methods=["POST"])
def menu_categorie_add():
    nom = request.form.get("nom")
    if not nom:
        return jsonify({"success": False, "error": "Nom de catégorie obligatoire"}), 400

    resultat = ecritures.creer_categorie(nom, request.form.get("type") or "Cuisine")
    return jsonify(resultat), 200 if resultat["success"] else 400


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
        tables=lectures.liste_tables(),
        types_service=ecritures.TYPES_SERVICE,
    )


@app.route("/commande/list")
def commande_list():
    return jsonify(
        {
            "data": lectures.liste_commandes(),
            "counter": lectures.compteurs_commandes(),
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
        id_table=request.form.get("id_table") or None,
        type_service=request.form.get("type_service") or "Sur place",
        nom_client=request.form.get("nom_client"),
        telephone_client=request.form.get("telephone_client"),
        couverts=int(nombre(request.form.get("couverts"), 1)),
        remise=nombre(request.form.get("remise")),
        commentaire=request.form.get("commentaire"),
        articles=articles,
    )

    if not resultat["success"]:
        return jsonify(resultat), 400
    return jsonify({**resultat, "message": "Commande enregistrée avec succès"})


@app.route("/commande/<reference>")
def commande_detail(reference):
    detail = lectures.detail_commande(reference)
    if not detail:
        return jsonify({"success": False, "error": "Commande introuvable"}), 404
    return jsonify({"success": True, "data": detail})


@app.route("/commande/<reference>/statut", methods=["POST"])
def commande_statut(reference):
    resultat = ecritures.changer_statut_commande(reference, request.form.get("statut"))
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


if __name__ == "__main__":
    app.run(port=5000, debug=True)
