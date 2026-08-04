"""Fonctionnalités activables : tous les maquis n'ont pas les mêmes besoins.

Un module correspond à une page et aux endpoints qui la servent. Le désactiver
le retire du menu et ferme ses URL, exactement comme un droit refusé.

Pour ajouter une fonctionnalité plus tard : décrire le module ici, écrire sa
page, et rattacher ses endpoints dans `backend/roles.py`. La ligne manquante en
base est créée au démarrage suivant, avec la valeur `defaut`.
"""

import time

from backend.database import connexion, executer, lire_tout

MODULES = [
    {
        "cle": "dashboard",
        "libelle": "Tableau de bord",
        "description": "Recette du jour, courbe des ventes, top des articles.",
        "obligatoire": False,
        "defaut": True,
    },
    {
        "cle": "salle",
        "libelle": "Gestion de salle",
        "description": "Plan de salle, tables et zones. Inutile pour un service "
        "au comptoir ou uniquement à emporter.",
        "obligatoire": False,
        "defaut": True,
    },
    {
        "cle": "commande",
        "libelle": "Commandes",
        "description": "Prise de commande et suivi des tickets.",
        "obligatoire": True,
        "defaut": True,
    },
    {
        "cle": "maquis",
        "libelle": "Maquis",
        "description": "Carte des boissons : bières, sucreries, eaux et jus. "
        "À désactiver pour un restaurant sans bar.",
        "obligatoire": False,
        "defaut": True,
    },
    {
        "cle": "menu",
        "libelle": "Menu du restaurant",
        "description": "Carte de la nourriture : grillades, plats, accompagnements.",
        "obligatoire": True,
        "defaut": True,
    },
    {
        "cle": "stock",
        "libelle": "Stock",
        "description": "Suivi des boissons, seuils d'alerte, entrées et sorties.",
        "obligatoire": False,
        "defaut": True,
    },
    {
        "cle": "caisse",
        "libelle": "Caisse",
        "description": "Encaissements et journal de caisse.",
        "obligatoire": True,
        "defaut": True,
    },
    {
        "cle": "depense",
        "libelle": "Dépenses",
        "description": "Approvisionnements, salaires, charges.",
        "obligatoire": False,
        "defaut": True,
    },
]

CLES = {module["cle"] for module in MODULES}
OBLIGATOIRES = {module["cle"] for module in MODULES if module["obligatoire"]}
PAR_CLE = {module["cle"]: module for module in MODULES}

# L'état change rarement mais serait lu à chaque requête : on le garde en
# mémoire quelques secondes pour ne pas ajouter un aller-retour par page.
DUREE_CACHE = 30
_cache = {"valeurs": None, "expire": 0.0}


def invalider_cache():
    _cache["valeurs"] = None


def _lire_etats():
    etats = {
        ligne["cle"]: bool(ligne["actif"])
        for ligne in lire_tout("SELECT cle, actif FROM modules")
    }
    # Un module encore absent de la base garde sa valeur par défaut.
    return {module["cle"]: etats.get(module["cle"], module["defaut"]) for module in MODULES}


def etats():
    if _cache["valeurs"] is None or time.monotonic() > _cache["expire"]:
        _cache["valeurs"] = _lire_etats()
        _cache["expire"] = time.monotonic() + DUREE_CACHE
    return _cache["valeurs"]


def actifs():
    return {cle for cle, actif in etats().items() if actif}


def actif(cle):
    """Une clé inconnue n'est pas un module : elle n'est donc pas désactivable."""
    return cle not in CLES or etats().get(cle, False)


def liste():
    """Les modules et leur état, pour la page d'administration."""
    en_cours = etats()
    return [{**module, "actif": en_cours[module["cle"]]} for module in MODULES]


def basculer(cle, actif_demande):
    if cle not in CLES:
        return {"success": False, "error": "Fonctionnalité inconnue"}
    if cle in OBLIGATOIRES and not actif_demande:
        return {
            "success": False,
            "error": f"« {PAR_CLE[cle]['libelle']} » ne peut pas être désactivé",
        }

    executer(
        "UPDATE modules SET actif = %s WHERE cle = %s", (int(actif_demande), cle)
    )
    invalider_cache()
    return {"success": True, "cle": cle, "actif": actif_demande}


def initialiser():
    """Ajoute en base les modules qui n'y sont pas encore."""
    with connexion() as conn:
        conn.executemany(
            "INSERT IGNORE INTO modules (cle, actif) VALUES (%s, %s)",
            [(module["cle"], int(module["defaut"])) for module in MODULES],
        )
        conn.commit()
    invalider_cache()
