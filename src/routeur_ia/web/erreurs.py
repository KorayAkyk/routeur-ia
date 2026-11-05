"""Traduction des erreurs en réponses JSON. Rien d'interne ni de saisi n'est renvoyé."""

from flask import Flask, Response, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from routeur_ia.domaine import ErreurRequete
from routeur_ia.routage import TacheInconnue
from routeur_ia.service import AucunFournisseur, BudgetEpuise


def _json(statut: int, **contenu: object) -> tuple[Response, int]:
    return jsonify(contenu), statut


def installer_erreurs(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def corps_invalide(erreur: ValidationError) -> tuple[Response, int]:
        details = erreur.errors(include_url=False, include_input=False, include_context=False)
        return _json(400, erreur="corps_invalide", details=details)

    @app.errorhandler(TacheInconnue)
    def tache_inconnue(erreur: TacheInconnue) -> tuple[Response, int]:
        return _json(400, erreur="tache_inconnue", tache=str(erreur))

    @app.errorhandler(BudgetEpuise)
    def budget_epuise(_: BudgetEpuise) -> tuple[Response, int]:
        return _json(402, erreur="budget_epuise")

    @app.errorhandler(ErreurRequete)
    def requete_refusee(erreur: ErreurRequete) -> tuple[Response, int]:
        return _json(422, erreur="requete_refusee_par_le_fournisseur", code=erreur.code)

    @app.errorhandler(AucunFournisseur)
    def aucun_fournisseur(erreur: AucunFournisseur) -> tuple[Response, int]:
        essais = [
            {"modele": e.modele, "essai": e.numero, "code": e.code_erreur} for e in erreur.essais
        ]
        return _json(503, erreur="aucun_fournisseur", essais=essais)

    @app.errorhandler(HTTPException)
    def erreur_http(erreur: HTTPException) -> tuple[Response, int]:
        statut = erreur.code or 500
        return _json(statut, erreur=(erreur.name or "erreur").lower().replace(" ", "_"))
