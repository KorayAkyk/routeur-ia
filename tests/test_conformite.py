"""Règles du dépôt vérifiées à chaque exécution, plutôt que promises dans le README."""

import re
import socket
import tomllib
from pathlib import Path

import pytest

from tests.conftest import ReseauInterdit

RACINE = Path(__file__).resolve().parents[1]
ECARTES = {".venv", ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
ECARTES |= {"donnees", "test-results", "htmlcov", "dist"}
SUFFIXES = {".py", ".md", ".toml", ".yml", ".html", ".css", ".js", ".example"}
LONGUEUR_MAX = 260
EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\ufe0f]")
CLE_API = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,}")


def fichiers_du_depot() -> list[Path]:
    return sorted(
        chemin
        for chemin in RACINE.rglob("*")
        if chemin.is_file()
        and chemin.suffix in SUFFIXES
        and not ECARTES & set(chemin.relative_to(RACINE).parts)
    )


def test_le_garde_fou_reseau_fonctionne() -> None:
    connexion = socket.socket()
    with pytest.raises(ReseauInterdit):
        connexion.connect(("203.0.113.1", 443))
    connexion.close()


def test_les_fichiers_restent_courts() -> None:
    trop_longs = [
        f"{chemin.relative_to(RACINE)} ({nombre} lignes)"
        for chemin in fichiers_du_depot()
        if (nombre := len(chemin.read_text(encoding="utf-8").splitlines())) > LONGUEUR_MAX
    ]
    assert trop_longs == []


def test_aucun_emoji() -> None:
    fautifs = [
        str(chemin.relative_to(RACINE))
        for chemin in fichiers_du_depot()
        if EMOJI.search(chemin.read_text(encoding="utf-8"))
    ]
    assert fautifs == []


def test_aucune_cle_d_api_dans_le_depot() -> None:
    fautifs = [
        str(chemin.relative_to(RACINE))
        for chemin in fichiers_du_depot()
        if CLE_API.search(chemin.read_text(encoding="utf-8"))
    ]
    assert fautifs == []


def test_les_dependances_sont_epinglees() -> None:
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    dependances = [
        *projet["project"]["dependencies"],
        *projet["project"]["optional-dependencies"]["dev"],
        *projet["build-system"]["requires"],
    ]
    assert dependances
    assert [d for d in dependances if not re.fullmatch(r"[a-z0-9-]+==[\w.]+", d)] == []


def test_env_example_ne_contient_aucune_valeur() -> None:
    lignes = (RACINE / ".env.example").read_text(encoding="utf-8").splitlines()
    variables = [ligne for ligne in lignes if ligne and not ligne.startswith("#")]
    assert variables
    assert [ligne for ligne in variables if not ligne.endswith("=")] == []


def test_les_modeles_claude_par_defaut() -> None:
    config = (RACINE / "config" / "routeur.toml").read_text(encoding="utf-8")
    for modele in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
        assert f'id = "{modele}"' in config


def test_les_actions_de_la_ci_sont_epinglees_par_empreinte() -> None:
    flux = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    actions = re.findall(r"uses:\s*(\S+)", flux)
    assert actions
    assert [a for a in actions if not re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", a)] == []
