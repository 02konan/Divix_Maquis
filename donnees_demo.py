"""Installe les données dont le logiciel a besoin pour fonctionner.

Rien de plus : ni maquis fictif, ni carte d'exemple, ni commandes inventées. Ce
script prépare une base neuve avant la première mise en service, et se relance
sans risque — il n'ajoute que ce qui manque.

    python donnees_demo.py

Trois jeux de données font tourner le logiciel :

- **les rôles** (`backend/roles.py`) — créés ici et à chaque démarrage de
  l'application, pour qu'un rôle ajouté à une version ultérieure apparaisse dans
  les bases déjà en service ;
- **les catégories** (`backend/etablissement.py`) — elles appartiennent à un
  établissement, elles ne peuvent donc pas exister avant lui : chaque maquis
  reçoit sa carte de départ à sa création, qu'il vienne du formulaire
  d'inscription ou de la console de l'éditeur ;
- **les modes de paiement** (`backend/ecritures.py`) — une liste fermée, la même
  pour tout le monde, que la caisse propose et que le serveur revérifie à
  l'encaissement.

Les deux derniers ne se posent donc pas en base ici : le premier suit
l'établissement, le second est porté par le code. Ce script les affiche pour
qu'on sache ce qui sera en place.

Le reste — établissements, comptes, articles — se crée depuis l'interface :
`/inscription` pour un maquis et son gérant, `/support` pour le compte de
l'éditeur.
"""

from backend import roles
from backend.database import initialiser_base, lire_tout
from backend.ecritures import MODES_PAIEMENT
from backend.etablissement import CATEGORIES_PAR_DEFAUT


def peupler():
    """Crée le schéma s'il manque, puis les rôles qui n'y sont pas encore."""
    initialiser_base()
    roles.initialiser()

    en_base = [ligne["nom"] for ligne in lire_tout("SELECT nom FROM roles ORDER BY id")]

    print(f"Base prête. {len(en_base)} rôles :")
    for nom in en_base:
        print(f"  · {nom}")

    print(f"\n{len(CATEGORIES_PAR_DEFAUT)} catégories par établissement, à sa création :")
    for nom, type_categorie in CATEGORIES_PAR_DEFAUT:
        print(f"  · {nom} ({type_categorie})")

    print(f"\n{len(MODES_PAIEMENT)} modes de paiement : {', '.join(MODES_PAIEMENT)}")

    print("\nPour ouvrir un premier maquis : /inscription")
    print("Pour le compte de l'éditeur : /support, ou")
    print("python outils/creer_compte_plateforme.py")


if __name__ == "__main__":
    peupler()
