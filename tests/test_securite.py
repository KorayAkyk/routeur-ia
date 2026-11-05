"""Jeton d'accès et en-têtes de sécurité."""

import base64
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from routeur_ia.composition import Application
from routeur_ia.web import creer_app
from tests.aides import creer_application

JETON = "jeton-de-test"


@pytest.fixture
def protege(tmp_path: Path) -> FlaskClient:
    return creer_app(creer_application(tmp_path / "j.sqlite", jeton_api=JETON)).test_client()


@pytest.fixture
def application_ouverte(tmp_path: Path) -> Application:
    return creer_application(tmp_path / "j.sqlite")


def basic(mot_de_passe: str) -> dict[str, str]:
    valeur = base64.b64encode(f"moi:{mot_de_passe}".encode()).decode()
    return {"Authorization": f"Basic {valeur}"}


@pytest.mark.parametrize("chemin", ["/", "/v1/budget", "/v1/couts"])
def test_sans_jeton_tout_est_refuse(protege: FlaskClient, chemin: str) -> None:
    reponse = protege.get(chemin)
    assert reponse.status_code == 401
    assert reponse.headers["WWW-Authenticate"].startswith("Basic")


def test_la_sante_reste_publique(protege: FlaskClient) -> None:
    assert protege.get("/sante").status_code == 200


def test_jeton_bearer(protege: FlaskClient) -> None:
    entetes = {"Authorization": f"Bearer {JETON}"}
    assert protege.get("/v1/budget", headers=entetes).status_code == 200


def test_mauvais_jeton_bearer(protege: FlaskClient) -> None:
    entetes = {"Authorization": "Bearer mauvais"}
    assert protege.get("/v1/budget", headers=entetes).status_code == 401


def test_basic_pour_le_navigateur(protege: FlaskClient) -> None:
    assert protege.get("/", headers=basic(JETON)).status_code == 200
    assert protege.get("/", headers=basic("mauvais")).status_code == 401


def test_autorisation_sans_valeur(protege: FlaskClient) -> None:
    assert protege.get("/", headers={"Authorization": "Bearer "}).status_code == 401
    assert protege.get("/", headers={"Authorization": "Digest x=y"}).status_code == 401


def test_jeton_non_ascii_ne_fait_pas_planter(protege: FlaskClient) -> None:
    assert protege.get("/", headers=basic("é" * 8)).status_code == 401


def test_en_tetes_de_securite(application_ouverte: Application) -> None:
    reponse = creer_app(application_ouverte).test_client().get("/")
    politique = reponse.headers["Content-Security-Policy"]
    assert "default-src 'none'" in politique
    assert "unsafe-inline" not in politique
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["Referrer-Policy"] == "no-referrer"
