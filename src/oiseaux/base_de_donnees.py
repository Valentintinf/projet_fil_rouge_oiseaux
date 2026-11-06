"""Connexion à PostgreSQL et exécution des scripts SQL du projet."""

from pathlib import Path
from typing import Any

import psycopg

DOSSIER_SQL = Path(__file__).resolve().parents[2] / "sql"


def connecter(**parametres: Any) -> psycopg.Connection:
    """Ouvre une connexion à PostgreSQL.

    Les paramètres viennent des variables d'environnement standard de PostgreSQL :
    PGHOST, PGPORT, PGUSER, PGPASSWORD et PGDATABASE (voir .env.example).
    Ils peuvent être surchargés, par exemple ``connecter(dbname="autre_base")``.
    """
    return psycopg.connect("", **parametres)


def executer_script(connexion: psycopg.Connection, chemin_relatif: str) -> None:
    """Exécute un fichier du dossier sql/ (création de schéma, de table...)."""
    requete = (DOSSIER_SQL / chemin_relatif).read_text(encoding="utf-8")
    connexion.execute(requete)
    connexion.commit()
