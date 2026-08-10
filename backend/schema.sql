-- Schéma MySQL de Divix Maquis.
-- Exécuté au démarrage par backend.database.initialiser_base().
--
-- La base héberge plusieurs établissements : chaque table métier porte un
-- id_etablissement, et toutes les requêtes filtrent dessus. Les références
-- (CMD-0001, ART-0007, ...) sont numérotées par établissement, donc uniques
-- par établissement et non globalement.

CREATE TABLE IF NOT EXISTS etablissements (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    nom           VARCHAR(160) NOT NULL,
    ville         VARCHAR(120) NULL,
    telephone     VARCHAR(40) NULL,
    actif         TINYINT(1) NOT NULL DEFAULT 1,
    date_creation DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS roles (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    nom  VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- L'email reste unique sur toute la base : c'est l'identifiant de connexion,
-- et c'est lui qui désigne l'établissement du compte.
-- id_etablissement nul = compte plateforme, qui n'appartient à aucun maquis.
CREATE TABLE IF NOT EXISTS utilisateurs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    nom              VARCHAR(120) NOT NULL,
    email            VARCHAR(190) NOT NULL UNIQUE,
    mot_de_passe     VARCHAR(255) NOT NULL,
    id_role          INT NOT NULL,
    id_etablissement INT NULL,
    actif            TINYINT(1) NOT NULL DEFAULT 1,
    date_creation    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_utilisateurs_etablissement (id_etablissement),
    CONSTRAINT fk_utilisateurs_role         FOREIGN KEY (id_role)          REFERENCES roles(id),
    CONSTRAINT fk_utilisateurs_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Fonctionnalités activables depuis la page Administration, propres à chaque
-- établissement. Les lignes manquantes sont créées à partir de backend/modules.py.
CREATE TABLE IF NOT EXISTS modules (
    id_etablissement INT NOT NULL,
    cle              VARCHAR(30) NOT NULL,
    actif            TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (id_etablissement, cle),
    CONSTRAINT fk_modules_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Numérotation des références (CMD-0001, PAI-0002, ...) : un compteur par
-- préfixe et par établissement, verrouillé le temps de l'incrément.
CREATE TABLE IF NOT EXISTS compteurs (
    id_etablissement INT NOT NULL,
    prefixe          VARCHAR(10) NOT NULL,
    valeur           INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id_etablissement, prefixe),
    CONSTRAINT fk_compteurs_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tables_salle (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    numero           VARCHAR(30) NOT NULL,
    zone             VARCHAR(80) NOT NULL DEFAULT 'Salle',
    places           INT NOT NULL DEFAULT 4,
    statut           VARCHAR(20) NOT NULL DEFAULT 'Libre',
    UNIQUE KEY uq_tables_salle_numero (id_etablissement, numero),
    CONSTRAINT fk_tables_salle_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS categories (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    nom              VARCHAR(120) NOT NULL,
    type             VARCHAR(40) NOT NULL DEFAULT 'Cuisine',
    UNIQUE KEY uq_categories_nom (id_etablissement, nom),
    CONSTRAINT fk_categories_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS articles (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    reference        VARCHAR(20) NOT NULL,
    nom              VARCHAR(255) NOT NULL,
    id_categorie     INT NULL,
    prix             DECIMAL(12,2) NOT NULL DEFAULT 0,
    cout_revient     DECIMAL(12,2) NOT NULL DEFAULT 0,
    gere_stock       TINYINT(1) NOT NULL DEFAULT 1,
    stock            INT NOT NULL DEFAULT 0,
    seuil_alerte     INT NOT NULL DEFAULT 5,
    disponible       TINYINT(1) NOT NULL DEFAULT 1,
    image            VARCHAR(255) NULL,
    id_utilisateur   INT NULL,
    date_creation    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_articles_reference (id_etablissement, reference),
    CONSTRAINT fk_articles_categorie     FOREIGN KEY (id_categorie)     REFERENCES categories(id),
    CONSTRAINT fk_articles_utilisateur   FOREIGN KEY (id_utilisateur)   REFERENCES utilisateurs(id),
    CONSTRAINT fk_articles_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS commandes (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    reference        VARCHAR(20) NOT NULL,
    id_table         INT NULL,
    type_service     VARCHAR(20) NOT NULL DEFAULT 'Sur place',
    nom_client       VARCHAR(255) NULL,
    telephone_client VARCHAR(40) NULL,
    couverts         INT NOT NULL DEFAULT 1,
    statut           VARCHAR(20) NOT NULL DEFAULT 'En cours',
    montant_total    DECIMAL(12,2) NOT NULL DEFAULT 0,
    remise           DECIMAL(12,2) NOT NULL DEFAULT 0,
    commentaire      TEXT NULL,
    id_utilisateur   INT NULL,
    date_commande    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_cloture     DATETIME NULL,
    UNIQUE KEY uq_commandes_reference (id_etablissement, reference),
    KEY idx_commandes_date (date_commande),
    KEY idx_commandes_statut (statut),
    CONSTRAINT fk_commandes_table         FOREIGN KEY (id_table)         REFERENCES tables_salle(id),
    CONSTRAINT fk_commandes_utilisateur   FOREIGN KEY (id_utilisateur)   REFERENCES utilisateurs(id),
    CONSTRAINT fk_commandes_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pas d'id_etablissement ici : une ligne appartient à sa commande, qui porte
-- déjà l'établissement, et toute lecture passe par elle.
CREATE TABLE IF NOT EXISTS lignes_commande (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    id_commande   INT NOT NULL,
    id_article    INT NOT NULL,
    quantite      INT NOT NULL,
    prix_unitaire DECIMAL(12,2) NOT NULL,
    total         DECIMAL(12,2) NOT NULL,
    note          TEXT NULL,
    KEY idx_lignes_commande (id_commande),
    CONSTRAINT fk_lignes_commande FOREIGN KEY (id_commande) REFERENCES commandes(id) ON DELETE CASCADE,
    CONSTRAINT fk_lignes_article  FOREIGN KEY (id_article)  REFERENCES articles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS paiements (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    reference        VARCHAR(20) NOT NULL,
    id_commande      INT NOT NULL,
    montant          DECIMAL(12,2) NOT NULL,
    mode             VARCHAR(40) NOT NULL,
    commentaire      TEXT NULL,
    id_utilisateur   INT NULL,
    date_paiement    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_paiements_reference (id_etablissement, reference),
    KEY idx_paiements_date (date_paiement),
    CONSTRAINT fk_paiements_commande      FOREIGN KEY (id_commande)      REFERENCES commandes(id),
    CONSTRAINT fk_paiements_utilisateur   FOREIGN KEY (id_utilisateur)   REFERENCES utilisateurs(id),
    CONSTRAINT fk_paiements_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mouvements_stock (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    id_article       INT NOT NULL,
    type_mouvement   VARCHAR(20) NOT NULL,
    quantite         INT NOT NULL,
    stock_apres      INT NOT NULL,
    motif            VARCHAR(255) NULL,
    id_utilisateur   INT NULL,
    date_mouvement   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_mouvements_date (date_mouvement),
    KEY idx_mouvements_etablissement (id_etablissement),
    CONSTRAINT fk_mouvements_article       FOREIGN KEY (id_article)       REFERENCES articles(id),
    CONSTRAINT fk_mouvements_utilisateur   FOREIGN KEY (id_utilisateur)   REFERENCES utilisateurs(id),
    CONSTRAINT fk_mouvements_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Journal des actions : qui a fait quoi, et quand. Alimenté automatiquement
-- après chaque écriture réussie, sans que l'appelant ait à y penser.
-- id_utilisateur reste nul si le compte est supprimé : la trace survit à qui
-- l'a laissée.
CREATE TABLE IF NOT EXISTS journal_actions (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    id_utilisateur   INT NULL,
    nom_utilisateur  VARCHAR(120) NOT NULL DEFAULT '—',
    role_utilisateur VARCHAR(50) NOT NULL DEFAULT '—',
    action           VARCHAR(60) NOT NULL,
    libelle          VARCHAR(120) NOT NULL,
    cible            VARCHAR(190) NULL,
    details          VARCHAR(500) NULL,
    date_action      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_journal_date (id_etablissement, date_action),
    CONSTRAINT fk_journal_utilisateur   FOREIGN KEY (id_utilisateur)   REFERENCES utilisateurs(id) ON DELETE SET NULL,
    CONSTRAINT fk_journal_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS depenses (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    id_etablissement INT NOT NULL,
    reference        VARCHAR(20) NOT NULL,
    libelle          VARCHAR(255) NOT NULL,
    categorie        VARCHAR(60) NOT NULL,
    montant          DECIMAL(12,2) NOT NULL,
    fournisseur      VARCHAR(255) NULL,
    mode_paiement    VARCHAR(40) NULL,
    commentaire      TEXT NULL,
    id_utilisateur   INT NULL,
    date_depense     DATE NOT NULL DEFAULT (CURDATE()),
    UNIQUE KEY uq_depenses_reference (id_etablissement, reference),
    KEY idx_depenses_date (date_depense),
    CONSTRAINT fk_depenses_utilisateur   FOREIGN KEY (id_utilisateur)   REFERENCES utilisateurs(id),
    CONSTRAINT fk_depenses_etablissement FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
