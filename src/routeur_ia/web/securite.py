"""Jeton d'accès facultatif et en-têtes de sécurité.

Sans jeton configuré, le service n'écoute que sur la machine locale (voir `cli.py`). Avec un jeton,
tout est protégé sauf `/sante`. Le navigateur peut s'identifier en Basic (mot de passe = jeton), ce
qui protège aussi la page de suivi sans écran de connexion à écrire.
"""

import hmac

from flask import Flask, Response, jsonify, request

CHEMINS_PUBLICS = frozenset({"/sante"})

_POLITIQUE_CONTENU = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def installer_securite(app: Flask, jeton: str | None) -> None:
    @app.before_request
    def verifier_jeton() -> Response | None:
        if jeton is None or request.path in CHEMINS_PUBLICS or _presente(jeton):
            return None
        reponse = jsonify(erreur="non_autorise")
        reponse.status_code = 401
        reponse.headers["WWW-Authenticate"] = 'Basic realm="routeur-ia"'
        return reponse

    @app.after_request
    def ajouter_entetes(reponse: Response) -> Response:
        reponse.headers["Content-Security-Policy"] = _POLITIQUE_CONTENU
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        return reponse


def _presente(jeton: str) -> bool:
    autorisation = request.authorization
    if autorisation is None:
        return False
    if autorisation.type == "bearer" and autorisation.token:
        return _egaux(autorisation.token, jeton)
    if autorisation.type == "basic" and autorisation.password:
        return _egaux(autorisation.password, jeton)
    return False


def _egaux(recu: str, attendu: str) -> bool:
    """Comparaison en temps constant, pour ne rien révéler du jeton par le temps de réponse."""
    return hmac.compare_digest(recu.encode(), attendu.encode())
