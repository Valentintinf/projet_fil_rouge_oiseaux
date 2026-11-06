"""Chargement du référentiel des communes de la Gironde, avec leur contour.

Source : API officielle https://geo.api.gouv.fr (données IGN et INSEE, Licence Ouverte).
Pour chaque commune : code INSEE, nom, intercommunalité (EPCI), population et contour.

Le contour sert à rattacher chaque observation à sa commune avec PostGIS
(voir docs/decisions/0001-postgis.md). Le référentiel change rarement : on le recharge
entièrement à chaque lancement.

Lancement : ``python -m oiseaux.ingestion.communes``
"""

import json
import logging
from typing import Any

import psycopg
import requests

from oiseaux.base_de_donnees import connecter, executer_script

DEPARTEMENT = "33"
EPCI_BORDEAUX_METROPOLE = "243300316"
URL_API = f"https://geo.api.gouv.fr/departements/{DEPARTEMENT}/communes"
USER_AGENT = (
    "oiseaux-gironde/0.1 (projet pedagogique; "
    "+https://github.com/Valentintinf/projet_fil_rouge_oiseaux)"
)

REQUETE_UPSERT = """
INSERT INTO ref.communes (code_insee, nom, code_epci, population, geom)
VALUES (
    %(code_insee)s, %(nom)s, %(code_epci)s, %(population)s,
    st_multi(st_setsrid(st_geomfromgeojson(%(contour)s), 4326))
)
ON CONFLICT (code_insee) DO UPDATE SET
    nom = EXCLUDED.nom,
    code_epci = EXCLUDED.code_epci,
    population = EXCLUDED.population,
    geom = EXCLUDED.geom,
    mis_a_jour_le = now()
"""

journal = logging.getLogger(__name__)


def telecharger(session: requests.Session) -> list[dict[str, Any]]:
    """Renvoie les communes du département au format GeoJSON (une « feature » par commune)."""
    params = {"format": "geojson", "geometry": "contour", "fields": "nom,code,codeEpci,population"}
    reponse = session.get(URL_API, params=params, timeout=60)
    reponse.raise_for_status()
    return reponse.json()["features"]


def transformer(commune: dict[str, Any]) -> dict[str, Any]:
    """Prépare une commune pour la base : le contour reste en GeoJSON, PostGIS le convertit."""
    proprietes = commune["properties"]
    return {
        "code_insee": proprietes["code"],
        "nom": proprietes["nom"],
        "code_epci": proprietes.get("codeEpci"),
        "population": proprietes.get("population"),
        "contour": json.dumps(commune["geometry"]),
    }


def charger(connexion: psycopg.Connection, lignes: list[dict[str, Any]]) -> int:
    """Insère les communes, ou les met à jour si elles existent déjà."""
    with connexion.cursor() as curseur:
        curseur.executemany(REQUETE_UPSERT, lignes)
    connexion.commit()
    return len(lignes)


def preparer_base(connexion: psycopg.Connection) -> None:
    """Crée les tables et la vue de rattachement des observations aux communes."""
    executer_script(connexion, "brut/inaturalist_observations.sql")
    executer_script(connexion, "ref/communes.sql")
    executer_script(connexion, "ref/observations_communes.sql")


def executer() -> int:
    """Télécharge et charge les communes, puis renvoie le nombre de communes chargées."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    communes = [transformer(commune) for commune in telecharger(session)]

    with connecter() as connexion:
        preparer_base(connexion)
        total = charger(connexion, communes)

    metropole = sum(1 for c in communes if c["code_epci"] == EPCI_BORDEAUX_METROPOLE)
    journal.info("%s communes chargées, dont %s de Bordeaux Métropole", total, metropole)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    executer()


if __name__ == "__main__":
    main()
