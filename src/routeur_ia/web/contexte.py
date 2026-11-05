"""Accès à l'application courante depuis les routes."""

from typing import cast

from flask import current_app

from routeur_ia.composition import Application


def application_courante() -> Application:
    return cast(Application, current_app.extensions["routeur_ia"])
