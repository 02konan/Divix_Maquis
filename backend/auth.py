from werkzeug.security import check_password_hash, generate_password_hash

from backend.database import executer, lire_un

REQUETE_UTILISATEUR = """
    SELECT utilisateurs.id, utilisateurs.nom, utilisateurs.email,
           utilisateurs.mot_de_passe, utilisateurs.id_role, roles.nom AS nom_role
    FROM utilisateurs
    JOIN roles ON utilisateurs.id_role = roles.id
    WHERE {condition} AND actif = 1
"""


def authentifier(email, mot_de_passe):
    """Renvoie l'utilisateur si les identifiants sont valides, sinon None."""
    ligne = lire_un(REQUETE_UTILISATEUR.format(condition="email = %s"), (email,))
    if not ligne or not check_password_hash(ligne["mot_de_passe"], mot_de_passe):
        return None
    ligne.pop("mot_de_passe")
    return ligne


def utilisateur_par_id(id_utilisateur):
    ligne = lire_un(
        REQUETE_UTILISATEUR.format(condition="utilisateurs.id = %s"), (id_utilisateur,)
    )
    if ligne:
        ligne.pop("mot_de_passe")
    return ligne


def creer_utilisateur(nom, email, mot_de_passe, id_role):
    return executer(
        """INSERT INTO utilisateurs (nom, email, mot_de_passe, id_role)
           VALUES (%s, %s, %s, %s)""",
        (nom, email, generate_password_hash(mot_de_passe), id_role),
    )
