"""Collecte des enregistrements de chants d'oiseaux de la Gironde depuis xeno-canto.

Source : https://xeno-canto.org/api/3/recordings (API v3, clé obligatoire et gratuite).
Ticket Jira : DE-69. Source suggérée par le formateur.

Choix de conception :
- Clé d'API : lue dans la variable d'environnement XENO_CANTO_API_KEY (fichier .env, jamais
  commité). Elle n'apparaît dans aucun message d'erreur ni aucun journal.
- Recherche par mots-clés (obligatoire en v3) : ``grp:birds`` et un rectangle ``box:`` autour
  de la Gironde. Le rattachement précis aux communes se fait ensuite avec PostGIS. Les
  recherches par rectangle excluent déjà les espèces protégées.
- Collecte incrémentale avec ``since:`` : on ne relit que ce qui a été mis en ligne depuis
  la dernière collecte (date de mise en ligne, au jour près).
- Licences : on écarte les licences « pas de modification » (ND) par prudence, comme pour
  iNaturalist. On ne télécharge aucun son : on garde les métadonnées et le lien.
- RGPD : on ne garde ni le nom de l'enregistreur, ni le lieu-dit, ni les remarques libres
  (qui peuvent contenir des informations personnelles). Coordonnées arrondies à environ 100 m.

Lancement : ``python -m oiseaux.ingestion.xeno_canto --help``
"""

import argparse
import logging
import os
import re
import time
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import psycopg
import requests

from oiseaux.base_de_donnees import connecter, executer_script

URL_API = "https://xeno-canto.org/api/3/recordings"
VARIABLE_CLE = "XENO_CANTO_API_KEY"
# Rectangle englobant la Gironde : lat_min, lon_min, lat_max, lon_max
RECTANGLE_GIRONDE = "44.19,-1.27,45.58,0.32"
TAILLE_PAGE = 500
PAUSE_ENTRE_REQUETES_S = 1.0
TENTATIVES_MAX = 5
CODES_A_REESSAYER = (429, 500, 502, 503, 504)
DECIMALES_COORDONNEES = 3
USER_AGENT = (
    "oiseaux-gironde/0.1 (projet pedagogique; "
    "+https://github.com/Valentintinf/projet_fil_rouge_oiseaux)"
)

REQUETE_UPSERT = """
INSERT INTO brut.xeno_canto_enregistrements (
    id, nom_scientifique, nom_anglais, statut_identification, type_son, qualite,
    enregistre_le, heure, duree_s, latitude, longitude, especes_en_fond, licence,
    url, url_son, url_sonagramme, mis_en_ligne_le
) VALUES (
    %(id)s, %(nom_scientifique)s, %(nom_anglais)s, %(statut_identification)s, %(type_son)s,
    %(qualite)s, %(enregistre_le)s, %(heure)s, %(duree_s)s, %(latitude)s, %(longitude)s,
    %(especes_en_fond)s, %(licence)s, %(url)s, %(url_son)s, %(url_sonagramme)s,
    %(mis_en_ligne_le)s
)
ON CONFLICT (id) DO UPDATE SET
    nom_scientifique = EXCLUDED.nom_scientifique,
    nom_anglais = EXCLUDED.nom_anglais,
    statut_identification = EXCLUDED.statut_identification,
    type_son = EXCLUDED.type_son,
    qualite = EXCLUDED.qualite,
    enregistre_le = EXCLUDED.enregistre_le,
    heure = EXCLUDED.heure,
    duree_s = EXCLUDED.duree_s,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    especes_en_fond = EXCLUDED.especes_en_fond,
    licence = EXCLUDED.licence,
    url = EXCLUDED.url,
    url_son = EXCLUDED.url_son,
    url_sonagramme = EXCLUDED.url_sonagramme,
    mis_en_ligne_le = EXCLUDED.mis_en_ligne_le,
    ingere_le = now()
"""

journal = logging.getLogger(__name__)

Enregistrement = dict[str, Any]
Attente = Callable[[float], None]


class CleManquanteError(RuntimeError):
    """La clé d'API xeno-canto n'est pas définie dans l'environnement."""


class ApiIndisponibleError(RuntimeError):
    """L'API xeno-canto est en erreur. Le message ne contient jamais la clé."""


def lire_cle() -> str:
    """Lit la clé d'API dans l'environnement, sans jamais l'afficher."""
    cle = os.environ.get(VARIABLE_CLE, "").strip()
    if not cle:
        raise CleManquanteError(f"Variable {VARIABLE_CLE} absente : ajoutez votre clé dans .env")
    return cle


def construire_requete(depuis: date | None = None) -> str:
    """Recherche par mots-clés : oiseaux de la Gironde, mis en ligne depuis une date."""
    requete = f"grp:birds box:{RECTANGLE_GIRONDE}"
    if depuis is not None:
        requete += f" since:{depuis.isoformat()}"
    return requete


def appeler_api(
    session: requests.Session, params: dict[str, Any], attendre: Attente = time.sleep
) -> dict[str, Any]:
    """Appelle l'API, réessaie en cas d'erreur temporaire, et masque la clé dans les erreurs."""
    for tentative in range(1, TENTATIVES_MAX + 1):
        delai = 2**tentative
        try:
            reponse = session.get(URL_API, params=params, timeout=60)
        except requests.ConnectionError, requests.Timeout:
            # Le message d'origine contient l'URL complète, donc la clé : on ne l'affiche pas.
            journal.warning("Erreur réseau, nouvel essai dans %s s", delai)
            attendre(delai)
            continue
        if reponse.status_code in CODES_A_REESSAYER:
            journal.warning("Réponse %s, nouvel essai dans %s s", reponse.status_code, delai)
            attendre(delai)
            continue
        if reponse.status_code != 200:
            raise ApiIndisponibleError(
                f"Erreur {reponse.status_code} de l'API xeno-canto : {extraire_erreur(reponse)}"
            )
        return reponse.json()
    raise ApiIndisponibleError(f"L'API xeno-canto ne répond pas après {TENTATIVES_MAX} tentatives")


def extraire_erreur(reponse: requests.Response) -> str:
    """Message d'erreur renvoyé par l'API (sans l'URL, qui contient la clé)."""
    try:
        contenu = reponse.json()
    except ValueError:
        return "réponse illisible"
    erreur = contenu.get("error")
    # Deux formats existent : {"error": {"code", "message"}} (documenté)
    # et {"error": "client_error", "message": "..."} (observé sur l'API réelle).
    if isinstance(erreur, dict):
        return f"{erreur.get('code')} – {erreur.get('message')}"
    return f"{erreur} – {contenu.get('message')}"


def extraire(
    session: requests.Session,
    cle: str,
    *,
    depuis: date | None = None,
    pages_max: int | None = None,
    attendre: Attente = time.sleep,
) -> Iterator[Enregistrement]:
    """Renvoie les enregistrements d'oiseaux de la Gironde, page par page."""
    page = 1
    while pages_max is None or page <= pages_max:
        params = {
            "query": construire_requete(depuis),
            "key": cle,
            "per_page": TAILLE_PAGE,
            "page": page,
        }
        resultat = appeler_api(session, params, attendre)
        yield from resultat.get("recordings", [])
        if page >= int(resultat.get("numPages", 1)):
            return
        page += 1
        attendre(PAUSE_ENTRE_REQUETES_S)


def code_licence(url: str | None) -> str | None:
    """Transforme l'URL de licence en code court.

    « https://creativecommons.org/licenses/by-nc-sa/4.0/ » donne « by-nc-sa ».
    Une licence « publicdomain » donne « cc0 ».
    """
    if not url:
        return None
    if "publicdomain" in url:
        return "cc0"
    trouve = re.search(r"/licenses/([a-z-]+)/", url)
    return trouve.group(1) if trouve else None


def est_reutilisable(enregistrement: Enregistrement) -> bool:
    """Écarte les licences inconnues et les licences « pas de modification » (ND)."""
    code = code_licence(enregistrement.get("lic"))
    return code is not None and "nd" not in code.split("-")


def lire_date(texte: str | None) -> date | None:
    """Lit une date xeno-canto. Les dates incomplètes (« 2019-05-00 », « ? ») donnent None."""
    try:
        return date.fromisoformat(texte or "")
    except ValueError:
        return None


def lire_duree(texte: str | None) -> int | None:
    """Convertit une durée « 4:08 » ou « 1:02:03 » en secondes."""
    if not texte or not re.fullmatch(r"\d+(:\d{1,2}){1,2}", texte):
        return None
    secondes = 0
    for morceau in texte.split(":"):
        secondes = secondes * 60 + int(morceau)
    return secondes


def lire_coordonnee(texte: str | None) -> float | None:
    """Lit et arrondit une coordonnée (vide ou masquée pour les espèces protégées : None)."""
    try:
        return round(float(texte), DECIMALES_COORDONNEES) if texte not in (None, "") else None
    except ValueError:
        return None


def transformer(enregistrement: Enregistrement) -> dict[str, Any]:
    """Garde les champs utiles, sans donnée personnelle, et normalise les formats."""
    sonagramme = (enregistrement.get("sono") or {}).get("med") or None
    genre, espece = enregistrement.get("gen", ""), enregistrement.get("sp", "")
    return {
        "id": int(enregistrement["id"]),
        "nom_scientifique": f"{genre} {espece}".strip(),
        "nom_anglais": enregistrement.get("en") or None,
        "statut_identification": enregistrement.get("status") or None,
        "type_son": enregistrement.get("type") or None,
        "qualite": enregistrement.get("q") or None,
        "enregistre_le": lire_date(enregistrement.get("date")),
        "heure": enregistrement.get("time") or None,
        "duree_s": lire_duree(enregistrement.get("length")),
        "latitude": lire_coordonnee(enregistrement.get("lat")),
        "longitude": lire_coordonnee(enregistrement.get("lon")),
        "especes_en_fond": [e for e in enregistrement.get("also") or [] if e],
        "licence": code_licence(enregistrement.get("lic")),
        "url": enregistrement.get("url") or f"https://xeno-canto.org/{enregistrement['id']}",
        "url_son": enregistrement.get("file") or None,
        "url_sonagramme": sonagramme,
        "mis_en_ligne_le": lire_date(enregistrement.get("uploaded")),
    }


def charger(connexion: psycopg.Connection, lignes: list[dict[str, Any]]) -> int:
    """Insère les enregistrements, ou les met à jour s'ils existent déjà."""
    if not lignes:
        return 0
    with connexion.cursor() as curseur:
        curseur.executemany(REQUETE_UPSERT, lignes)
    connexion.commit()
    return len(lignes)


def derniere_mise_en_ligne(connexion: psycopg.Connection) -> date | None:
    """Date de mise en ligne la plus récente déjà chargée : point de départ de la collecte."""
    ligne = connexion.execute(
        "SELECT MAX(mis_en_ligne_le) FROM brut.xeno_canto_enregistrements"
    ).fetchone()
    return ligne[0] if ligne else None


def executer(*, pages_max: int | None = None, complet: bool = False) -> int:
    """Lance la collecte complète ou incrémentale et renvoie le nombre de lignes chargées."""
    cle = lire_cle()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    with connecter() as connexion:
        executer_script(connexion, "brut/xeno_canto_enregistrements.sql")
        depuis = None if complet else derniere_mise_en_ligne(connexion)
        journal.info("Collecte %s", f"depuis le {depuis.isoformat()}" if depuis else "complète")

        lignes = []
        ignorees = 0
        for enregistrement in extraire(session, cle, depuis=depuis, pages_max=pages_max):
            if est_reutilisable(enregistrement):
                lignes.append(transformer(enregistrement))
            else:
                ignorees += 1
        total = charger(connexion, lignes)

    journal.info("Terminé : %s enregistrements chargés, %s ignorés (licence)", total, ignorees)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pages-max", type=int, help="nombre maximum de pages de 500 enregistrements"
    )
    parser.add_argument(
        "--complet", action="store_true", help="tout recharger au lieu d'une collecte incrémentale"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    executer(pages_max=arguments.pages_max, complet=arguments.complet)


if __name__ == "__main__":
    main()
