"""Tests de la collecte xeno-canto (DE-69).

Les tests unitaires n'appellent pas l'API et n'ont pas besoin de la clé.
Les tests d'intégration utilisent la base de test (voir conftest.py).
"""

from datetime import date
from typing import Any

import psycopg
import pytest

from oiseaux.ingestion import xeno_canto

CLE_FACTICE = "cle-de-test-123"

# Exemple tiré de la documentation de l'API v3, adapté à la Gironde
ENREGISTREMENT = {
    "id": "694038",
    "gen": "Troglodytes",
    "sp": "troglodytes",
    "grp": "birds",
    "status": "identified",
    "en": "Eurasian Wren",
    "rec": "Jean Dupont",
    "cnt": "France",
    "loc": "12 chemin des Vignes, Pessac",
    "lat": "44.80637",
    "lon": "-0.63172",
    "type": "song",
    "url": "https://xeno-canto.org/694038",
    "file": "https://xeno-canto.org/694038/download",
    "sono": {"small": "s.png", "med": "https://xeno-canto.org/sono-med.png", "large": "l.png"},
    "lic": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "q": "A",
    "length": "4:08",
    "time": "09:30",
    "date": "2021-12-23",
    "uploaded": "2021-12-27",
    "also": ["Turdus viscivorus", "Parus major"],
    "rmk": "Enregistré depuis mon jardin, au fond de l'allée.",
}


class FausseReponse:
    def __init__(self, status_code: int, contenu: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._contenu = contenu or {}

    def json(self) -> dict[str, Any]:
        return self._contenu


class FausseSession:
    def __init__(self, reponses: list[FausseReponse]) -> None:
        self.reponses = list(reponses)
        self.appels: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: int) -> FausseReponse:
        self.appels.append(dict(params))
        return self.reponses.pop(0)


def page(numero: int, nb_pages: int, *ids: int) -> FausseReponse:
    contenu = {"page": numero, "numPages": nb_pages, "recordings": [{"id": str(i)} for i in ids]}
    return FausseReponse(200, contenu)


def ne_pas_attendre(_secondes: float) -> None:
    pass


# --- clé d'API ------------------------------------------------------------------------


def test_lire_cle_echoue_clairement_si_absente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(xeno_canto.VARIABLE_CLE, raising=False)

    with pytest.raises(xeno_canto.CleManquanteError, match="XENO_CANTO_API_KEY"):
        xeno_canto.lire_cle()


@pytest.mark.parametrize(
    ("contenu", "attendu"),
    [
        # Format décrit dans la documentation
        ({"error": {"code": "invalid_key", "message": "Missing key"}}, "invalid_key – Missing key"),
        # Format observé sur l'API réelle (réponse 401 avec une clé invalide)
        ({"error": "client_error", "message": "Missing key"}, "client_error – Missing key"),
    ],
)
def test_la_cle_n_apparait_pas_dans_les_erreurs(contenu: dict[str, Any], attendu: str) -> None:
    session = FausseSession([FausseReponse(401, contenu)])

    with pytest.raises(xeno_canto.ApiIndisponibleError) as erreur:
        list(xeno_canto.extraire(session, CLE_FACTICE, attendre=ne_pas_attendre))

    assert CLE_FACTICE not in str(erreur.value)
    assert attendu in str(erreur.value)


# --- requête et pagination ------------------------------------------------------------


def test_construire_requete_oiseaux_gironde() -> None:
    assert xeno_canto.construire_requete() == "grp:birds box:44.19,-1.27,45.58,0.32"


def test_construire_requete_incrementale() -> None:
    requete = xeno_canto.construire_requete(date(2026, 11, 1))

    assert requete.endswith(" since:2026-11-01")


def test_extraire_parcourt_toutes_les_pages() -> None:
    session = FausseSession([page(1, 3, 1, 2), page(2, 3, 3, 4), page(3, 3, 5)])

    ids = [e["id"] for e in xeno_canto.extraire(session, CLE_FACTICE, attendre=ne_pas_attendre)]

    assert ids == ["1", "2", "3", "4", "5"]
    assert [appel["page"] for appel in session.appels] == [1, 2, 3]
    assert all(appel["key"] == CLE_FACTICE for appel in session.appels)


def test_extraire_respecte_pages_max() -> None:
    session = FausseSession([page(1, 3, 1), page(2, 3, 2)])

    ids = [
        e["id"]
        for e in xeno_canto.extraire(session, CLE_FACTICE, pages_max=2, attendre=ne_pas_attendre)
    ]

    assert ids == ["1", "2"]


def test_appeler_api_reessaie_apres_une_erreur_503() -> None:
    session = FausseSession([FausseReponse(503), page(1, 1, 7)])
    attentes: list[float] = []

    resultat = xeno_canto.appeler_api(session, {}, attendre=attentes.append)

    assert resultat["recordings"] == [{"id": "7"}]
    assert attentes == [2]


# --- licences et formats --------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "code", "reutilisable"),
    [
        ("https://creativecommons.org/licenses/by-nc-sa/4.0/", "by-nc-sa", True),
        ("https://creativecommons.org/licenses/by/4.0/", "by", True),
        ("https://creativecommons.org/licenses/by-nc-nd/2.5/", "by-nc-nd", False),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "cc0", True),
        ("", None, False),
    ],
)
def test_licences(url: str, code: str | None, reutilisable: bool) -> None:
    assert xeno_canto.code_licence(url) == code
    assert xeno_canto.est_reutilisable({"lic": url}) is reutilisable


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [("2021-12-23", date(2021, 12, 23)), ("2019-05-00", None), ("?", None), (None, None)],
)
def test_lire_date_accepte_les_dates_incompletes(texte: str | None, attendu: date | None) -> None:
    assert xeno_canto.lire_date(texte) == attendu


@pytest.mark.parametrize(
    ("texte", "attendu"), [("4:08", 248), ("0:05", 5), ("1:02:03", 3723), ("", None), ("?", None)]
)
def test_lire_duree(texte: str, attendu: int | None) -> None:
    assert xeno_canto.lire_duree(texte) == attendu


# --- transformer ----------------------------------------------------------------------


def test_transformer_garde_les_champs_utiles() -> None:
    ligne = xeno_canto.transformer(ENREGISTREMENT)

    assert ligne["id"] == 694038
    assert ligne["nom_scientifique"] == "Troglodytes troglodytes"
    assert ligne["licence"] == "by-nc-sa"
    assert ligne["duree_s"] == 248
    assert ligne["enregistre_le"] == date(2021, 12, 23)
    assert ligne["especes_en_fond"] == ["Turdus viscivorus", "Parus major"]
    assert ligne["url_sonagramme"] == "https://xeno-canto.org/sono-med.png"


def test_transformer_ne_garde_aucune_donnee_personnelle() -> None:
    valeurs = " ".join(str(v) for v in xeno_canto.transformer(ENREGISTREMENT).values())

    assert "Jean Dupont" not in valeurs  # enregistreur
    assert "chemin des Vignes" not in valeurs  # lieu-dit
    assert "jardin" not in valeurs  # remarque libre


def test_transformer_arrondit_ou_vide_les_coordonnees() -> None:
    ligne = xeno_canto.transformer(ENREGISTREMENT)
    masquee = xeno_canto.transformer({**ENREGISTREMENT, "lat": "", "lon": None})

    assert (ligne["latitude"], ligne["longitude"]) == (44.806, -0.632)
    assert (masquee["latitude"], masquee["longitude"]) == (None, None)


# --- intégration (PostgreSQL + PostGIS) -----------------------------------------------


@pytest.mark.integration
def test_charger_puis_mettre_a_jour_sans_doublon(connexion: psycopg.Connection) -> None:
    ligne = xeno_canto.transformer(ENREGISTREMENT)
    xeno_canto.charger(connexion, [ligne])
    xeno_canto.charger(connexion, [{**ligne, "qualite": "B"}])

    lignes = connexion.execute(
        "SELECT id, qualite, especes_en_fond, round(st_y(geom)::numeric, 3) "
        "FROM brut.xeno_canto_enregistrements"
    ).fetchall()

    assert len(lignes) == 1
    identifiant, qualite, especes, latitude = lignes[0]
    assert (identifiant, qualite) == (694038, "B")
    assert especes == ["Turdus viscivorus", "Parus major"]
    assert float(latitude) == 44.806


@pytest.mark.integration
def test_derniere_mise_en_ligne(connexion: psycopg.Connection) -> None:
    assert xeno_canto.derniere_mise_en_ligne(connexion) is None

    xeno_canto.charger(connexion, [xeno_canto.transformer(ENREGISTREMENT)])

    assert xeno_canto.derniere_mise_en_ligne(connexion) == date(2021, 12, 27)
