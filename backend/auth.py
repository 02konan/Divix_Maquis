from werkzeug.security import check_password_hash, generate_password_hash

from backend.database import executer, lire_un

# L'établissement du compte est ramené avec lui : c'est lui qui cadre toutes les
# lectures de la session. `etablissement_actif` distingue le compte plateforme,
# qui n'en a pas, d'un compte dont l'établissement a été suspendu.
REQUETE_UTILISATEUR = """
    SELECT utilisateurs.id, utilisateurs.nom, utilisateurs.email,
           utilisateurs.mot_de_passe, utilisateurs.id_role,
           utilisateurs.id_etablissement, roles.nom AS nom_role,
           e.nom AS nom_etablissement,
           COALESCE(e.actif, 1) AS etablissement_actif
    FROM utilisateurs
    JOIN roles ON utilisateurs.id_role = roles.id
    LEFT JOIN etablissements e ON utilisateurs.id_etablissement = e.id
    WHERE {condition} AND utilisateurs.actif = 1
"""


def authentifier(email, mot_de_passe):
    ligne = lire_un(
        REQUETE_UTILISATEUR.format(condition="utilisateurs.email = %s"), (email,)
    )
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


def creer_utilisateur(nom, email, mot_de_passe, id_role, id_etablissement):
    return executer(
        """INSERT INTO utilisateurs (nom, email, mot_de_passe, id_role, id_etablissement)
           VALUES (%s, %s, %s, %s, %s)""",
        (nom, email, generate_password_hash(mot_de_passe), id_role, id_etablissement),
    )
