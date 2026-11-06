"""Outils partagés par les tests d'intégration (base PostgreSQL + PostGIS).

Les tests d'intégration tournent dans la CI ou en local si les variables PG* sont définies
(sinon, ils sont ignorés). Ils utilisent une base dédiée, ``<PGDATABASE>_test``, créée si
besoin : la base de travail et les données déjà collectées ne sont jamais touchées.
"""

import os
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import sql

from oiseaux.base_de_donnees import connecter, executer_script
from oiseaux.ingestion.communes import preparer_base


@pytest.fixture
def ligne_observation() -> dict[str, Any]:
    """Une observation iNaturalist déjà transformée, prête à être chargée en base."""
    return {
        "id": 1,
        "observe_le": "2026-04-12",
        "observe_a": "2026-04-12T08:30:00+02:00",
        "cree_le": "2026-04-12T09:00:00+02:00",
        "mis_a_jour_le": "2026-04-12T09:00:00+02:00",
        "taxon_id": 13071,
        "nom_scientifique": "Luscinia svecica",
        "nom_francais": "gorgebleue à miroir",
        "rang": "species",
        "latitude": 44.645,
        "longitude": -1.023,
        "precision_m": 20,
        "coordonnees_floutees": False,
        "captif": False,
        "qualite": "needs_id",
        "licence": "cc-by",
        "url": "https://www.inaturalist.org/observations/1",
    }


@pytest.fixture(scope="session")
def base_de_test() -> str:
    """Crée la base dédiée aux tests si elle n'existe pas, et renvoie son nom."""
    if not os.environ.get("PGHOST"):
        pytest.skip("Pas de base PostgreSQL : variable PGHOST non définie")
    nom = f"{os.environ.get('PGDATABASE', 'postgres')}_test"
    with connecter(autocommit=True) as admin:
        existe = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nom,)).fetchone()
        if not existe:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nom)))
    return nom


@pytest.fixture
def connexion(base_de_test: str) -> Iterator[psycopg.Connection]:
    """Connexion à la base de test, avec des tables créées et vides."""
    with connecter(dbname=base_de_test) as connexion:
        preparer_base(connexion)
        executer_script(connexion, "brut/xeno_canto_enregistrements.sql")
        connexion.execute(
            "TRUNCATE brut.inaturalist_observations, brut.xeno_canto_enregistrements, ref.communes"
        )
        connexion.commit()
        yield connexion
