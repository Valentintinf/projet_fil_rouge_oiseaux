"""Tests d'intégration de la collecte iNaturalist : chargement réel dans PostgreSQL.

La base de test et les fixtures ``connexion`` et ``ligne_observation`` sont dans conftest.py.
"""

from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from oiseaux.ingestion import inaturalist

pytestmark = pytest.mark.integration


def test_charger_insere_puis_met_a_jour_sans_doublon(
    connexion: psycopg.Connection, ligne_observation: dict[str, Any]
) -> None:
    inaturalist.charger(connexion, [ligne_observation])
    modifiee = {**ligne_observation, "qualite": "research", "mis_a_jour_le": "2026-04-20T10:00Z"}
    inaturalist.charger(connexion, [modifiee])

    lignes = connexion.execute("SELECT id, qualite FROM brut.inaturalist_observations").fetchall()

    assert lignes == [(1, "research")]


def test_derniere_mise_a_jour_sert_de_point_de_depart(
    connexion: psycopg.Connection, ligne_observation: dict[str, Any]
) -> None:
    assert inaturalist.derniere_mise_a_jour(connexion) is None

    plus_recente = {**ligne_observation, "id": 2, "mis_a_jour_le": "2026-05-01T00:00:00Z"}
    inaturalist.charger(connexion, [ligne_observation, plus_recente])

    assert inaturalist.derniere_mise_a_jour(connexion) == datetime(2026, 5, 1, tzinfo=UTC)


def test_le_point_geographique_est_calcule_depuis_les_coordonnees(
    connexion: psycopg.Connection, ligne_observation: dict[str, Any]
) -> None:
    inaturalist.charger(connexion, [ligne_observation])

    x, y = connexion.execute(
        "SELECT st_x(geom), st_y(geom) FROM brut.inaturalist_observations"
    ).fetchone()

    assert (round(x, 3), round(y, 3)) == (-1.023, 44.645)
