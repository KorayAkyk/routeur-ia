"""Historique de démonstration : de vraies exécutions du service, sur le faux fournisseur.

Rien n'est inséré à la main dans le journal. On rejoue quelques jours de demandes avec une horloge
simulée, ce qui passe par le vrai routage, les vraies bascules et le vrai calcul de coût. Les
jetons, eux, sont simulés, et la page de suivi l'annonce.
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

from routeur_ia.composition import Application, assembler, maintenant_utc
from routeur_ia.config import Config
from routeur_ia.domaine import ErreurTransitoire, MessageUtilisateur
from routeur_ia.fournisseurs.faux import FauxFournisseur
from routeur_ia.service import AucunFournisseur, BudgetEpuise, Demande

TACHES = ("classification", "extraction", "general", "resume", "traduction", "code", "raisonnement")
POIDS_TACHES = (5, 3, 4, 4, 2, 2, 1)
GRAINE = 42
JOURS_AVANT_LA_FIN_DE_LA_PANNE = 5
LONGUEUR_TEXTE_TRES_LONG = 160_000


def peupler(
    config: Config,
    chemin_base: Path,
    jours: int = 30,
    maintenant: datetime | None = None,
) -> int:
    """Remplit un journal vide avec `jours` jours de demandes. Renvoie le nombre de demandes."""
    fin = maintenant or maintenant_utc()
    instant = [fin - timedelta(days=jours - 1)]
    fournisseurs = {
        nom: FauxFournisseur(nom)
        for nom in sorted({modele.fournisseur for modele in config.modeles.values()})
    }
    application = assembler(
        config,
        fournisseurs,
        chemin_base,
        horloge=lambda: instant[0],
        dormir=lambda _: None,
        horloge_sante=lambda: instant[0].timestamp(),
    )
    alea = random.Random(GRAINE)  # noqa: S311 (données de démonstration)
    total = 0
    for rang in range(jours):
        # Une journée de panne complète de Claude : Gemini doit prendre le relais.
        fournisseurs["anthropic"].simuler_panne(rang == jours - JOURS_AVANT_LA_FIN_DE_LA_PANNE)
        jour = fin - timedelta(days=jours - 1 - rang)
        heures = sorted(
            (alea.randint(7, 19), alea.randint(0, 59)) for _ in range(alea.randint(8, 20))
        )
        for heure, minute in heures:
            instant[0] = jour.replace(hour=heure, minute=minute)
            _incident_eventuel(alea, fournisseurs)
            total += _une_demande(application, alea)
    return total


def _incident_eventuel(alea: random.Random, fournisseurs: dict[str, FauxFournisseur]) -> None:
    """De temps en temps, une surcharge : le service doit reprendre, puis basculer."""
    tirage = alea.random()
    if tirage < 0.08:
        fournisseurs["anthropic"].programmer(ErreurTransitoire("http_529"))
    elif tirage < 0.11:
        erreurs = [ErreurTransitoire("http_503") for _ in range(3)]
        fournisseurs["anthropic"].programmer(*erreurs)


def _une_demande(application: Application, alea: random.Random) -> int:
    tache = alea.choices(TACHES, POIDS_TACHES)[0]
    longueur = alea.randint(80, 6_000) if tache != "classification" else alea.randint(40, 600)
    if alea.random() < 0.03:
        longueur = LONGUEUR_TEXTE_TRES_LONG
    demande = Demande(
        tache=tache,
        messages=(MessageUtilisateur("x" * longueur),),
        max_jetons=1024,
    )
    try:
        application.service.executer(demande)
    except (BudgetEpuise, AucunFournisseur):
        return 0
    return 1
