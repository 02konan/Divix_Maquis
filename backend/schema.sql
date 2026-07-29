

CREATE TABLE IF NOT EXISTS roles (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nom  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS utilisateurs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nom           TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    mot_de_passe  TEXT NOT NULL,
    id_role       INTEGER NOT NULL REFERENCES roles(id),
    actif         INTEGER NOT NULL DEFAULT 1,
    date_creation TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tables_salle (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    numero  TEXT NOT NULL UNIQUE,
    zone    TEXT NOT NULL DEFAULT 'Salle',
    places  INTEGER NOT NULL DEFAULT 4,
    statut  TEXT NOT NULL DEFAULT 'Libre'
);

CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    nom   TEXT NOT NULL UNIQUE,
    type  TEXT NOT NULL DEFAULT 'Cuisine'
);

CREATE TABLE IF NOT EXISTS articles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    reference      TEXT NOT NULL UNIQUE,
    nom            TEXT NOT NULL,
    id_categorie   INTEGER REFERENCES categories(id),
    prix           REAL NOT NULL DEFAULT 0,
    cout_revient   REAL NOT NULL DEFAULT 0,
    gere_stock     INTEGER NOT NULL DEFAULT 1,
    stock          INTEGER NOT NULL DEFAULT 0,
    seuil_alerte   INTEGER NOT NULL DEFAULT 5,
    disponible     INTEGER NOT NULL DEFAULT 1,
    image          TEXT,
    id_utilisateur INTEGER REFERENCES utilisateurs(id),
    date_creation  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS commandes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    reference        TEXT NOT NULL UNIQUE,
    id_table         INTEGER REFERENCES tables_salle(id),
    type_service     TEXT NOT NULL DEFAULT 'Sur place',
    nom_client       TEXT,
    telephone_client TEXT,
    couverts         INTEGER NOT NULL DEFAULT 1,
    statut           TEXT NOT NULL DEFAULT 'En cours',
    montant_total    REAL NOT NULL DEFAULT 0,
    remise           REAL NOT NULL DEFAULT 0,
    commentaire      TEXT,
    id_utilisateur   INTEGER REFERENCES utilisateurs(id),
    date_commande    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    date_cloture     TEXT
);

CREATE TABLE IF NOT EXISTS lignes_commande (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    id_commande   INTEGER NOT NULL REFERENCES commandes(id) ON DELETE CASCADE,
    id_article    INTEGER NOT NULL REFERENCES articles(id),
    quantite      INTEGER NOT NULL,
    prix_unitaire REAL NOT NULL,
    total         REAL NOT NULL,
    note          TEXT
);

CREATE TABLE IF NOT EXISTS paiements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    reference      TEXT NOT NULL UNIQUE,
    id_commande    INTEGER NOT NULL REFERENCES commandes(id),
    montant        REAL NOT NULL,
    mode           TEXT NOT NULL,
    commentaire    TEXT,
    id_utilisateur INTEGER REFERENCES utilisateurs(id),
    date_paiement  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS mouvements_stock (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_article     INTEGER NOT NULL REFERENCES articles(id),
    type_mouvement TEXT NOT NULL,
    quantite       INTEGER NOT NULL,
    stock_apres    INTEGER NOT NULL,
    motif          TEXT,
    id_utilisateur INTEGER REFERENCES utilisateurs(id),
    date_mouvement TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS depenses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    reference      TEXT NOT NULL UNIQUE,
    libelle        TEXT NOT NULL,
    categorie      TEXT NOT NULL,
    montant        REAL NOT NULL,
    fournisseur    TEXT,
    mode_paiement  TEXT,
    commentaire    TEXT,
    id_utilisateur INTEGER REFERENCES utilisateurs(id),
    date_depense   TEXT NOT NULL DEFAULT (date('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_commandes_date   ON commandes(date_commande);
CREATE INDEX IF NOT EXISTS idx_commandes_statut ON commandes(statut);
CREATE INDEX IF NOT EXISTS idx_lignes_commande  ON lignes_commande(id_commande);
CREATE INDEX IF NOT EXISTS idx_paiements_date   ON paiements(date_paiement);
CREATE INDEX IF NOT EXISTS idx_depenses_date    ON depenses(date_depense);
