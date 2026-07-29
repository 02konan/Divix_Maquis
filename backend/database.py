"""Couche d'accès SQLite pour Divix Maquis."""

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def chemin_base():
    """Chemin du fichier SQLite, surchargeable via la variable DATABASE."""
    return os.getenv("DATABASE", str(BASE_DIR / "maquis.db"))


def connexion():
    conn = sqlite3.connect(chemin_base())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def executer(sql, params=()):
    """INSERT / UPDATE / DELETE : renvoie l'id de la ligne insérée."""
    with connexion() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid


def lire_tout(sql, params=()):
    with connexion() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def lire_un(sql, params=()):
    with connexion() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def valeur(sql, params=(), defaut=0):
    """Renvoie la première colonne de la première ligne (COUNT, SUM, ...)."""
    with connexion() as conn:
        row = conn.execute(sql, params).fetchone()
        if not row or row[0] is None:
            return defaut
        return row[0]


def initialiser_base():
    """Crée les tables si elles n'existent pas encore."""
    with connexion() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()


def generer_reference(prefixe, table):
    """Construit une référence lisible du type CMD-0001."""
    total = valeur(f"SELECT COUNT(*) FROM {table}")
    return f"{prefixe}-{total + 1:04d}"
