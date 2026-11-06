"""Ajoute au message de commit la clé du ticket Jira lue dans le nom de la branche.

Exemple : sur la branche « feat/DE-41-biodiv-sports », le message
« feat: collecte des zones sensibles » devient « feat: collecte des zones sensibles (DE-41) ».

Rien n'est ajouté si :
- la branche ne contient pas de clé (par exemple main) ;
- le message contient déjà une clé ;
- la première ligne du message est vide (commit rédigé dans l'éditeur) ;
- c'est un commit de fusion ou d'annulation (« Merge », « Revert »).

Installé par pre-commit comme hook « prepare-commit-msg » (voir .pre-commit-config.yaml).
"""

import re
import sys
from pathlib import Path

MOTIF_CLE = re.compile(r"\bDE-\d+\b")
FICHIER_HEAD = Path(".git/HEAD")


def branche_courante(fichier_head: Path = FICHIER_HEAD) -> str:
    """Nom de la branche courante, ou chaîne vide si HEAD est détaché."""
    contenu = fichier_head.read_text(encoding="utf-8").strip()
    prefixe = "ref: refs/heads/"
    return contenu.removeprefix(prefixe) if contenu.startswith(prefixe) else ""


def ajouter_cle(message: str, branche: str) -> str:
    """Renvoie le message avec la clé de la branche à la fin de la première ligne."""
    cle = MOTIF_CLE.search(branche)
    premiere_ligne, saut, reste = message.partition("\n")
    if (
        cle is None
        or MOTIF_CLE.search(message)
        or not premiere_ligne.strip()
        or premiere_ligne.startswith(("Merge ", "Revert "))
    ):
        return message
    return f"{premiere_ligne.rstrip()} ({cle.group()}){saut or chr(10)}{reste}"


def main(arguments: list[str]) -> int:
    fichier_message = Path(arguments[0])
    message = fichier_message.read_text(encoding="utf-8")
    nouveau = ajouter_cle(message, branche_courante())
    if nouveau != message:
        fichier_message.write_text(nouveau, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
