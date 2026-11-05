"""Choix des fournisseurs selon l'environnement.

Le mode par défaut est le faux fournisseur. Une clé présente dans l'environnement ne déclenche
jamais seule des appels payants : il faut demander explicitement `ROUTEUR_MODE=reel`.
"""

from collections.abc import Mapping

from routeur_ia.config import Config
from routeur_ia.domaine import Fournisseur
from routeur_ia.fournisseurs.faux import FauxFournisseur

MODE_FAUX = "faux"
MODE_REEL = "reel"


class ModeInvalide(ValueError):
    """Le mode demandé n'existe pas, ou aucune clé n'est disponible en mode réel."""


def lire_mode(env: Mapping[str, str]) -> str:
    mode = env.get("ROUTEUR_MODE") or MODE_FAUX
    if mode not in (MODE_FAUX, MODE_REEL):
        raise ModeInvalide(f"ROUTEUR_MODE inconnu : {mode!r} (attendu : faux ou reel)")
    return mode


def creer_fournisseurs(config: Config, env: Mapping[str, str]) -> dict[str, Fournisseur]:
    if lire_mode(env) == MODE_FAUX:
        noms = sorted({modele.fournisseur for modele in config.modeles.values()})
        return {nom: FauxFournisseur(nom) for nom in noms}
    return _fournisseurs_reels(config, env)


def _fournisseurs_reels(config: Config, env: Mapping[str, str]) -> dict[str, Fournisseur]:
    # Imports locaux : le mode sans clé n'a pas besoin de charger les SDK.
    delai = config.tentatives.delai_appel_s
    fournisseurs: dict[str, Fournisseur] = {}
    cle_anthropic = env.get("ANTHROPIC_API_KEY")
    if cle_anthropic:
        from routeur_ia.fournisseurs import anthropique

        client_anthropic = anthropique.creer_client(cle_anthropic, delai)
        fournisseurs[anthropique.NOM] = anthropique.FournisseurAnthropic(client_anthropic)
    cle_gemini = env.get("GEMINI_API_KEY")
    if cle_gemini:
        from routeur_ia.fournisseurs import google

        client_google = google.creer_client(cle_gemini, delai)
        fournisseurs[google.NOM] = google.FournisseurGoogle(client_google)
    if not fournisseurs:
        raise ModeInvalide("mode réel : définir ANTHROPIC_API_KEY ou GEMINI_API_KEY")
    return fournisseurs
