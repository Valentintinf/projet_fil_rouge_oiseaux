"""Tests unitaires de la collecte iNaturalist : aucun appel réseau, aucune base de données."""

from datetime import UTC, datetime
from typing import Any

import pytest
import requests

from oiseaux.ingestion import inaturalist

OBSERVATION = {
    "id": 611995,
    "observed_on": "1980-07-20",
    "time_observed_at": None,
    "created_at": "2014-04-07T13:15:21+01:00",
    "updated_at": "2016-06-23T10:44:03+01:00",
    "quality_grade": "research",
    "license_code": "cc-by-nc",
    "obscured": False,
    "captive": False,
    "public_positional_accuracy": 3023,
    "uri": "https://www.inaturalist.org/observations/611995",
    "place_guess": "12 rue des Lilas, Le Teich",
    "geojson": {"type": "Point", "coordinates": [-1.022936, 44.645377]},
    "taxon": {
        "id": 13071,
        "name": "Luscinia svecica",
        "rank": "species",
        "preferred_common_name": "gorgebleue à miroir",
    },
    "user": {"id": 42, "login": "observateur_du_bassin", "name": "Jean Dupont"},
}


class FausseReponse:
    def __init__(self, status_code: int, contenu: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._contenu = contenu or {}

    def json(self) -> dict[str, Any]:
        return self._contenu

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"Erreur {self.status_code}")


class FausseSession:
    """Remplace requests.Session : renvoie des réponses préparées et garde les appels."""

    def __init__(self, reponses: list[FausseReponse]) -> None:
        self.reponses = list(reponses)
        self.appels: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: int) -> FausseReponse:
        self.appels.append(dict(params))
        return self.reponses.pop(0)


def page(*ids: int) -> FausseReponse:
    return FausseReponse(200, {"results": [{"id": i} for i in ids]})


def ne_pas_attendre(_secondes: float) -> None:
    pass


# --- transformer -----------------------------------------------------------------------


def test_transformer_garde_les_champs_utiles() -> None:
    ligne = inaturalist.transformer(OBSERVATION)

    assert ligne["id"] == 611995
    assert ligne["nom_scientifique"] == "Luscinia svecica"
    assert ligne["nom_francais"] == "gorgebleue à miroir"
    assert ligne["qualite"] == "research"
    assert ligne["licence"] == "cc-by-nc"
    assert ligne["precision_m"] == 3023


def test_transformer_ne_garde_aucune_donnee_personnelle() -> None:
    ligne = inaturalist.transformer(OBSERVATION)
    valeurs = " ".join(str(valeur) for valeur in ligne.values())

    assert "observateur_du_bassin" not in valeurs
    assert "Jean Dupont" not in valeurs
    assert "rue des Lilas" not in valeurs


def test_transformer_arrondit_les_coordonnees_a_3_decimales() -> None:
    ligne = inaturalist.transformer(OBSERVATION)

    assert ligne["latitude"] == 44.645
    assert ligne["longitude"] == -1.023


def test_transformer_accepte_une_observation_sans_taxon_ni_coordonnees() -> None:
    observation = {**OBSERVATION, "taxon": None, "geojson": None}

    ligne = inaturalist.transformer(observation)

    assert ligne["taxon_id"] is None
    assert ligne["latitude"] is None
    assert ligne["longitude"] is None


@pytest.mark.parametrize(
    ("licence", "attendu"),
    [("cc-by", True), ("cc0", True), ("cc-by-nc-nd", False), (None, False)],
)
def test_est_reutilisable_selon_la_licence(licence: str | None, attendu: bool) -> None:
    assert inaturalist.est_reutilisable({**OBSERVATION, "license_code": licence}) is attendu


# --- extraire --------------------------------------------------------------------------


def test_extraire_pagine_avec_id_above(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inaturalist, "TAILLE_PAGE", 2)
    session = FausseSession([page(1, 2), page(3, 4), page(5)])

    ids = [o["id"] for o in inaturalist.extraire(session, attendre=ne_pas_attendre)]

    assert ids == [1, 2, 3, 4, 5]
    assert [appel["id_above"] for appel in session.appels] == [0, 2, 4]


def test_extraire_s_arrete_sur_une_page_vide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inaturalist, "TAILLE_PAGE", 2)
    session = FausseSession([page(1, 2), page()])

    ids = [o["id"] for o in inaturalist.extraire(session, attendre=ne_pas_attendre)]

    assert ids == [1, 2]
    assert len(session.appels) == 2


def test_extraire_respecte_pages_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inaturalist, "TAILLE_PAGE", 2)
    session = FausseSession([page(1, 2), page(3, 4), page(5, 6)])

    ids = [o["id"] for o in inaturalist.extraire(session, pages_max=2, attendre=ne_pas_attendre)]

    assert ids == [1, 2, 3, 4]
    assert len(session.appels) == 2


def test_extraire_filtre_oiseaux_gironde_et_licences() -> None:
    session = FausseSession([page()])

    list(inaturalist.extraire(session, attendre=ne_pas_attendre))

    params = session.appels[0]
    assert params["iconic_taxa"] == "Aves"
    assert params["place_id"] == inaturalist.PLACE_GIRONDE
    assert params["license"] == "cc0,cc-by,cc-by-sa,cc-by-nc,cc-by-nc-sa"
    assert "updated_since" not in params


def test_extraire_incremental_ajoute_updated_since() -> None:
    session = FausseSession([page()])
    depuis = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    list(inaturalist.extraire(session, depuis=depuis, attendre=ne_pas_attendre))

    assert session.appels[0]["updated_since"] == "2026-11-01T12:00:00+00:00"


# --- appeler_api -----------------------------------------------------------------------


def test_appeler_api_reessaie_apres_une_erreur_429() -> None:
    session = FausseSession([FausseReponse(429), FausseReponse(200, {"results": []})])
    attentes: list[float] = []

    resultat = inaturalist.appeler_api(session, {}, attendre=attentes.append)

    assert resultat == {"results": []}
    assert attentes == [2]


def test_appeler_api_abandonne_apres_trop_d_erreurs() -> None:
    session = FausseSession([FausseReponse(503)] * inaturalist.TENTATIVES_MAX)

    with pytest.raises(inaturalist.ApiIndisponibleError):
        inaturalist.appeler_api(session, {}, attendre=ne_pas_attendre)


def test_appeler_api_ne_reessaie_pas_une_erreur_400() -> None:
    session = FausseSession([FausseReponse(400)])

    with pytest.raises(requests.HTTPError):
        inaturalist.appeler_api(session, {}, attendre=ne_pas_attendre)

    assert len(session.appels) == 1
