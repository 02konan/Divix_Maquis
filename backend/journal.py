"""Journal des actions : qui a fait quoi, et quand.

Le journal se remplit tout seul, depuis un crochet posé sur les réponses de
l'application : chaque écriture réussie y laisse une ligne, sans que la route
concernée ait à y penser. Ajouter une écriture au logiciel ne peut donc pas
« oublier » de se journaliser — il suffit de lui donner un libellé ici.

Une action sans libellé n'est pas journalisée : c'est ainsi qu'on écarte le
bruit (consultations, appels de données) sans avoir à l'énumérer.
"""

from backend.database import executer, lire_tout, lire_un, message_erreur
from backend.etablissement import courant_ou_none

# Endpoint Flask → ce que le gérant lira dans le journal. Les endpoints absents
# ne sont pas journalisés.
LIBELLES = {
    "login": "Connexion",
    "salle_add": "Table créée",
    "salle_statut": "Table changée d'état",
    "commande_add": "Commande enregistrée",
    "commande_statut": "Commande changée d'état",
    "maquis_add": "Article ajouté au maquis",
    "maquis_modifier": "Article du maquis modifié",
    "maquis_disponibilite": "Disponibilité changée au maquis",
    "maquis_categorie_add": "Catégorie de maquis créée",
    "menu_add": "Article ajouté au menu",
    "menu_modifier": "Article du menu modifié",
    "menu_disponibilite": "Disponibilité changée au menu",
    "menu_categorie_add": "Catégorie de menu créée",
    "stock_mouvement": "Mouvement de stock",
    "caisse_add": "Encaissement",
    "depense_add": "Dépense enregistrée",
    "administration_modules": "Fonctionnalité basculée",
    "administration_utilisateur_add": "Compte créé",
    "administration_utilisateur_actif": "Compte activé ou désactivé",
    "administration_utilisateur_role": "Rôle d'un compte modifié",
    "administration_utilisateur_motdepasse": "Mot de passe réinitialisé",
}

# Champs qu'on ne recopie jamais dans le journal, même haché : un journal
# consultable ne doit pas devenir une liste de secrets.
CHAMPS_SECRETS = ("mot_de_passe", "password", "motdepasse")

LONGUEUR_DETAILS = 500


def journalisable(action):
    return action in LIBELLES


def resumer(formulaire):
    """Résumé lisible d'un formulaire, sans les secrets ni les pavés."""
    morceaux = []
    for champ, valeur in formulaire.items():
        if any(secret in champ.lower() for secret in CHAMPS_SECRETS):
            continue
        valeur = " ".join(str(valeur).split())
        if not valeur:
            continue
        if len(valeur) > 80:
            valeur = valeur[:77] + "…"
        morceaux.append(f"{champ} : {valeur}")
    resume = " · ".join(morceaux)
    return resume[:LONGUEUR_DETAILS] or None


def enregistrer(action, utilisateur, cible=None, details=None):
    """Pose une ligne dans le journal de l'établissement courant.

    Ne lève jamais : une action réussie ne doit pas être annoncée comme
    échouée parce que sa trace n'a pas pu s'écrire. L'échec part dans les
    journaux techniques, où il reste trouvable.
    """
    id_etablissement = courant_ou_none()
    if id_etablissement is None or not journalisable(action):
        return

    try:
        executer(
            """INSERT INTO journal_actions
               (id_etablissement, id_utilisateur, nom_utilisateur, role_utilisateur,
                action, libelle, cible, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                id_etablissement,
                utilisateur.get("id"),
                utilisateur.get("nom") or "—",
                utilisateur.get("role") or "—",
                action,
                LIBELLES[action],
                (cible or None) and str(cible)[:190],
                details,
            ),
        )
    except Exception as erreur:  # noqa: BLE001 - la trace ne doit rien casser
        from backend.database import journal as journal_technique

        journal_technique.warning("Journal des actions : %s", message_erreur(erreur))


def liste(limite=300):
    from backend.etablissement import courant

    return lire_tout(
        """
        SELECT id, nom_utilisateur, role_utilisateur, action, libelle, cible,
               details, date_action
        FROM journal_actions
        WHERE id_etablissement = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (courant(), limite),
    )


def compteurs():
    from backend.etablissement import courant

    return lire_un(
        """
        SELECT COUNT(*) AS actions_total,
               COALESCE(SUM(date_action >= CURDATE()
                            AND date_action < CURDATE() + INTERVAL 1 DAY), 0)
                   AS actions_jour,
               COUNT(DISTINCT nom_utilisateur) AS auteurs
        FROM journal_actions
        WHERE id_etablissement = %s
        """,
        (courant(),),
    )


def libelles_utilises():
    """Libellés présents dans le journal, pour alimenter le filtre de la page."""
    from backend.etablissement import courant

    return [
        ligne["libelle"]
        for ligne in lire_tout(
            """SELECT DISTINCT libelle FROM journal_actions
               WHERE id_etablissement = %s ORDER BY libelle""",
            (courant(),),
        )
    ]
