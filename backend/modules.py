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
        "cle": "serveur",
        "libelle": "Serveurs",
        "description": "Comptes de service pour les serveurs, qui prennent la "
        "commande depuis leur téléphone. À désactiver là où c'est le caissier "
        "qui saisit tout : les rôles serveur ne sont alors plus attribuables et "
        "les comptes existants ne peuvent plus se connecter, sans rien perdre "
        "de leur historique.",
        "obligatoire": False,
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
DEFAUTS = {module["cle"]: module["defaut"] for module in MODULES}

# L'état change rarement mais serait lu à chaque requête : on le garde en
# mémoire quelques secondes pour ne pas ajouter un aller-retour par page.
# Un jeu de valeurs par établissement, puisque chacun a ses fonctionnalités.
DUREE_CACHE = 30
_cache = {}


def invalider_cache():
    _cache.clear()


def _lire_etats(id_etablissement):
    etats = {
        ligne["cle"]: bool(ligne["actif"])
        for ligne in lire_tout(
            "SELECT cle, actif FROM modules WHERE id_etablissement = %s",
            (id_etablissement,),
        )
    }
    # Un module encore absent de la base garde sa valeur par défaut.
    return {cle: etats.get(cle, defaut) for cle, defaut in DEFAUTS.items()}


def etats():
    """État des fonctionnalités de l'établissement courant.

    Hors établissement — page de connexion, compte plateforme — on rend les
    valeurs par défaut plutôt que de lever : ces pages ne dépendent d'aucune
    fonctionnalité, mais le gabarit commun demande quand même le menu.
    """
    from backend.etablissement import courant_ou_none

    id_etablissement = courant_ou_none()
    if id_etablissement is None:
        return dict(DEFAUTS)

    entree = _cache.get(id_etablissement)
    if entree is None or time.monotonic() > entree["expire"]:
        entree = {
            "valeurs": _lire_etats(id_etablissement),
            "expire": time.monotonic() + DUREE_CACHE,
        }
        _cache[id_etablissement] = entree
    return entree["valeurs"]


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
    from backend.etablissement import courant

    if cle not in CLES:
        return {"success": False, "error": "Fonctionnalité inconnue"}
    if cle in OBLIGATOIRES and not actif_demande:
        return {
            "success": False,
            "error": f"« {PAR_CLE[cle]['libelle']} » ne peut pas être désactivé",
        }

    # ON DUPLICATE plutôt qu'un UPDATE : un module ajouté au logiciel après la
    # création de l'établissement n'a pas encore sa ligne.
    executer(
        """INSERT INTO modules (id_etablissement, cle, actif) VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE actif = VALUES(actif)""",
        (courant(), cle, int(actif_demande)),
    )
    invalider_cache()
    return {"success": True, "cle": cle, "actif": actif_demande}


def initialiser(id_etablissement=None):
    """Ajoute les modules qui manquent, pour un établissement ou pour tous.

    Sans argument, sert au démarrage : un module ajouté au logiciel doit
    apparaître chez les établissements déjà en service.
    """
    with connexion() as conn:
        if id_etablissement is None:
            cibles = [
                ligne["id"]
                for ligne in conn.execute("SELECT id FROM etablissements").fetchall()
            ]
        else:
            cibles = [id_etablissement]

        conn.executemany(
            "INSERT IGNORE INTO modules (id_etablissement, cle, actif) VALUES (%s, %s, %s)",
            [
                (cible, module["cle"], int(module["defaut"]))
                for cible in cibles
                for module in MODULES
            ],
        )
        conn.commit()
    invalider_cache()
