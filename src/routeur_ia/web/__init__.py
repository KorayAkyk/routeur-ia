"""Application Flask : API JSON, page de suivi, en-têtes de sécurité."""

from flask import Flask

from routeur_ia.composition import Application
from routeur_ia.web.api import api
from routeur_ia.web.erreurs import installer_erreurs
from routeur_ia.web.presentation import entier, usd_court
from routeur_ia.web.securite import installer_securite
from routeur_ia.web.suivi import suivi

TAILLE_MAX_CORPS = 1024 * 1024
CLE_EXTENSION = "routeur_ia"


def creer_app(application: Application) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = TAILLE_MAX_CORPS
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions[CLE_EXTENSION] = application
    app.add_template_filter(usd_court, "usd")
    app.add_template_filter(entier, "entier")
    installer_securite(app, application.jeton_api)
    installer_erreurs(app)
    app.register_blueprint(api)
    app.register_blueprint(suivi)
    return app
