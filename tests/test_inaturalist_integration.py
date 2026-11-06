"""Tests d'intégration : chargement réel dans PostgreSQL.

Ils tournent dans la CI ou en local si les variables PG* sont définies (sinon, ils sont
ignorés). Ils utilisent une base dédiée, ``<PGDATABASE>_test``, créée si besoin : la base de
travail et les données déjà collectées ne sont jamais touchées.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg import sql

from oiseaux.base_de_donnees import connecter, executer_script
from oiseaux.ingestion import inaturalist

pytestmark = pytest.mark.integration

LIGNE = {
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
    with connecter(dbname=base_de_test) as connexion:
        executer_script(connexion, "brut/inaturalist_observations.sql")
        connexion.execute("TRUNCATE brut.inaturalist_observations")
        connexion.commit()
        yield connexion


def test_charger_insere_puis_met_a_jour_sans_doublon(connexion: psycopg.Connection) -> None:
    inaturalist.charger(connexion, [LIGNE])
    ligne_modifiee = {**LIGNE, "qualite": "research", "mis_a_jour_le": "2026-04-20T10:00:00+02:00"}
    inaturalist.charger(connexion, [ligne_modifiee])

    lignes = connexion.execute("SELECT id, qualite FROM brut.inaturalist_observations").fetchall()

    assert lignes == [(1, "research")]


def test_derniere_mise_a_jour_sert_de_point_de_depart(connexion: psycopg.Connection) -> None:
    assert inaturalist.derniere_mise_a_jour(connexion) is None

    plus_recente = {**LIGNE, "id": 2, "mis_a_jour_le": "2026-05-01T00:00:00Z"}
    inaturalist.charger(connexion, [LIGNE, plus_recente])

    assert inaturalist.derniere_mise_a_jour(connexion) == datetime(2026, 5, 1, tzinfo=UTC)
