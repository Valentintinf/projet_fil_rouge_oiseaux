"""Tests du hook qui ajoute la clé Jira de la branche au message de commit."""

from pathlib import Path

import pytest

import ajouter_cle_jira as hook


@pytest.mark.parametrize(
    ("message", "branche", "attendu"),
    [
        # Cas nominal : la clé de la branche est ajoutée à la fin de la première ligne
        ("feat: zones sensibles\n", "feat/DE-41-biodiv-sports", "feat: zones sensibles (DE-41)\n"),
        # Le corps du message est conservé
        ("fix: arrondi\n\nDétail.\n", "fix/DE-7-arrondi", "fix: arrondi (DE-7)\n\nDétail.\n"),
        # Message sans saut de ligne final (git commit -m)
        ("docs: grilles", "docs/DE-33-grilles", "docs: grilles (DE-33)\n"),
        # Clé déjà présente : rien ne change
        ("feat: zones (DE-41)\n", "feat/DE-41-biodiv", "feat: zones (DE-41)\n"),
        # Branche sans clé (main) : rien ne change
        ("chore: ménage\n", "main", "chore: ménage\n"),
        # Commit rédigé dans l'éditeur : première ligne vide, rien ne change
        ("\n# Message du commit\n", "feat/DE-41-x", "\n# Message du commit\n"),
        # Fusion : rien ne change
        ("Merge branch 'feat/DE-41-x'\n", "main", "Merge branch 'feat/DE-41-x'\n"),
    ],
)
def test_ajouter_cle(message: str, branche: str, attendu: str) -> None:
    assert hook.ajouter_cle(message, branche) == attendu


def test_branche_courante_lit_le_fichier_head(tmp_path: Path) -> None:
    head = tmp_path / "HEAD"
    head.write_text("ref: refs/heads/feat/DE-41-biodiv-sports\n", encoding="utf-8")

    assert hook.branche_courante(head) == "feat/DE-41-biodiv-sports"


def test_branche_courante_vide_si_head_detache(tmp_path: Path) -> None:
    head = tmp_path / "HEAD"
    head.write_text("3171b9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6\n", encoding="utf-8")

    assert hook.branche_courante(head) == ""


def test_main_reecrit_le_fichier_du_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fichier = tmp_path / "COMMIT_EDITMSG"
    fichier.write_text("feat: zones sensibles\n", encoding="utf-8")
    monkeypatch.setattr(hook, "branche_courante", lambda: "feat/DE-41-biodiv")

    assert hook.main([str(fichier)]) == 0
    assert fichier.read_text(encoding="utf-8") == "feat: zones sensibles (DE-41)\n"
