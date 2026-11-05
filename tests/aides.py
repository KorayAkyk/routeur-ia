"""Outils partagés par les tests : configuration à prix simples, horloges maîtrisées."""

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from routeur_ia.composition import Application, assembler
from routeur_ia.config import Config, lire_config
from routeur_ia.domaine import Fournisseur, MessageUtilisateur
from routeur_ia.fournisseurs.faux import FauxFournisseur
from routeur_ia.service import Demande

INSTANT = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def config_brute() -> dict[str, Any]:
    """Prix ronds et volontairement différents de la vraie configuration."""
    return {
        "budget": {
            "plafond_mensuel_usd": "10.00",
            "seuil_economie": 0.30,
            "seuil_critique": 0.10,
        },
        "tentatives": {
            "max_essais": 3,
            "attente_initiale_s": 1.0,
            "facteur": 2.0,
            "attente_max_s": 8.0,
            "gigue": 0.0,
            "delai_appel_s": 10.0,
        },
        "pannes": {"echecs_avant_panne": 3, "duree_panne_s": 60.0},
        "routage": {
            "seuil_court": 100,
            "seuil_long": 1000,
            "seuil_tres_long": 5000,
            "niveau_par_tache": {
                "classification": "eco",
                "general": "standard",
                "resume": "standard",
                "agent": "standard",
                "code": "expert",
            },
        },
        "niveaux": [
            {"nom": "eco", "modeles": ["a-eco", "g-eco"], "effort": "low"},
            {"nom": "standard", "modeles": ["a-std", "g-std"], "effort": "medium"},
            {"nom": "expert", "modeles": ["a-exp", "g-exp"], "effort": "high"},
        ],
        "modeles": [
            {
                "id": "a-eco",
                "fournisseur": "anthropic",
                "prix_entree": "1",
                "prix_sortie": "5",
                "palier_jetons": 1000,
                "prix_entree_palier": "2",
                "prix_sortie_palier": "10",
            },
            {"id": "g-eco", "fournisseur": "google", "prix_entree": "1.5", "prix_sortie": "6"},
            {"id": "a-std", "fournisseur": "anthropic", "prix_entree": "3", "prix_sortie": "15"},
            {"id": "g-std", "fournisseur": "google", "prix_entree": "2", "prix_sortie": "12"},
            {"id": "a-exp", "fournisseur": "anthropic", "prix_entree": "5", "prix_sortie": "25"},
            {"id": "g-exp", "fournisseur": "google", "prix_entree": "4", "prix_sortie": "20"},
        ],
    }


def creer_config(**surcharges: Any) -> Config:
    """Surcharge par section, par exemple `budget={"plafond_mensuel_usd": "0.01"}`."""
    brut = config_brute()
    for section, valeurs in surcharges.items():
        brut[section] = {**brut[section], **valeurs}
    return lire_config(brut)


class Horloge:
    """Horloge avancée à la main : les tests ne dorment jamais vraiment."""

    def __init__(self, depart: datetime = INSTANT) -> None:
        self.instant = depart
        self.secondes = 1000.0

    def __call__(self) -> datetime:
        return self.instant

    def monotone(self) -> float:
        return self.secondes


class Dormeur:
    """Enregistre les attentes demandées au lieu d'attendre."""

    def __init__(self) -> None:
        self.attentes: list[float] = []

    def __call__(self, duree: float) -> None:
        self.attentes.append(duree)


def faux_fournisseurs() -> dict[str, FauxFournisseur]:
    return {"anthropic": FauxFournisseur("anthropic"), "google": FauxFournisseur("google")}


def creer_application(
    chemin: Path,
    config: Config | None = None,
    fournisseurs: Mapping[str, Fournisseur] | None = None,
    horloge: Horloge | None = None,
    dormeur: Dormeur | None = None,
    jeton_api: str | None = None,
    mode: str = "faux",
) -> Application:
    horloge = horloge or Horloge()
    return assembler(
        config=config or creer_config(),
        fournisseurs=faux_fournisseurs() if fournisseurs is None else fournisseurs,
        chemin_base=chemin,
        mode=mode,
        jeton_api=jeton_api,
        horloge=horloge,
        dormir=dormeur or Dormeur(),
        horloge_sante=horloge.monotone,
    )


def demande(tache: str = "resume", texte: str = "x" * 600, max_jetons: int = 100) -> Demande:
    return Demande(tache=tache, messages=(MessageUtilisateur(texte),), max_jetons=max_jetons)
