"""Nouvelles tentatives avec attente croissante, sur les seules erreurs transitoires."""

from collections.abc import Callable
from dataclasses import dataclass

from routeur_ia.domaine import ErreurTransitoire


@dataclass(frozen=True)
class PolitiqueReprise:
    max_essais: int
    attente_initiale_s: float
    facteur: float
    attente_max_s: float
    gigue: float = 0.0


def calculer_attente(
    politique: PolitiqueReprise,
    numero_echec: int,
    alea: float = 0.0,
    attente_suggeree: float | None = None,
) -> float:
    """Durée avant l'essai suivant. `numero_echec` commence à 1, `alea` est dans [0, 1[.

    La gigue retire une part de l'attente pour que des clients touchés en même temps ne
    reviennent pas en même temps. Une attente demandée par le fournisseur (`retry-after`) sert de
    minimum, dans la limite du plafond.
    """
    base = politique.attente_initiale_s * politique.facteur ** (numero_echec - 1)
    plafonnee = min(base, politique.attente_max_s)
    attente = plafonnee * (1 - politique.gigue * alea)
    if attente_suggeree is not None:
        attente = max(attente, min(attente_suggeree, politique.attente_max_s))
    return attente


def executer_avec_reprises[T](
    appel: Callable[[int], T],
    politique: PolitiqueReprise,
    dormir: Callable[[float], None],
    alea: Callable[[], float],
) -> T:
    """Exécute `appel(numero_essai)`. Toute autre erreur que transitoire remonte aussitôt."""
    for essai in range(1, politique.max_essais):
        try:
            return appel(essai)
        except ErreurTransitoire as erreur:
            dormir(calculer_attente(politique, essai, alea(), erreur.attente_suggeree))
    return appel(politique.max_essais)
