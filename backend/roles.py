"""Droits d'accès : quelles pages chaque rôle peut ouvrir, et y modifier quoi.

Le contrôle se fait par endpoint Flask, donc il couvre d'un seul coup les pages
et les endpoints JSON qu'elles appellent : masquer une entrée du menu ne suffit
pas, l'URL reste tapable à la main.
"""

# Ordre d'affichage dans le menu. La première page autorisée sert d'accueil.
PAGES = [
    {"cle": "dashboard", "url": "/", "libelle": "Dashboard", "icone": "bxf bx-layers"},
    {"cle": "salle", "url": "/salle", "libelle": "Salle", "icone": "bxf bx-grid"},
    {"cle": "commande", "url": "/commande", "libelle": "Commandes", "icone": "bxf bx-receipt"},
    {"cle": "maquis", "url": "/maquis", "libelle": "Maquis", "icone": "bxf bx-beer"},
    {"cle": "menu", "url": "/menu", "libelle": "Menu", "icone": "bxf bx-fork-knife"},
    {"cle": "stock", "url": "/stock", "libelle": "Stock", "icone": "bxf bx-package"},
    {"cle": "caisse", "url": "/caisse", "libelle": "Caisse", "icone": "bx bx-currency-notes"},
    {"cle": "depense", "url": "/depense", "libelle": "Dépenses", "icone": "bxf bx-wallet"},
    {"cle": "administration", "url": "/administration", "libelle": "Administration", "icone": "bxf bx-cog"},
    {"cle": "plateforme", "url": "/plateforme", "libelle": "Établissements", "icone": "bxf bx-buildings"},
]

TOUTES_LES_PAGES = {page["cle"] for page in PAGES}

# La console plateforme voit tous les établissements : elle est hors du logiciel
# que loue chaque maquis, et le gérant n'y a donc pas accès.
PAGES_ETABLISSEMENT = TOUTES_LES_PAGES - {"plateforme"}

PAGES_PAR_ROLE = {
    "Administrateur plateforme": {"plateforme"},
    # Seul le gérant administre les fonctionnalités et les comptes.
    "Gérant": PAGES_ETABLISSEMENT,
    "Caissier": {"salle", "commande", "caisse"},
    "Serveur": {"salle", "commande", "maquis", "menu"},
    "Serveur bar": {"salle", "commande", "maquis"},
    "Serveur restaurant": {"salle", "commande", "menu"},
}

# Rôles qui n'existent que si l'établissement travaille avec des serveurs
# connectés. La fonctionnalité « serveur » désactivée, ils ne sont plus
# attribuables et leurs comptes sont refusés à la connexion.
ROLES_SERVEUR = {"Serveur", "Serveur bar", "Serveur restaurant"}

# Rôle réservé à l'éditeur : il n'appartient à aucun établissement et n'est
# jamais proposé dans la gestion des comptes d'un maquis.
ROLE_PLATEFORME = "Administrateur plateforme"

# La carte est coupée en deux pages : le maquis sert la boisson, le menu la
# nourriture. Le partage suit le type des catégories, déjà porté par la base.
DOMAINE_PAR_PAGE = {
    "maquis": ("Bar",),
    "menu": ("Cuisine",),
}

# Le maquis et le restaurant ont des serveurs distincts : les uns servent la
# boisson, les autres la nourriture. Le partage suit le type des catégories,
# déjà porté par la base (« Bar » ou « Cuisine »). Un rôle absent de ce tableau
# n'est pas cloisonné et voit toute la carte.
DOMAINES_PAR_ROLE = {
    "Serveur bar": ("Bar",),
    "Serveur restaurant": ("Cuisine",),
}

# Pages consultables sans pouvoir y écrire : le serveur voit la carte et les
# prix, mais ne crée ni article ni catégorie.
LECTURE_SEULE_PAR_ROLE = {
    "Serveur": {"maquis", "menu"},
    "Serveur bar": {"maquis"},
    "Serveur restaurant": {"menu"},
}

# Chaque endpoint est rattaché à la page dont il dépend. `menu_disponibles`
# appartient à « commande » : c'est le sélecteur d'articles de la prise de
# commande, dont un caissier a besoin sans avoir accès à la carte.
PAGE_PAR_ENDPOINT = {
    "dashboard": "dashboard",
    "dashboard_data": "dashboard",
    "salle": "salle",
    "salle_list": "salle",
    "salle_add": "salle",
    "salle_statut": "salle",
    "commande": "commande",
    "commande_list": "commande",
    "commande_add": "commande",
    "commande_detail": "commande",
    "commande_statut": "commande",
    "menu_disponibles": "commande",
    "maquis": "maquis",
    "maquis_list": "maquis",
    "maquis_add": "maquis",
    "maquis_modifier": "maquis",
    "maquis_disponibilite": "maquis",
    "maquis_categorie_add": "maquis",
    "menu": "menu",
    "menu_list": "menu",
    "menu_add": "menu",
    "menu_modifier": "menu",
    "menu_disponibilite": "menu",
    "menu_categorie_add": "menu",
    "stock": "stock",
    "stock_list": "stock",
    "stock_mouvement": "stock",
    "caisse": "caisse",
    "caisse_list": "caisse",
    "caisse_encaissables": "caisse",
    "caisse_add": "caisse",
    "depense": "depense",
    "depense_list": "depense",
    "depense_add": "depense",
    "administration": "administration",
    "administration_modules": "administration",
    "administration_utilisateur_add": "administration",
    "administration_utilisateur_actif": "administration",
    "administration_utilisateur_role": "administration",
    "administration_utilisateur_motdepasse": "administration",
    "plateforme": "plateforme",
    "plateforme_list": "plateforme",
    "plateforme_add": "plateforme",
    "plateforme_actif": "plateforme",
}

# Écritures qui relèvent de la gestion de l'établissement, pas du service :
# un serveur n'a pas à créer des tables.
ENDPOINTS_GESTION = {"salle_add"}
ROLES_GESTION = {"Gérant"}

ENDPOINTS_PUBLICS = {"login", "inscription", "static"}
ENDPOINTS_TOUJOURS_AUTORISES = {"logout"}

# Endpoints qui rendent une page : un refus s'y traduit par une redirection
# plutôt que par du JSON.
ENDPOINTS_HTML = {page["cle"] for page in PAGES} | {"commande"}


def initialiser():
    """Crée en base les rôles déclarés ici qui n'y sont pas encore.

    Une base déjà en service ne connaît pas les rôles ajoutés depuis : sans
    cela, le gérant ne pourrait pas les attribuer à ses employés.
    """
    from backend.database import connexion

    with connexion() as conn:
        conn.executemany(
            "INSERT IGNORE INTO roles (nom) VALUES (%s)",
            [(nom,) for nom in PAGES_PAR_ROLE],
        )
        conn.commit()


def roles_attribuables(serveurs_actifs=True):
    """Rôles qu'un gérant peut donner à ses employés.

    Le rôle plateforme n'en fait jamais partie, et les rôles serveur
    disparaissent là où l'établissement travaille sans serveur connecté.
    """
    exclus = {ROLE_PLATEFORME} | (set() if serveurs_actifs else ROLES_SERVEUR)
    return [nom for nom in PAGES_PAR_ROLE if nom not in exclus]


def domaines(role):
    """Types de catégories que le rôle peut voir et commander ; None = tout."""
    return DOMAINES_PAR_ROLE.get(role)


def domaine_page(page):
    """Types de catégories présentés par une page de carte."""
    return DOMAINE_PAR_PAGE.get(page)


def pages_autorisees(role):
    """Un rôle inconnu n'a accès à rien : mieux vaut fermer que d'ouvrir par défaut."""
    return PAGES_PAR_ROLE.get(role, set())


def menu(role):
    autorisees = pages_autorisees(role)
    return [page for page in PAGES if page["cle"] in autorisees]


def page_accueil(role):
    pages = menu(role)
    return pages[0]["url"] if pages else "/logout"


def acces_autorise(role, endpoint, methode="GET"):
    if endpoint in ENDPOINTS_TOUJOURS_AUTORISES:
        return True
    if endpoint in ENDPOINTS_GESTION and role not in ROLES_GESTION:
        return False

    page = PAGE_PAR_ENDPOINT.get(endpoint)
    if page is None or page not in pages_autorisees(role):
        return False
    if methode != "GET" and page in LECTURE_SEULE_PAR_ROLE.get(role, set()):
        return False
    return True
