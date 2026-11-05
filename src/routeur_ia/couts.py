"""Calcul de coût en nano-dollars entiers.

Les prix descendent à quelques centimes par million de jetons. Stocker des entiers (1 dollar =
10^9 nano-dollars) évite les erreurs d'arrondi des flottants quand on additionne des milliers de
lignes en SQL. Les calculs passent par `Decimal`.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from math import ceil

from routeur_ia.config import Modele

NANO_PAR_USD = 1_000_000_000
JETONS_PAR_PRIX = 1_000_000
CARACTERES_PAR_JETON = 3


def estimer_jetons(texte: str) -> int:
    """Estimation prudente, sans appel réseau, utilisée avant de connaître le vrai décompte.

    Environ 3 caractères par jeton : volontairement au-dessus de la réalité habituelle en français
    ou en anglais, car cette estimation sert aussi à réserver du budget.
    """
    return ceil(len(texte) / CARACTERES_PAR_JETON)


def prix_applicables(modele: Modele, jetons_entree: int) -> tuple[Decimal, Decimal]:
    """Prix d'entrée et de sortie, selon le palier éventuel : il s'applique à toute la demande."""
    if (
        modele.palier_jetons is not None
        and modele.prix_entree_palier is not None
        and modele.prix_sortie_palier is not None
        and jetons_entree > modele.palier_jetons
    ):
        return modele.prix_entree_palier, modele.prix_sortie_palier
    return modele.prix_entree, modele.prix_sortie


def cout_nano(modele: Modele, jetons_entree: int, jetons_sortie: int) -> int:
    """Coût réel d'un appel."""
    return _en_nano(_cout_usd(modele, jetons_entree, jetons_sortie), ROUND_HALF_UP)


def cout_maximal_nano(modele: Modele, jetons_entree_estimes: int, max_jetons_sortie: int) -> int:
    """Plafond de coût d'un appel, arrondi au supérieur, pour réserver le budget."""
    brut = _cout_usd(modele, jetons_entree_estimes, max_jetons_sortie)
    return _en_nano(brut, ROUND_CEILING)


def cout_entree_nano(modele: Modele, jetons_entree: int) -> int:
    """Coût de la seule entrée, pour comparer les modèles sur un texte très long."""
    return _en_nano(_cout_usd(modele, jetons_entree, 0), ROUND_HALF_UP)


def nano_en_usd(montant: int) -> Decimal:
    return Decimal(montant) / NANO_PAR_USD


def usd_en_nano(montant: Decimal) -> int:
    return _en_nano(montant, ROUND_HALF_UP)


def formater_usd(montant_nano: int) -> str:
    """Montant lisible : six décimales suffisent pour voir un appel à bas prix."""
    return f"{nano_en_usd(montant_nano):.6f}"


def _cout_usd(modele: Modele, jetons_entree: int, jetons_sortie: int) -> Decimal:
    if jetons_entree < 0 or jetons_sortie < 0:
        raise ValueError("un nombre de jetons ne peut pas être négatif")
    prix_entree, prix_sortie = prix_applicables(modele, jetons_entree)
    return (jetons_entree * prix_entree + jetons_sortie * prix_sortie) / JETONS_PAR_PRIX


def _en_nano(montant_usd: Decimal, arrondi: str) -> int:
    return int((montant_usd * NANO_PAR_USD).to_integral_value(rounding=arrondi))
