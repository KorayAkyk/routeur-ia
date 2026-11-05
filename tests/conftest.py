"""Garde-fous communs : aucun test ne peut joindre un vrai fournisseur."""

import socket
from collections.abc import Iterator
from typing import Any

import pytest

_CONNECT_ORIGINAL = socket.socket.connect
_ADRESSES_LOCALES = frozenset({"127.0.0.1", "::1", "localhost"})


class ReseauInterdit(RuntimeError):
    """Un test a tenté de sortir de la machine."""


def _connect_local_seulement(self: socket.socket, adresse: Any) -> None:
    if self.family in (socket.AF_INET, socket.AF_INET6) and adresse[0] not in _ADRESSES_LOCALES:
        raise ReseauInterdit(f"connexion réseau interdite dans les tests : {adresse[0]}")
    _CONNECT_ORIGINAL(self, adresse)


@pytest.fixture(autouse=True, scope="session")
def reseau_coupe() -> Iterator[None]:
    """Toute la suite tourne avec le réseau extérieur coupé au niveau du socket."""
    socket.socket.connect = _connect_local_seulement  # type: ignore[method-assign,assignment]
    yield
    socket.socket.connect = _CONNECT_ORIGINAL  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def sans_cles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une clé présente sur le poste de développement ne doit jamais influencer un test."""
    for variable in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ROUTEUR_MODE",
        "ROUTEUR_JETON_API",
        "ROUTEUR_BASE",
        "ROUTEUR_CONFIG",
    ):
        monkeypatch.delenv(variable, raising=False)
