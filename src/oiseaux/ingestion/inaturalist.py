"""Collecte des observations d'oiseaux de la Gironde depuis l'API iNaturalist.

Source : https://api.inaturalist.org/v1/observations (API publique, sans authentification).

Choix de conception :
- Pagination par ``id_above`` : l'API limite la pagination classique à 10 000 résultats.
- Collecte incrémentale avec ``updated_since`` : après le premier chargement, on ne relit
  que les observations créées ou modifiées depuis la dernière collecte.
- Licences : on ne garde que les observations sous licence réutilisable (voir LICENCES).
- RGPD : aucune donnée sur l'observateur n'est conservée (ni identifiant, ni pseudo, ni
  ``place_guess``, qui peut contenir une adresse). Les coordonnées sont arrondies à
  3 décimales, soit environ 100 m.
- Respect de l'API : une requête par seconde au plus, et nouvelles tentatives avec un délai
  croissant en cas d'erreur 429 ou 5xx.

Lancement : ``python -m oiseaux.ingestion.inaturalist --help``
"""

import argparse
import logging
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import psycopg
import requests

from oiseaux.base_de_donnees import connecter, executer_script

URL_API = "https://api.inaturalist.org/v1/observations"
PLACE_GIRONDE = 30139
LICENCES = ("cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa")
TAILLE_PAGE = 200
PAUSE_ENTRE_REQUETES_S = 1.0
TENTATIVES_MAX = 5
CODES_A_REESSAYER = (429, 500, 502, 503, 504)
DECIMALES_COORDONNEES = 3
USER_AGENT = (
    "oiseaux-gironde/0.1 (projet pedagogique; "
    "+https://github.com/Valentintinf/projet_fil_rouge_oiseaux)"
)

REQUETE_UPSERT = """
INSERT INTO brut.inaturalist_observations (
    id, observe_le, observe_a, cree_le, mis_a_jour_le, taxon_id, nom_scientifique,
    nom_francais, rang, latitude, longitude, precision_m, coordonnees_floutees, captif,
    qualite, licence, url
) VALUES (
    %(id)s, %(observe_le)s, %(observe_a)s, %(cree_le)s, %(mis_a_jour_le)s, %(taxon_id)s,
    %(nom_scientifique)s, %(nom_francais)s, %(rang)s, %(latitude)s, %(longitude)s,
    %(precision_m)s, %(coordonnees_floutees)s, %(captif)s, %(qualite)s, %(licence)s, %(url)s
)
ON CONFLICT (id) DO UPDATE SET
    observe_le = EXCLUDED.observe_le,
    observe_a = EXCLUDED.observe_a,
    mis_a_jour_le = EXCLUDED.mis_a_jour_le,
    taxon_id = EXCLUDED.taxon_id,
    nom_scientifique = EXCLUDED.nom_scientifique,
    nom_francais = EXCLUDED.nom_francais,
    rang = EXCLUDED.rang,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    precision_m = EXCLUDED.precision_m,
    coordonnees_floutees = EXCLUDED.coordonnees_floutees,
    captif = EXCLUDED.captif,
    qualite = EXCLUDED.qualite,
    licence = EXCLUDED.licence,
    url = EXCLUDED.url,
    ingere_le = now()
"""

journal = logging.getLogger(__name__)

Observation = dict[str, Any]
Attente = Callable[[float], None]


class ApiIndisponibleError(RuntimeError):
    """L'API iNaturalist est restée en erreur après toutes les tentatives."""


def appeler_api(
    session: requests.Session, params: dict[str, Any], attendre: Attente = time.sleep
) -> dict[str, Any]:
    """Appelle l'API et réessaie, avec un délai croissant, en cas d'erreur temporaire."""
    for tentative in range(1, TENTATIVES_MAX + 1):
        delai = 2**tentative
        try:
            reponse = session.get(URL_API, params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as erreur:
            journal.warning("Erreur réseau (%s), nouvel essai dans %s s", erreur, delai)
            attendre(delai)
            continue
        if reponse.status_code in CODES_A_REESSAYER:
            journal.warning(
                "Réponse %s de l'API, nouvel essai dans %s s", reponse.status_code, delai
            )
            attendre(delai)
            continue
        reponse.raise_for_status()
        return reponse.json()
    raise ApiIndisponibleError(f"L'API iNaturalist ne répond pas après {TENTATIVES_MAX} tentatives")


def extraire(
    session: requests.Session,
    *,
    depuis: datetime | None = None,
    pages_max: int | None = None,
    attendre: Attente = time.sleep,
) -> Iterator[Observation]:
    """Renvoie les observations d'oiseaux de la Gironde, de la plus ancienne à la plus récente."""
    id_minimum = 0
    pages_lues = 0
    while pages_max is None or pages_lues < pages_max:
        params: dict[str, Any] = {
            "iconic_taxa": "Aves",
            "place_id": PLACE_GIRONDE,
            "license": ",".join(LICENCES),
            "locale": "fr",
            "order_by": "id",
            "order": "asc",
            "per_page": TAILLE_PAGE,
            "id_above": id_minimum,
        }
        if depuis is not None:
            params["updated_since"] = depuis.isoformat()

        resultats = appeler_api(session, params, attendre)["results"]
        pages_lues += 1
        yield from resultats

        if len(resultats) < TAILLE_PAGE:
            return
        id_minimum = resultats[-1]["id"]
        attendre(PAUSE_ENTRE_REQUETES_S)


def arrondir(valeur: float | None) -> float | None:
    """Arrondit une coordonnée pour ne pas exposer un lieu précis (domicile, jardin...)."""
    return None if valeur is None else round(valeur, DECIMALES_COORDONNEES)


def est_reutilisable(observation: Observation) -> bool:
    """Vérifie que la licence de l'observation autorise sa réutilisation."""
    return observation.get("license_code") in LICENCES


def transformer(observation: Observation) -> dict[str, Any]:
    """Garde uniquement les champs utiles et sans donnée personnelle."""
    taxon = observation.get("taxon") or {}
    longitude, latitude = (observation.get("geojson") or {}).get("coordinates") or (None, None)
    return {
        "id": observation["id"],
        "observe_le": observation.get("observed_on"),
        "observe_a": observation.get("time_observed_at"),
        "cree_le": observation["created_at"],
        "mis_a_jour_le": observation["updated_at"],
        "taxon_id": taxon.get("id"),
        "nom_scientifique": taxon.get("name"),
        "nom_francais": taxon.get("preferred_common_name"),
        "rang": taxon.get("rank"),
        "latitude": arrondir(latitude),
        "longitude": arrondir(longitude),
        "precision_m": observation.get("public_positional_accuracy"),
        "coordonnees_floutees": bool(observation.get("obscured")),
        "captif": bool(observation.get("captive")),
        "qualite": observation["quality_grade"],
        "licence": observation["license_code"],
        "url": observation["uri"],
    }


def charger(connexion: psycopg.Connection, lignes: list[dict[str, Any]]) -> int:
    """Insère les lignes, ou les met à jour si l'observation existe déjà."""
    if not lignes:
        return 0
    with connexion.cursor() as curseur:
        curseur.executemany(REQUETE_UPSERT, lignes)
    connexion.commit()
    return len(lignes)


def derniere_mise_a_jour(connexion: psycopg.Connection) -> datetime | None:
    """Date de mise à jour la plus récente déjà chargée : point de départ de la collecte."""
    ligne = connexion.execute(
        "SELECT MAX(mis_a_jour_le) FROM brut.inaturalist_observations"
    ).fetchone()
    return ligne[0] if ligne else None


def executer(*, pages_max: int | None = None, complet: bool = False) -> int:
    """Lance la collecte complète ou incrémentale et renvoie le nombre de lignes chargées."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    with connecter() as connexion:
        executer_script(connexion, "brut/inaturalist_observations.sql")
        depuis = None if complet else derniere_mise_a_jour(connexion)
        journal.info("Collecte %s", f"depuis le {depuis.isoformat()}" if depuis else "complète")

        total = 0
        lot: list[dict[str, Any]] = []
        ignorees = 0
        for observation in extraire(session, depuis=depuis, pages_max=pages_max):
            if not est_reutilisable(observation):
                ignorees += 1
                continue
            lot.append(transformer(observation))
            if len(lot) >= TAILLE_PAGE:
                total += charger(connexion, lot)
                journal.info("%s observations chargées", total)
                lot = []
        total += charger(connexion, lot)

    journal.info("Terminé : %s observations chargées, %s ignorées (licence)", total, ignorees)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pages-max", type=int, help="nombre maximum de pages de 200 observations (pour tester)"
    )
    parser.add_argument(
        "--complet", action="store_true", help="tout recharger au lieu d'une collecte incrémentale"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    executer(pages_max=arguments.pages_max, complet=arguments.complet)


if __name__ == "__main__":
    main()
