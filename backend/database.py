
import os
import re
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


class Connexion:
   
    def __init__(self, connexion_pymysql):
        self._conn = connexion_pymysql

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
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, type_exception, *_):
        try:
            if type_exception is not None:
                self._conn.rollback()
        finally:
            self._conn.close()


def connexion():
    return Connexion(pymysql.connect(**parametres_connexion()))


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
    """Construit une référence lisible du type CMD-0001."""
    total = valeur(f"SELECT COUNT(*) FROM {table}")
    return f"{prefixe}-{total + 1:04d}"
