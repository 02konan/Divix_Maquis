
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
        return curseur

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
        return [_ligne(row) for row in conn.execute(sql, params).fetchall()]


def lire_un(sql, params=()):
    with connexion() as conn:
        row = conn.execute(sql, params).fetchone()
        return _ligne(row) if row else None


def valeur(sql, params=(), defaut=0):
    """Renvoie la première colonne de la première ligne (COUNT, SUM, ...)."""
    with connexion() as conn:
        row = conn.execute(sql, params).fetchone()
        if not row:
            return defaut
        premiere = next(iter(row.values()))
        return defaut if premiere is None else _convertir(premiere)


MOTIF_DOUBLON = re.compile(r"Duplicate entry '(.*)' for key")
MOTIF_COLONNE_LONGUE = re.compile(r"Data too long for column '(\w+)'")


def message_erreur(erreur):
    """Traduit une erreur MySQL en message affichable ; laisse passer le reste.

    Sans cela l'interface affiche des tuples bruts du type
    `(1062, "Duplicate entry '1' for key 'numero'")`.
    """
    if isinstance(erreur, pymysql.err.IntegrityError):
        detail = str(erreur)
        doublon = MOTIF_DOUBLON.search(detail)
        if doublon:
            return f"« {doublon.group(1)} » existe déjà."
        if "foreign key constraint fails" in detail:
            return "Référence introuvable ou encore utilisée ailleurs."
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


def initialiser_base():
    """Crée la base et les tables si elles n'existent pas encore."""
    creer_base_si_absente()
    with connexion() as conn:
        for instruction in instructions_schema():
            conn.execute(instruction)
        conn.commit()

def generer_reference(prefixe, table):
    """Construit une référence lisible du type CMD-0001.

    Le numéro vient d'un compteur dédié, verrouillé le temps de l'incrément :
    un simple `COUNT(*) + 1` attribuait la même référence à deux commandes
    prises au même instant, et l'une des deux était refusée.
    Le compteur s'amorce sur les lignes déjà présentes (jeu de démonstration,
    reprise de données) au premier appel.
    """
    with connexion() as conn:
        conn.execute(
            f"""INSERT INTO compteurs (prefixe, valeur)
                SELECT %s, COUNT(*) + 1 FROM {table}
                ON DUPLICATE KEY UPDATE valeur = valeur + 1""",
            (prefixe,),
        )
        numero = conn.execute(
            "SELECT valeur FROM compteurs WHERE prefixe = %s", (prefixe,)
        ).fetchone()["valeur"]
        conn.commit()
    return f"{prefixe}-{numero:04d}"
