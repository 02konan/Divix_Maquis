
import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

# Chargé ici pour que tous les points d'entrée (app.py, donnees_demo, tests)
# partagent la même configuration MySQL.
load_dotenv()

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Le nom de la base est injecté dans le SQL (CREATE DATABASE n'accepte pas de
# paramètre lié) : on n'autorise donc que des identifiants MySQL classiques.
MOTIF_NOM_BASE = re.compile(r"^[A-Za-z0-9_$]+$")


def nom_base():
    """Nom de la base MySQL, surchargeable via la variable DATABASE."""
    nom = os.getenv("DATABASE", "divix_maquis")
    if not MOTIF_NOM_BASE.match(nom):
        raise ValueError(f"Nom de base MySQL invalide : {nom!r}")
    return nom


def parametres_connexion(avec_base=True):

    parametres = {
        "host": os.getenv("DB_HOST"),
        # Un MySQL managé n'écoute pas forcément sur 3306.
        "port": int(os.getenv("DB_PORT") or 3306),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    socket_unix = os.getenv("MYSQL_UNIX_SOCKET")
    if socket_unix:
        parametres["unix_socket"] = socket_unix
    if avec_base:
        parametres["database"] = nom_base()
    return parametres


# Une connexion MySQL par thread, réutilisée d'une requête à l'autre : ouvrir une
# connexion coûte un aller-retour réseau et une authentification, ce qui est
# prohibitif quand une page enchaîne vingt requêtes.
_local = threading.local()

# Le serveur ferme les connexions inactives (wait_timeout) : au-delà de ce délai
# sans usage, on vérifie que la connexion vit encore avant de la réutiliser.
DELAI_VERIFICATION = 30


def _connexion_partagee():
    maintenant = time.monotonic()
    conn = getattr(_local, "conn", None)
    if conn is not None:
        if maintenant - getattr(_local, "dernier_usage", 0) > DELAI_VERIFICATION:
            try:
                conn.ping(reconnect=False)
            except pymysql.MySQLError:
                fermer_connexion()
                conn = None
        if conn is not None:
            _local.dernier_usage = maintenant
            return conn

    conn = pymysql.connect(**parametres_connexion())
    _local.conn = conn
    _local.dernier_usage = maintenant
    return conn


def fermer_connexion():
    """Ferme la connexion du thread courant (fin de processus, tests, ...)."""
    conn = getattr(_local, "conn", None)
    _local.conn = None
    if conn is not None:
        try:
            conn.close()
        except pymysql.MySQLError:
            pass


class Curseur:
    """Curseur dont les lignes passent toutes par la normalisation des types.

    Sans lui, `lire_un` normalisait mais `conn.execute(...).fetchone()` non : sur
    une base dont les montants sont en DECIMAL, les écritures récupéraient des
    `Decimal` et les mélangeaient aux flottants venus du formulaire, ce qui
    échoue (`unsupported operand type(s) for -`).
    """

    def __init__(self, curseur):
        self._curseur = curseur

    def fetchone(self):
        row = self._curseur.fetchone()
        return _ligne(row) if row else row

    def fetchall(self):
        return [_ligne(row) for row in self._curseur.fetchall()]

    def fetchmany(self, taille=None):
        lignes = (
            self._curseur.fetchmany()
            if taille is None
            else self._curseur.fetchmany(taille)
        )
        return [_ligne(row) for row in lignes]

    def __iter__(self):
        for row in self._curseur:
            yield _ligne(row)

    @property
    def lastrowid(self):
        return self._curseur.lastrowid

    @property
    def rowcount(self):
        return self._curseur.rowcount


class Connexion:
    # En sortie de bloc la transaction est toujours close (rollback) : sinon la
    # connexion réutilisée garderait un instantané REPEATABLE READ et relirait
    # des données périmées. Un bloc imbriqué rejoint la transaction englobante.

    def __init__(self, connexion_pymysql, imbriquee):
        self._conn = connexion_pymysql
        self._imbriquee = imbriquee

    def execute(self, sql, params=()):
        curseur = self._conn.cursor()
        # `params or None` évite que PyMySQL tente une interpolation inutile.
        curseur.execute(sql, params or None)
        return Curseur(curseur)

    def executemany(self, sql, sequence):
        curseur = self._conn.cursor()
        curseur.executemany(sql, sequence)
        return curseur

    def commit(self):
        # Un bloc imbriqué ne valide pas : la transaction appartient au bloc
        # englobant, qui n'a peut-être pas fini ses écritures.
        if not self._imbriquee:
            self._conn.commit()

    def rollback(self):
        if not self._imbriquee:
            self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        _local.profondeur -= 1
        if self._imbriquee:
            return
        try:
            self._conn.rollback()
        except pymysql.MySQLError:
            fermer_connexion()


def connexion():
    profondeur = getattr(_local, "profondeur", 0)
    _local.profondeur = profondeur + 1
    try:
        return Connexion(_connexion_partagee(), imbriquee=profondeur > 0)
    except Exception:
        _local.profondeur = profondeur
        raise


def _convertir(valeur_brute):
    if isinstance(valeur_brute, datetime):
        return valeur_brute.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valeur_brute, date):
        return valeur_brute.isoformat()
    if isinstance(valeur_brute, timedelta):
        return str(valeur_brute)
    if isinstance(valeur_brute, Decimal):
      
        if valeur_brute == valeur_brute.to_integral_value():
            return int(valeur_brute)
        return float(valeur_brute)
    if isinstance(valeur_brute, (bytes, bytearray)):
        return valeur_brute.decode("utf-8", "replace")
    return valeur_brute


def _ligne(row):
    return {colonne: _convertir(valeur_brute) for colonne, valeur_brute in row.items()}


def executer(sql, params=()):
    """INSERT / UPDATE / DELETE : renvoie l'id de la ligne insérée."""
    with connexion() as conn:
        curseur = conn.execute(sql, params)
        conn.commit()
        return curseur.lastrowid


def lire_tout(sql, params=()):
    with connexion() as conn:
        return conn.execute(sql, params).fetchall()


def lire_un(sql, params=()):
    with connexion() as conn:
        return conn.execute(sql, params).fetchone()


def valeur(sql, params=(), defaut=0):
    """Renvoie la première colonne de la première ligne (COUNT, SUM, ...)."""
    with connexion() as conn:
        row = conn.execute(sql, params).fetchone()
        if not row:
            return defaut
        premiere = next(iter(row.values()))
        return defaut if premiere is None else premiere


MOTIF_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.IGNORECASE)
CODE_BASE_INCONNUE = 1049  # ER_BAD_DB_ERROR

MOTIF_DOUBLON = re.compile(r"Duplicate entry '(.*)' for key")
MOTIF_COLONNE_LONGUE = re.compile(r"Data too long for column '(\w+)'")
MOTIF_CLE_ETRANGERE = re.compile(r"FOREIGN KEY \(`(\w+)`\)")

# La colonne fautive dit précisément ce qui manque : un message générique
# obligeait à deviner entre la catégorie, l'utilisateur ou la table.
MESSAGES_CLE_ETRANGERE = {
    "id_categorie": "Cette catégorie n'existe plus : rechargez la page.",
    "id_utilisateur": "Votre session n'est plus valide : reconnectez-vous.",
    "id_article": "Cet article n'existe plus : rechargez la page.",
    "id_commande": "Cette commande n'existe plus : rechargez la page.",
    "id_table": "Cette table n'existe plus : rechargez la page.",
    "id_role": "Ce rôle n'existe pas.",
}

journal = logging.getLogger(__name__)


def message_erreur(erreur):
    """Traduit une erreur MySQL en message affichable ; laisse passer le reste.

    Sans cela l'interface affiche des tuples bruts du type
    `(1062, "Duplicate entry '1' for key 'numero'")`. L'erreur technique part
    dans les journaux : masquée à l'écran, elle resterait sinon introuvable.
    """
    if isinstance(erreur, pymysql.MySQLError):
        journal.warning("Erreur MySQL : %s", erreur)

    if isinstance(erreur, pymysql.err.IntegrityError):
        detail = str(erreur)
        doublon = MOTIF_DOUBLON.search(detail)
        if doublon:
            return f"« {doublon.group(1)} » existe déjà."
        if "foreign key constraint fails" in detail:
            colonne = MOTIF_CLE_ETRANGERE.search(detail)
            return MESSAGES_CLE_ETRANGERE.get(
                colonne.group(1) if colonne else "",
                "Référence introuvable ou encore utilisée ailleurs.",
            )
        return "Enregistrement refusé : contrainte de base non respectée."
    if isinstance(erreur, pymysql.err.DataError):
        colonne = MOTIF_COLONNE_LONGUE.search(str(erreur))
        if colonne:
            return f"Le champ « {colonne.group(1)} » est trop long."
        return "Une des valeurs saisies est invalide."
    if isinstance(erreur, pymysql.MySQLError):
        return "La base de données est momentanément inaccessible."
    return str(erreur)


def creer_base_si_absente():
    """Crée la base MySQL elle-même : l'application démarre sur un serveur vierge."""
    conn = pymysql.connect(**parametres_connexion(avec_base=False))
    try:
        with conn.cursor() as curseur:
            curseur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{nom_base()}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def instructions_schema():
    """Découpe schema.sql : PyMySQL n'exécute qu'une instruction à la fois."""
    contenu = re.sub(r"--[^\n]*", "", SCHEMA_PATH.read_text(encoding="utf-8"))
    return [
        instruction.strip() for instruction in contenu.split(";") if instruction.strip()
    ]


def _tables_manquantes(conn):
    attendues = set(MOTIF_TABLE.findall("\n".join(instructions_schema())))
    existantes = {
        ligne["nom"]
        for ligne in conn.execute(
            """SELECT table_name AS nom FROM information_schema.tables
               WHERE table_schema = %s""",
            (nom_base(),),
        ).fetchall()
    }
    return attendues - existantes


# Tables métier rattachées à un établissement. L'ordre importe : une table est
# migrée avant celles qui la référencent.
TABLES_ETABLISSEMENT = (
    "utilisateurs",
    "modules",
    "compteurs",
    "tables_salle",
    "categories",
    "articles",
    "commandes",
    "paiements",
    "mouvements_stock",
    "depenses",
)

# Colonnes qui étaient uniques sur toute la base et ne le sont plus que par
# établissement : deux maquis ont chacun leur table « 1 » et leur CMD-0001.
# L'email n'y figure pas : il sert à se connecter, donc il reste global.
UNICITES_PAR_ETABLISSEMENT = {
    "modules": "cle",
    "compteurs": "prefixe",
    "tables_salle": "numero",
    "categories": "nom",
    "articles": "reference",
    "commandes": "reference",
    "paiements": "reference",
    "depenses": "reference",
}

NOM_ETABLISSEMENT_REPRISE = "Mon établissement"


def _colonnes(conn, table):
    return {
        ligne["nom"]
        for ligne in conn.execute(
            """SELECT column_name AS nom FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s""",
            (nom_base(), table),
        ).fetchall()
    }


def _index_uniques_sur(conn, table, colonne):
    """Index uniques ne portant que sur cette colonne, donc à élargir."""
    lignes = conn.execute(
        """SELECT index_name AS nom, COUNT(*) AS colonnes,
                  MAX(column_name) AS colonne
           FROM information_schema.statistics
           WHERE table_schema = %s AND table_name = %s AND non_unique = 0
           GROUP BY index_name""",
        (nom_base(), table),
    ).fetchall()
    return [
        ligne["nom"]
        for ligne in lignes
        if ligne["colonnes"] == 1 and ligne["colonne"] == colonne
    ]


def _etablissement_de_reprise(conn):
    """L'établissement auquel rattacher les données d'une base mono-maquis."""
    ligne = conn.execute("SELECT id FROM etablissements ORDER BY id LIMIT 1").fetchone()
    if ligne:
        return ligne["id"]
    return conn.execute(
        "INSERT INTO etablissements (nom) VALUES (%s)", (NOM_ETABLISSEMENT_REPRISE,)
    ).lastrowid


def _migration_necessaire(conn):
    """Deux sondages suffisent à savoir si la base est déjà multi-établissement.

    Parcourir les dix tables à chaque démarrage coûterait vingt allers-retours
    pour ne rien faire. La première condition attrape une base d'avant la
    migration, la seconde une migration interrompue en cours de route : MySQL
    valide chaque ALTER au fil de l'eau, un plantage laisserait la base à
    moitié convertie.
    """
    return "id_etablissement" not in _colonnes(conn, "utilisateurs") or bool(
        _index_uniques_sur(conn, "commandes", "reference")
    )


def _migrer_vers_multi_etablissement(conn):
    """Rattache une base déjà en service à un établissement, sans perdre de données.

    Les installations d'avant le multi-établissement n'ont pas la colonne
    id_etablissement, et leurs numéros de table ou de commande sont uniques sur
    toute la base. On ajoute la colonne, on y met l'établissement de reprise,
    puis on élargit les contraintes d'unicité. Chaque étape se teste avant de
    s'exécuter : la fonction tourne à chaque démarrage et ne doit rien faire
    quand la base est déjà à jour.
    """
    a_touche = False

    for table in TABLES_ETABLISSEMENT:
        if "id_etablissement" in _colonnes(conn, table):
            continue
        a_touche = True
        id_reprise = _etablissement_de_reprise(conn)
        journal.info("Migration multi-établissement : colonne ajoutée à %s", table)

        # En trois temps : la colonne naît nullable pour que les lignes déjà
        # présentes passent, puis elle se remplit, puis elle se ferme.
        conn.execute(f"ALTER TABLE {table} ADD COLUMN id_etablissement INT NULL")
        conn.execute(f"UPDATE {table} SET id_etablissement = %s", (id_reprise,))
        if table != "utilisateurs":  # un compte plateforme n'a pas d'établissement
            conn.execute(f"ALTER TABLE {table} MODIFY id_etablissement INT NOT NULL")
        conn.execute(
            f"""ALTER TABLE {table}
                ADD CONSTRAINT fk_{table}_etablissement
                FOREIGN KEY (id_etablissement) REFERENCES etablissements(id)"""
        )

    for table, colonne in UNICITES_PAR_ETABLISSEMENT.items():
        for index in _index_uniques_sur(conn, table, colonne):
            a_touche = True
            journal.info("Migration multi-établissement : unicité %s.%s", table, colonne)
            if index == "PRIMARY":
                conn.execute(
                    f"""ALTER TABLE {table} DROP PRIMARY KEY,
                        ADD PRIMARY KEY (id_etablissement, {colonne})"""
                )
            else:
                conn.execute(f"ALTER TABLE {table} DROP INDEX `{index}`")
                conn.execute(
                    f"""ALTER TABLE {table}
                        ADD UNIQUE KEY uq_{table}_{colonne} (id_etablissement, {colonne})"""
                )

    if a_touche:
        conn.commit()


def initialiser_base():
    """Crée la base et les tables si elles n'existent pas encore.

    Appelée à chaque démarrage : on évite d'y rejouer tout le schéma, qui
    coûterait une douzaine d'allers-retours à chaque réveil du service.
    """
    try:
        _connexion_partagee()
    except pymysql.err.OperationalError as erreur:
        if erreur.args[0] != CODE_BASE_INCONNUE:
            raise
        creer_base_si_absente()

    with connexion() as conn:
        if _tables_manquantes(conn):
            for instruction in instructions_schema():
                conn.execute(instruction)
            conn.commit()
        if _migration_necessaire(conn):
            _migrer_vers_multi_etablissement(conn)


def generer_reference(prefixe, table):
    """Construit une référence lisible du type CMD-0001, propre à l'établissement.

    Le numéro vient d'un compteur dédié, verrouillé le temps de l'incrément :
    un simple `COUNT(*) + 1` attribuait la même référence à deux commandes
    prises au même instant, et l'une des deux était refusée.
    Le compteur s'amorce sur les lignes déjà présentes (jeu de démonstration,
    reprise de données) au premier appel.
    """
    from backend.etablissement import courant

    id_etablissement = courant()
    with connexion() as conn:
        conn.execute(
            f"""INSERT INTO compteurs (id_etablissement, prefixe, valeur)
                SELECT %s, %s, COUNT(*) + 1 FROM {table}
                 WHERE id_etablissement = %s
                ON DUPLICATE KEY UPDATE valeur = valeur + 1""",
            (id_etablissement, prefixe, id_etablissement),
        )
        numero = conn.execute(
            """SELECT valeur FROM compteurs
               WHERE id_etablissement = %s AND prefixe = %s""",
            (id_etablissement, prefixe),
        ).fetchone()["valeur"]
        conn.commit()
    return f"{prefixe}-{numero:04d}"
