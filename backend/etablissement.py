"""L'établissement courant, et la liste des établissements de la plateforme.

Une seule base héberge plusieurs maquis. Plutôt que de passer l'identifiant en
paramètre à la cinquantaine de fonctions de `lectures` et `ecritures` — où un
oubli ferait fuiter les données d'un établissement chez un autre — il est posé
une fois par requête dans une variable de contexte, que chaque requête SQL
relit. `courant()` lève plutôt que de renvoyer `None` : une lecture non
rattachée est un bug, pas une lecture sur tout le monde.
"""

from contextvars import ContextVar

from backend.database import (
    connexion,
    executer,
    lire_tout,
    lire_un,
    message_erreur,
)

_courant = ContextVar("id_etablissement", default=None)

# Un établissement neuf part avec la structure de carte d'un maquis ivoirien.
# Sans elle, le gérant tombe sur une carte vide et doit inventer ses rubriques
# avant de pouvoir saisir le moindre article. Le partage Bar / Cuisine est celui
# qui sépare la page Maquis de la page Menu ; les rubriques se renomment, se
# suppriment et se complètent ensuite.
CATEGORIES_PAR_DEFAUT = [
    ("Grillades", "Cuisine"),
    ("Plats & Sauces", "Cuisine"),
    ("Accompagnements", "Cuisine"),
    ("Bières", "Bar"),
    ("Sucreries", "Bar"),
    ("Eaux & Jus", "Bar"),
]


def definir(id_etablissement):
    """Rattache le traitement en cours à un établissement (None pour aucun)."""
    _courant.set(int(id_etablissement) if id_etablissement else None)


def courant():
    id_etablissement = _courant.get()
    if id_etablissement is None:
        raise RuntimeError(
            "Aucun établissement dans le contexte : appelez "
            "etablissement.definir() avant toute lecture ou écriture."
        )
    return id_etablissement


def courant_ou_none():
    """Pour les rares appelants qui doivent composer avec l'absence (plateforme)."""
    return _courant.get()


# ----------------------------------------------------------------------------
# Gestion de la plateforme
# ----------------------------------------------------------------------------


def liste():
    """Tous les établissements, avec de quoi juger de leur activité."""
    return lire_tout(
        """
        SELECT e.id, e.nom, e.ville, e.telephone, e.actif, e.date_creation,
               (SELECT COUNT(*) FROM utilisateurs u
                 WHERE u.id_etablissement = e.id) AS comptes,
               (SELECT COUNT(*) FROM commandes c
                 WHERE c.id_etablissement = e.id) AS commandes,
               (SELECT COALESCE(SUM(p.montant), 0) FROM paiements p
                 WHERE p.id_etablissement = e.id) AS encaisse
        FROM etablissements e
        ORDER BY e.id
        """
    )


def par_id(id_etablissement):
    return lire_un(
        "SELECT id, nom, ville, telephone, actif FROM etablissements WHERE id = %s",
        (id_etablissement,),
    )


def creer(nom, ville=None, telephone=None):
    """Crée l'établissement, ses fonctionnalités et sa carte de départ.

    Tout se fait dans la même transaction : un établissement à moitié équipé —
    sans fonctionnalité ou sans catégorie — serait plus embêtant à rattraper
    qu'une création franchement refusée.
    """
    from backend import modules

    if not nom or not nom.strip():
        return {"success": False, "error": "Le nom de l'établissement est obligatoire"}

    try:
        with connexion() as conn:
            id_etablissement = conn.execute(
                "INSERT INTO etablissements (nom, ville, telephone) VALUES (%s, %s, %s)",
                (nom.strip(), ville or None, telephone or None),
            ).lastrowid
            conn.executemany(
                "INSERT INTO categories (id_etablissement, nom, type) VALUES (%s, %s, %s)",
                [
                    (id_etablissement, categorie, type_categorie)
                    for categorie, type_categorie in CATEGORIES_PAR_DEFAUT
                ],
            )
            conn.commit()
        modules.initialiser(id_etablissement)
        return {"success": True, "id_etablissement": id_etablissement}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}


def basculer(id_etablissement, actif):
    """Suspend ou rouvre un établissement ; ses comptes suivent à la connexion."""
    try:
        executer(
            "UPDATE etablissements SET actif = %s WHERE id = %s",
            (1 if actif else 0, int(id_etablissement)),
        )
        return {"success": True}
    except Exception as erreur:
        return {"success": False, "error": message_erreur(erreur)}
