"""API JSON du routeur."""

from datetime import timedelta
from typing import Any

from flask import Blueprint, Response, abort, jsonify, request

from routeur_ia.couts import estimer_jetons, formater_usd
from routeur_ia.domaine import MessageUtilisateur
from routeur_ia.fournisseurs.faux import FauxFournisseur
from routeur_ia.routage import Decision
from routeur_ia.service import Demande
from routeur_ia.web.contexte import application_courante
from routeur_ia.web.schemas import CorpsAgent, CorpsDemande, CorpsPanne, CorpsSimulation

api = Blueprint("api", __name__)

JOURS_MAX = 366


def _decision_json(decision: Decision) -> dict[str, Any]:
    return {
        "niveau": decision.niveau,
        "candidats": [modele.id for modele in decision.candidats],
        "etapes": [{"regle": e.regle, "effet": e.effet} for e in decision.etapes],
    }


@api.get("/sante")
def sante() -> Response:
    return jsonify(statut="ok", mode=application_courante().mode)


@api.post("/v1/demandes")
def creer_demande() -> Response:
    corps = CorpsDemande.model_validate(request.get_json())
    resultat = application_courante().service.executer(
        Demande(
            tache=corps.tache,
            messages=(MessageUtilisateur(corps.message),),
            max_jetons=corps.max_jetons,
            systeme=corps.systeme,
        )
    )
    reponse = resultat.reponse
    return jsonify(
        id=resultat.id_demande,
        texte=reponse.texte,
        arret=reponse.arret,
        modele=resultat.modele.id,
        fournisseur=resultat.modele.fournisseur,
        bascule=resultat.bascule,
        jetons={"entree": reponse.jetons_entree, "sortie": reponse.jetons_sortie},
        cout_usd=formater_usd(resultat.cout_nano),
        decision=_decision_json(resultat.decision),
        essais=[
            {"modele": e.modele, "essai": e.numero, "statut": e.statut, "code": e.code_erreur}
            for e in resultat.essais
        ],
    )


@api.post("/v1/routage/simuler")
def simuler() -> Response:
    """Montre la décision de routage sans appeler de modèle et sans rien dépenser."""
    corps = CorpsSimulation.model_validate(request.get_json())
    decision = application_courante().service.decider(corps.tache, estimer_jetons(corps.message))
    return jsonify(_decision_json(decision))


@api.post("/v1/agent")
def lancer_agent() -> Response:
    corps = CorpsAgent.model_validate(request.get_json())
    resultat = application_courante().agent.executer(corps.objectif)
    return jsonify(
        texte=resultat.texte,
        arret=resultat.arret,
        cout_usd=formater_usd(resultat.cout_nano),
        etapes=[
            {
                "modele": etape.modele,
                "appels": [{"outil": a.nom, "arguments": a.arguments} for a in etape.appels],
                "resultats": [
                    {"outil": r.nom, "contenu": r.contenu, "erreur": r.est_erreur}
                    for r in etape.resultats
                ],
            }
            for etape in resultat.etapes
        ],
    )


@api.get("/v1/couts")
def couts() -> Response:
    application = application_courante()
    jours = request.args.get("jours", default=30, type=int)
    if not 1 <= jours <= JOURS_MAX:
        abort(400)
    depuis = application.horloge().date() - timedelta(days=jours - 1)
    return jsonify(
        depuis=depuis.isoformat(),
        lignes=[
            {
                "jour": ligne.jour.isoformat(),
                "modele": ligne.modele,
                "appels": ligne.appels,
                "echecs": ligne.echecs,
                "jetons_entree": ligne.jetons_entree,
                "jetons_sortie": ligne.jetons_sortie,
                "cout_usd": formater_usd(ligne.cout_nano),
            }
            for ligne in application.journal.couts_par_jour_et_modele(depuis)
        ],
    )


@api.get("/v1/budget")
def budget() -> Response:
    etat = application_courante().budget.etat()
    return jsonify(
        plafond_usd=formater_usd(etat.plafond_nano),
        depense_usd=formater_usd(etat.depense_nano),
        restant_usd=formater_usd(etat.restant_nano),
        part_restante=round(etat.part_restante, 4),
    )


@api.post("/demo/panne")
def simuler_panne() -> Response:
    """Provoque ou arrête une panne du faux fournisseur. Cette route n'existe qu'en mode faux."""
    application = application_courante()
    if not application.mode_faux:
        abort(404)
    corps = CorpsPanne.model_validate(request.get_json())
    fournisseur = application.fournisseurs.get(corps.fournisseur)
    if not isinstance(fournisseur, FauxFournisseur):
        abort(404)
    fournisseur.simuler_panne(corps.active)
    if not corps.active:
        application.sante.reinitialiser(corps.fournisseur)
    return jsonify(fournisseur=corps.fournisseur, en_panne=corps.active)
