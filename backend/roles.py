"""Droits d'accès : quelles pages chaque rôle peut ouvrir, et y modifier quoi.

Le contrôle se fait par endpoint Flask, donc il couvre d'un seul coup les pages
et les endpoints JSON qu'elles appellent : masquer une entrée du menu ne suffit
pas, l'URL reste tapable à la main.
"""

# Ordre d'affichage dans le menu. La première page autorisée sert d'accueil.
PAGES = [
    {"cle": "dashboard", "url": "/", "libelle": "Dashboard", "icone": "bxf bx-layers"},
    {"cle": "salle", "url": "/salle", "libelle": "Salle", "icone": "bxf bx-grid-alt"},
    {"cle": "commande", "url": "/commande", "libelle": "Commandes", "icone": "bxf bx-receipt"},
    {"cle": "menu", "url": "/menu", "libelle": "Menu", "icone": "bxf bx-restaurant"},
    {"cle": "stock", "url": "/stock", "libelle": "Stock", "icone": "bxf bx-package"},
    {"cle": "caisse", "url": "/caisse", "libelle": "Caisse", "icone": "bx bx-currency-notes"},
    {"cle": "depense", "url": "/depense", "libelle": "Dépenses", "icone": "bxf bx-wallet"},
]

TOUTES_LES_PAGES = {page["cle"] for page in PAGES}

PAGES_PAR_ROLE = {
    "Gérant": TOUTES_LES_PAGES,
    "Caissier": {"salle", "commande", "caisse"},
    "Serveur": {"salle", "commande", "menu"},
}

# Pages consultables sans pouvoir y écrire : le serveur voit la carte et les
# prix, mais ne crée ni article ni catégorie.
LECTURE_SEULE_PAR_ROLE = {
    "Serveur": {"menu"},
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
    "menu": "menu",
    "menu_list": "menu",
    "menu_add": "menu",
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
}

ENDPOINTS_PUBLICS = {"login", "static"}
ENDPOINTS_TOUJOURS_AUTORISES = {"logout"}

# Endpoints qui rendent une page : un refus s'y traduit par une redirection
# plutôt que par du JSON.
ENDPOINTS_HTML = {page["cle"] for page in PAGES} | {"commande"}


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

    page = PAGE_PAR_ENDPOINT.get(endpoint)
    if page is None or page not in pages_autorisees(role):
        return False
    if methode != "GET" and page in LECTURE_SEULE_PAR_ROLE.get(role, set()):
        return False
    return True
