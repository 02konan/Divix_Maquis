"""Crée le compte de l'éditeur, celui qui ouvre la console des établissements.

Ce compte ne peut pas se créer depuis l'interface, et c'est voulu : le rôle
« Administrateur plateforme » n'est pas attribuable depuis la page
Administration d'un maquis, sans quoi un gérant se hisserait au niveau de
l'éditeur. Il faut donc une porte d'entrée en dehors du logiciel — la voici.

    python outils/creer_compte_plateforme.py
    python outils/creer_compte_plateforme.py --email support@divix.ci

Le script se connecte à la base désignée par les variables d'environnement
habituelles (DB_HOST, DB_USER, DB_PASSWORD, DATABASE), comme l'application.
Sur un hébergeur, lancez-le depuis le shell du service : il y trouvera la même
configuration.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import roles  # noqa: E402
from backend.auth import creer_utilisateur  # noqa: E402
from backend.database import initialiser_base, lire_un, message_erreur  # noqa: E402
from backend.ecritures import LONGUEUR_MOT_DE_PASSE  # noqa: E402


def demander(question, valeur=None):
    while not valeur:
        valeur = input(f"{question} : ").strip()
    return valeur


def demander_mot_de_passe():
    while True:
        # getpass plutôt qu'un argument : un mot de passe passé en ligne de
        # commande reste dans l'historique du shell et dans la liste des
        # processus, où n'importe qui sur la machine peut le lire.
        mot_de_passe = getpass.getpass("Mot de passe : ")
        if len(mot_de_passe) < LONGUEUR_MOT_DE_PASSE:
            print(f"  → au moins {LONGUEUR_MOT_DE_PASSE} caractères, recommencez.")
            continue
        if mot_de_passe != getpass.getpass("Confirmez le mot de passe : "):
            print("  → les deux saisies diffèrent, recommencez.")
            continue
        return mot_de_passe


def main():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--nom", help="Nom affiché du compte")
    analyseur.add_argument("--email", help="Adresse de connexion")
    arguments = analyseur.parse_args()

    # Le rôle est créé au démarrage de l'application ; sur une base qui n'a
    # jamais servi, il faut l'y mettre nous-mêmes.
    initialiser_base()
    roles.initialiser()

    nom = demander("Nom affiché", arguments.nom)
    email = demander("Adresse email", arguments.email)

    if lire_un("SELECT id FROM utilisateurs WHERE email = %s", (email,)):
        print(f"\nUn compte utilise déjà {email}.")
        return 1

    mot_de_passe = demander_mot_de_passe()

    ligne = lire_un("SELECT id FROM roles WHERE nom = %s", (roles.ROLE_PLATEFORME,))
    if not ligne:
        print(f"\nLe rôle « {roles.ROLE_PLATEFORME} » est introuvable en base.")
        return 1

    try:
        # id_etablissement à None : ce compte n'appartient à aucun maquis, ce
        # qui lui ferme toutes les pages de service et n'ouvre que la console.
        creer_utilisateur(nom, email, mot_de_passe, ligne["id"], None)
    except Exception as erreur:  # noqa: BLE001 - message lisible plutôt qu'une trace
        print(f"\nCréation impossible : {message_erreur(erreur)}")
        return 1

    print(f"\nCompte plateforme créé pour {email}.")
    print("Connectez-vous avec : vous arriverez sur /plateforme.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
