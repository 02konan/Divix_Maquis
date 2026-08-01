# Divix Maquis

Application de gestion de maquis et restaurant : prise de commande en salle, carte,
stock des boissons, caisse et dépenses.

L'interface reprend intégralement celle de **Divix SysPaie** (mêmes feuilles de style,
même structure de pages, mêmes composants). Seul le backend a été remplacé : le métier
« ventes à crédit » a laissé la place au métier « restauration ». Les données sont
stockées dans **MySQL** (MySQL ≥ 8.0.13 ou MariaDB ≥ 10.2).

## Démarrage

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

# créer un fichier .env avec les variables ci-dessous
python donnees_demo.py             # crée la base + un jeu de démonstration
python app.py                      # http://127.0.0.1:5000
```

Pour le rechargement automatique pendant le développement : `FLASK_DEBUG=1 python app.py`
(le mode debug est désactivé par défaut, il ouvrirait une console d'exécution à distance).

L'application crée elle-même la base (`CREATE DATABASE IF NOT EXISTS`) et les tables au
démarrage : il suffit que le serveur MySQL soit joignable et que l'utilisateur ait le
droit de créer une base. Connexion configurée par variables d'environnement :

| Variable            | Défaut         | Rôle |
|---------------------|----------------|------|
| `DB_HOST`           | `localhost`    | Hôte du serveur |
| `DB_PORT`           | `3306`         | Port (un MySQL managé n'écoute pas toujours sur 3306) |
| `DB_USER`           | —              | Utilisateur |
| `DB_PASSWORD`       | *(vide)*       | Mot de passe |
| `DATABASE`          | `divix_maquis` | Nom de la base |
| `MYSQL_UNIX_SOCKET` | —              | Socket Unix, au lieu d'une connexion TCP |
| `PORT`              | `5000`         | Port d'écoute de l'application |

Comptes de démonstration :

| Rôle     | Email                      | Mot de passe |
|----------|----------------------------|--------------|
| Gérant   | `admin@divixmaquis.ci`     | `admin123`   |
| Caissier | `caisse@divixmaquis.ci`    | `caisse123`  |
| Serveur  | `serveur@divixmaquis.ci`   | `serveur123` |

> Changez ces mots de passe avant toute mise en production, et définissez `SECRET_KEY`
> dans le fichier `.env`.

## Fonctionnalités activables

Tous les maquis n'ont pas les mêmes besoins : un service au comptoir n'a que faire
d'un plan de salle. La page **Administration**, réservée au gérant, active ou
désactive chaque fonctionnalité :

| Fonctionnalité | Désactivable |
|----------------|--------------|
| Tableau de bord, Gestion de salle, Stock, Dépenses | oui |
| Commandes, Carte, Caisse | non — cœur du logiciel |

Une fonctionnalité désactivée disparaît du menu **et** ses URL sont fermées (`403`
sur les appels de données), pour tout le monde, gérant compris. Les données déjà
saisies sont conservées et réapparaissent telles quelles à la réactivation.

Désactiver la gestion de salle retire aussi le choix de table dans la prise de
commande — une table envoyée par un formulaire forgé est ignorée — et remplace la
carte « Tables occupées » du tableau de bord par le reste à encaisser.

Pour ajouter une fonctionnalité plus tard : la décrire dans `backend/modules.py`,
écrire sa page, rattacher ses endpoints dans `backend/roles.py`. La ligne en base
est créée au démarrage suivant. L'état est relu au plus toutes les 30 secondes,
donc un basculement peut mettre ce délai à se propager aux autres workers gunicorn.

## Droits par rôle

| | Dashboard | Salle | Commandes | Menu | Stock | Caisse | Dépenses |
|---|---|---|---|---|---|---|---|
| **Gérant**   | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| | *(et la page Administration)* | | | | | | |
| **Caissier** | — | ✓ | ✓ | — | — | ✓ | — |
| **Serveur**  | — | ✓ | ✓ | lecture | — | — | — |

La répartition se lit et se modifie dans `backend/roles.py`. Le contrôle porte sur les
endpoints Flask, donc il couvre les pages **et** les appels de données qu'elles font :
retirer une entrée du menu ne protège rien, l'URL reste tapable à la main. Une page
interdite renvoie l'utilisateur sur sa page d'accueil, un appel de données répond `403`.

Le menu latéral est construit à partir des pages autorisées, et chacun arrive après
connexion sur sa première page autorisée. Un rôle absent du tableau n'a accès à rien.

## Les pages

| Page          | Rôle |
|---------------|------|
| **Dashboard** | Recette du jour, commandes, ticket moyen, tables occupées, courbe des 7 derniers jours, top ventes |
| **Salle**     | Plan de salle par zone (Salle, Terrasse, Bar, VIP), état des tables, ticket en cours |
| **Commandes** | Prise de commande (recherche d'articles, panier, remise), suivi des tickets, détail et ticket imprimable |
| **Menu**      | Carte du maquis : plats, grillades et boissons, prix, marge, disponibilité |
| **Stock**     | Stock des boissons, seuils d'alerte, entrées/sorties/pertes/inventaires |
| **Caisse**    | Encaissements totaux ou partiels, répartition par mode de paiement, journal de caisse |
| **Dépenses**  | Approvisionnements, salaires, loyer, charges |

## Organisation du code

```
divix_maquis/
├── app.py                  routes Flask uniquement (validation + JSON)
├── backend/
│   ├── schema.sql          schéma MySQL
│   ├── database.py         connexion et helpers de requête
│   ├── auth.py             authentification (mots de passe hachés)
│   ├── models.py           utilisateur Flask-Login
│   ├── lectures.py         toutes les lectures (listes, compteurs, dashboard)
│   └── ecritures.py        toutes les écritures (commandes, caisse, stock, dépenses)
├── donnees_demo.py         initialisation + jeu de démonstration
├── templates/              interface reprise de Divix SysPaie
├── static/css/             admin.css, login.css, table-mobile.css (identiques) + maquis.css
└── static/js/              commun.js (helpers partagés) + un script par page
```

Deux règles structurent le backend :

- **Les prix ne viennent jamais du formulaire.** `creer_commande` relit le prix de chaque
  article en base avant de calculer le total, ce qui évite qu'un client modifie le montant.
- **Le stock et la salle suivent la commande.** Une commande décrémente le stock des
  boissons et occupe la table ; un ticket soldé ou annulé libère la table automatiquement.

## Modèle de données

`roles`, `utilisateurs`, `tables_salle`, `categories`, `articles`, `commandes`,
`lignes_commande`, `paiements`, `mouvements_stock`, `depenses`, `compteurs`,
`modules`.

`compteurs` porte la numérotation des références (`CMD-0001`, `PAI-0002`, ...) :
le numéro est attribué sous verrou, sinon deux commandes prises au même instant
reçoivent la même référence et l'une des deux est refusée. Pour la même raison,
la lecture du stock d'un article et celle du reste à payer d'un ticket se font
en `SELECT ... FOR UPDATE`.

Un article porte un indicateur `gere_stock` : les boissons sont décomptées à la vente,
les plats sont préparés à la commande et ne consomment pas de stock.

## Tests

```bash
pip install -r dev-requirements.txt
python -m pytest tests/
```

Les tests créent puis suppriment une base `divix_maquis_test` sur le serveur configuré
(les mêmes variables `DB_*` qu'en développement). Si aucun serveur MySQL n'est
joignable, ils sont ignorés (`skipped`) plutôt qu'en échec.

Les tests couvrent l'authentification, l'accès aux pages, les endpoints JSON, la
décrémentation du stock, le refus des commandes en rupture, le fait que le prix envoyé
par le client est ignoré, et le cycle d'encaissement partiel puis total.

## Passer en production

- Renseigner `SECRET_KEY` dans `.env` et changer les mots de passe de démonstration.
- Créer un utilisateur MySQL dédié à l'application plutôt que d'utiliser `root`.
- Servir l'application avec gunicorn :

  ```
  gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60
  ```

  C'est le contenu du `Procfile`. Sur Render, cette commande se saisit aussi dans le
  champ **Start Command** du service (Build Command : `pip install -r requirements.txt`).

  `0.0.0.0` et `$PORT` sont indispensables en conteneur : écouter sur `127.0.0.1` ou sur
  un port fixe rend le service invisible et l'hébergeur signale « no open ports detected ».
  Le même message apparaît si l'application ne démarre pas du tout : `initialiser_base()`
  s'exécute à l'import, donc une base injoignable fait échouer le worker avant qu'il
  n'ouvre le port. Les journaux distinguent les deux cas (`Worker failed to boot` suivi de
  `Can't connect to MySQL server`).

### Particularités de Render

- **Render n'héberge pas de MySQL managé** (Postgres et Key Value uniquement). La base
  vit donc ailleurs : il faut autoriser les connexions distantes depuis Render côté
  hébergeur MySQL, et renseigner `DB_PORT` s'il diffère de 3306.
- **Une instance gratuite s'endort après 15 minutes sans trafic**, et la requête suivante
  attend environ une minute le temps du réveil. Une page « lente à charger » de temps en
  temps vient de là, pas de l'application.
- **Le disque est éphémère.** Les images de plats envoyées par `/menu/add` sont écrites
  dans `static/uploads/` et disparaissent à chaque redéploiement ou réveil du service.
  Il faut un disque persistant, ou un stockage externe, pour les conserver.
- Sauvegarder régulièrement la base : `mysqldump divix_maquis | gzip > sauvegarde.sql.gz`.
- Les librairies d'interface (Bootstrap, SweetAlert2, Chart.js, Boxicons) sont chargées
  depuis des CDN, comme dans Divix SysPaie. Si le maquis a une connexion instable,
  il vaut mieux les héberger localement dans `static/vendor/` : l'interface reste
  utilisable même sans internet.
