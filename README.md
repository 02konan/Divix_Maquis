# Divix Maquis

Application de gestion de maquis et restaurant : prise de commande en salle, carte,
stock des boissons, caisse et dépenses.

L'interface reprend intégralement celle de **Divix SysPaie** (mêmes feuilles de style,
même structure de pages, mêmes composants). Seul le backend a été remplacé : le métier
« ventes à crédit » a laissé la place au métier « restauration », et la base MySQL à
SQLite pour que le projet démarre sans aucune configuration.

## Démarrage

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

python -m backend.donnees_demo     # crée maquis.db + un jeu de démonstration
python app.py                      # http://127.0.0.1:5000
```

Comptes de démonstration :

| Rôle     | Email                      | Mot de passe |
|----------|----------------------------|--------------|
| Gérant   | `admin@divixmaquis.ci`     | `admin123`   |
| Caissier | `caisse@divixmaquis.ci`    | `caisse123`  |
| Serveur  | `serveur@divixmaquis.ci`   | `serveur123` |

> Changez ces mots de passe avant toute mise en production, et définissez `SECRET_KEY`
> dans un fichier `.env` (voir `.env.example`).

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
│   ├── schema.sql          schéma SQLite
│   ├── database.py         connexion et helpers de requête
│   ├── auth.py             authentification (mots de passe hachés)
│   ├── models.py           utilisateur Flask-Login
│   ├── lectures.py         toutes les lectures (listes, compteurs, dashboard)
│   ├── ecritures.py        toutes les écritures (commandes, caisse, stock, dépenses)
│   └── donnees_demo.py     initialisation + jeu de démonstration
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
`lignes_commande`, `paiements`, `mouvements_stock`, `depenses`.

Un article porte un indicateur `gere_stock` : les boissons sont décomptées à la vente,
les plats sont préparés à la commande et ne consomment pas de stock.

## Tests

```bash
pip install -r dev-requirements.txt
python -m pytest tests/
```

Les tests couvrent l'authentification, l'accès aux pages, les endpoints JSON, la
décrémentation du stock, le refus des commandes en rupture, le fait que le prix envoyé
par le client est ignoré, et le cycle d'encaissement partiel puis total.

## Passer en production

- Renseigner `SECRET_KEY` dans `.env` et changer les mots de passe de démonstration.
- Servir l'application avec `gunicorn app:app` derrière un reverse proxy.
- Sauvegarder régulièrement `maquis.db` (ou pointer `DATABASE` vers un autre chemin).
- Les librairies d'interface (Bootstrap, SweetAlert2, Chart.js, Boxicons) sont chargées
  depuis des CDN, comme dans Divix SysPaie. Si le maquis a une connexion instable,
  il vaut mieux les héberger localement dans `static/vendor/` : l'interface reste
  utilisable même sans internet.
