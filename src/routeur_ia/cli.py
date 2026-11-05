"""Ligne de commande : `routeur-ia serve` et `routeur-ia demo`."""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from waitress import serve

from routeur_ia.composition import Application, depuis_environnement
from routeur_ia.config import CHEMIN_PAR_DEFAUT, charger_config
from routeur_ia.demo import peupler
from routeur_ia.fournisseurs.fabrique import MODE_FAUX
from routeur_ia.web import creer_app

HOTES_LOCAUX = frozenset({"127.0.0.1", "localhost", "::1"})
BASE_DEMO = Path("donnees/demo.sqlite")


class ExpositionRefusee(ValueError):
    """Écouter hors de la machine locale exige un jeton d'accès."""


def verifier_exposition(hote: str, application: Application) -> None:
    if hote not in HOTES_LOCAUX and application.jeton_api is None:
        raise ExpositionRefusee(f"écouter sur {hote} exige de définir ROUTEUR_JETON_API")


def _lancer(application: Application, hote: str, port: int) -> None:
    verifier_exposition(hote, application)
    print(f"routeur-ia, mode {application.mode} : http://{hote}:{port}/", flush=True)
    serve(creer_app(application), host=hote, port=port)


def _commande_demo(hote: str, port: int) -> None:
    """Sans clé, sans réseau : ces variables écrasent l'environnement, même si une clé y traîne."""
    env = dict(os.environ)
    env["ROUTEUR_MODE"] = MODE_FAUX
    env["ROUTEUR_BASE"] = str(BASE_DEMO)
    if not BASE_DEMO.exists():
        config = charger_config(Path(env.get("ROUTEUR_CONFIG") or CHEMIN_PAR_DEFAUT))
        nombre = peupler(config, BASE_DEMO)
        print(f"Historique de démonstration créé : {nombre} demandes simulées.")
    _lancer(depuis_environnement(env), hote, port)


def main(arguments: Sequence[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="routeur-ia", description=__doc__)
    sous_commandes = analyseur.add_subparsers(dest="commande", required=True)
    for nom, aide in (
        ("serve", "lance le service selon l'environnement"),
        ("demo", "lance le service sans clé, avec un historique simulé"),
    ):
        sous_commande = sous_commandes.add_parser(nom, help=aide)
        sous_commande.add_argument("--hote", default="127.0.0.1")
        sous_commande.add_argument("--port", type=int, default=8000)
    options = analyseur.parse_args(arguments)
    try:
        if options.commande == "demo":
            _commande_demo(options.hote, options.port)
        else:
            _lancer(depuis_environnement(), options.hote, options.port)
    except ValueError as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 2
    return 0
