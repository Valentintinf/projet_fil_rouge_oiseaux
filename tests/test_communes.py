"""Tests du référentiel des communes et du rattachement des observations aux communes."""

import json
from typing import Any

import psycopg
import pytest

from oiseaux.ingestion import communes, inaturalist


def carre(x_min: float, y_min: float, cote: float) -> dict[str, Any]:
    """Contour GeoJSON d'un carré, pour simuler une commune."""
    x_max, y_max = x_min + cote, y_min + cote
    anneau = [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max], [x_min, y_min]]
    return {"type": "Polygon", "coordinates": [anneau]}


def commune_geojson(code: str, nom: str, epci: str, contour: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"code": code, "nom": nom, "codeEpci": epci, "population": 1000},
        "geometry": contour,
    }


# Deux communes fictives côte à côte : l'une dans Bordeaux Métropole, l'autre non.
COMMUNE_METROPOLE = commune_geojson(
    "33063", "Bordeaux", communes.EPCI_BORDEAUX_METROPOLE, carre(-0.7, 44.8, 0.1)
)
COMMUNE_HORS_METROPOLE = commune_geojson("33051", "Le Teich", "243301165", carre(-1.1, 44.6, 0.1))


class FausseSession:
    def __init__(self, contenu: dict[str, Any]) -> None:
        self.contenu = contenu
        self.params: dict[str, Any] = {}

    def get(self, url: str, params: dict[str, Any], timeout: int) -> FausseSession:
        self.params = params
        return self

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self.contenu


# --- tests unitaires -------------------------------------------------------------------


def test_telecharger_demande_les_contours_en_geojson() -> None:
    session = FausseSession({"features": [COMMUNE_METROPOLE]})

    resultat = communes.telecharger(session)

    assert resultat == [COMMUNE_METROPOLE]
    assert session.params["format"] == "geojson"
    assert session.params["geometry"] == "contour"
    assert "codeEpci" in session.params["fields"]


def test_transformer_garde_le_code_insee_l_epci_et_le_contour() -> None:
    ligne = communes.transformer(COMMUNE_METROPOLE)

    assert ligne["code_insee"] == "33063"
    assert ligne["nom"] == "Bordeaux"
    assert ligne["code_epci"] == communes.EPCI_BORDEAUX_METROPOLE
    assert json.loads(ligne["contour"])["type"] == "Polygon"


# --- tests d'intégration (PostgreSQL + PostGIS) ---------------------------------------


@pytest.mark.integration
def test_chaque_observation_est_rattachee_a_sa_commune(
    connexion: psycopg.Connection, ligne_observation: dict[str, Any]
) -> None:
    communes.charger(
        connexion, [communes.transformer(c) for c in (COMMUNE_METROPOLE, COMMUNE_HORS_METROPOLE)]
    )
    obs = ligne_observation
    inaturalist.charger(
        connexion,
        [
            {**obs, "id": 1, "longitude": -0.65, "latitude": 44.85},  # dans Bordeaux
            {**obs, "id": 2, "longitude": -1.05, "latitude": 44.65},  # dans Le Teich
            {**obs, "id": 3, "longitude": -1.50, "latitude": 44.00},  # hors des communes
        ],
    )

    lignes = connexion.execute(
        "SELECT observation_id, commune, bordeaux_metropole "
        "FROM brut.inaturalist_observations_communes ORDER BY observation_id"
    ).fetchall()

    assert lignes == [(1, "Bordeaux", True), (2, "Le Teich", False), (3, None, False)]


@pytest.mark.integration
def test_recharger_les_communes_ne_cree_pas_de_doublon(connexion: psycopg.Connection) -> None:
    ligne = communes.transformer(COMMUNE_METROPOLE)
    communes.charger(connexion, [ligne])
    communes.charger(connexion, [{**ligne, "population": 2000}])

    lignes = connexion.execute("SELECT code_insee, population FROM ref.communes").fetchall()

    assert lignes == [("33063", 2000)]
