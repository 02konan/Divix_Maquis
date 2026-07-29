-- Schéma MySQL de Divix Maquis.
-- Exécuté au démarrage par backend.database.initialiser_base().

CREATE TABLE IF NOT EXISTS roles (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    nom  VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS utilisateurs (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    nom           VARCHAR(120) NOT NULL,
    email         VARCHAR(190) NOT NULL UNIQUE,
    mot_de_passe  VARCHAR(255) NOT NULL,
    id_role       INT NOT NULL,
    actif         TINYINT(1) NOT NULL DEFAULT 1,
    date_creation DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_utilisateurs_role FOREIGN KEY (id_role) REFERENCES roles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tables_salle (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    numero  VARCHAR(20) NOT NULL UNIQUE,
    zone    VARCHAR(50) NOT NULL DEFAULT 'Salle',
    places  INT NOT NULL DEFAULT 4,
    statut  VARCHAR(20) NOT NULL DEFAULT 'Libre'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS categories (
    id    INT AUTO_INCREMENT PRIMARY KEY,
    nom   VARCHAR(80) NOT NULL UNIQUE,
    type  VARCHAR(40) NOT NULL DEFAULT 'Cuisine'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS articles (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    reference      VARCHAR(20) NOT NULL UNIQUE,
    nom            VARCHAR(150) NOT NULL,
    id_categorie   INT NULL,
    prix           DOUBLE NOT NULL DEFAULT 0,
    cout_revient   DOUBLE NOT NULL DEFAULT 0,
    gere_stock     TINYINT(1) NOT NULL DEFAULT 1,
    stock          INT NOT NULL DEFAULT 0,
    seuil_alerte   INT NOT NULL DEFAULT 5,
    disponible     TINYINT(1) NOT NULL DEFAULT 1,
    image          VARCHAR(255) NULL,
    id_utilisateur INT NULL,
    date_creation  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_articles_categorie   FOREIGN KEY (id_categorie)   REFERENCES categories(id),
    CONSTRAINT fk_articles_utilisateur FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS commandes (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    reference        VARCHAR(20) NOT NULL UNIQUE,
    id_table         INT NULL,
    type_service     VARCHAR(20) NOT NULL DEFAULT 'Sur place',
    nom_client       VARCHAR(120) NULL,
    telephone_client VARCHAR(30) NULL,
    couverts         INT NOT NULL DEFAULT 1,
    statut           VARCHAR(20) NOT NULL DEFAULT 'En cours',
    montant_total    DOUBLE NOT NULL DEFAULT 0,
    remise           DOUBLE NOT NULL DEFAULT 0,
    commentaire      TEXT NULL,
    id_utilisateur   INT NULL,
    date_commande    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_cloture     DATETIME NULL,
    KEY idx_commandes_date (date_commande),
    KEY idx_commandes_statut (statut),
    CONSTRAINT fk_commandes_table       FOREIGN KEY (id_table)       REFERENCES tables_salle(id),
    CONSTRAINT fk_commandes_utilisateur FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lignes_commande (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    id_commande   INT NOT NULL,
    id_article    INT NOT NULL,
    quantite      INT NOT NULL,
    prix_unitaire DOUBLE NOT NULL,
    total         DOUBLE NOT NULL,
    note          TEXT NULL,
    KEY idx_lignes_commande (id_commande),
    CONSTRAINT fk_lignes_commande FOREIGN KEY (id_commande) REFERENCES commandes(id) ON DELETE CASCADE,
    CONSTRAINT fk_lignes_article  FOREIGN KEY (id_article)  REFERENCES articles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS paiements (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    reference      VARCHAR(20) NOT NULL UNIQUE,
    id_commande    INT NOT NULL,
    montant        DOUBLE NOT NULL,
    mode           VARCHAR(40) NOT NULL,
    commentaire    TEXT NULL,
    id_utilisateur INT NULL,
    date_paiement  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_paiements_date (date_paiement),
    CONSTRAINT fk_paiements_commande    FOREIGN KEY (id_commande)    REFERENCES commandes(id),
    CONSTRAINT fk_paiements_utilisateur FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mouvements_stock (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    id_article     INT NOT NULL,
    type_mouvement VARCHAR(20) NOT NULL,
    quantite       INT NOT NULL,
    stock_apres    INT NOT NULL,
    motif          VARCHAR(190) NULL,
    id_utilisateur INT NULL,
    date_mouvement DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_mouvements_date (date_mouvement),
    CONSTRAINT fk_mouvements_article     FOREIGN KEY (id_article)     REFERENCES articles(id),
    CONSTRAINT fk_mouvements_utilisateur FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS depenses (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    reference      VARCHAR(20) NOT NULL UNIQUE,
    libelle        VARCHAR(190) NOT NULL,
    categorie      VARCHAR(60) NOT NULL,
    montant        DOUBLE NOT NULL,
    fournisseur    VARCHAR(150) NULL,
    mode_paiement  VARCHAR(40) NULL,
    commentaire    TEXT NULL,
    id_utilisateur INT NULL,
    date_depense   DATE NOT NULL DEFAULT (CURDATE()),
    KEY idx_depenses_date (date_depense),
    CONSTRAINT fk_depenses_utilisateur FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
