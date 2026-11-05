"""Calcul de coût : valeurs exactes, paliers de prix, arrondis."""

from decimal import Decimal

import pytest

from routeur_ia.config import Modele
from routeur_ia.couts import (
    cout_entree_nano,
    cout_maximal_nano,
    cout_nano,
    estimer_jetons,
    formater_usd,
    nano_en_usd,
    prix_applicables,
    usd_en_nano,
)

SIMPLE = Modele("m", "f", Decimal("2.00"), Decimal("10.00"))
AVEC_PALIER = Modele(
    "p",
    "f",
    Decimal("0.10"),
    Decimal("0.50"),
    palier_jetons=100_000,
    prix_entree_palier=Decimal("0.50"),
    prix_sortie_palier=Decimal("2.50"),
)


def test_cout_exact_en_nano_dollars() -> None:
    # 1000 x 2 $/M + 500 x 10 $/M = 0,002 $ + 0,005 $ = 0,007 $
    assert cout_nano(SIMPLE, 1000, 500) == 7_000_000


def test_cout_nul_sans_jetons() -> None:
    assert cout_nano(SIMPLE, 0, 0) == 0


def test_un_seul_jeton_au_plus_bas_prix_reste_visible() -> None:
    # 0,10 $/M : un jeton vaut 100 nano-dollars. Un flottant en micro-dollars l'aurait perdu.
    assert cout_nano(AVEC_PALIER, 1, 0) == 100


def test_le_palier_ne_s_applique_pas_au_seuil_exact() -> None:
    assert prix_applicables(AVEC_PALIER, 100_000) == (Decimal("0.10"), Decimal("0.50"))


def test_le_palier_s_applique_a_toute_la_demande_au_dela() -> None:
    assert prix_applicables(AVEC_PALIER, 100_001) == (Decimal("0.50"), Decimal("2.50"))
    # 100 001 x 0,50 $/M + 1000 x 2,50 $/M = 0,0500005 $ + 0,0025 $
    assert cout_nano(AVEC_PALIER, 100_001, 1000) == 52_500_500


def test_un_modele_sans_palier_garde_son_prix() -> None:
    assert prix_applicables(SIMPLE, 10_000_000) == (Decimal("2.00"), Decimal("10.00"))


def test_l_arrondi_du_cout_reel_se_fait_au_plus_proche() -> None:
    modele = Modele("m", "f", Decimal("0.0005"), Decimal("0"))
    assert cout_nano(modele, 1, 0) == 1  # 0,5 nano arrondi au-dessus
    assert cout_nano(Modele("m", "f", Decimal("0.0004"), Decimal("0")), 1, 0) == 0


def test_le_cout_maximal_s_arrondit_toujours_au_superieur() -> None:
    modele = Modele("m", "f", Decimal("0.0001"), Decimal("0"))
    assert cout_nano(modele, 1, 0) == 0
    assert cout_maximal_nano(modele, 1, 0) == 1


def test_le_cout_d_entree_ignore_la_sortie() -> None:
    assert cout_entree_nano(SIMPLE, 1000) == cout_nano(SIMPLE, 1000, 0)


def test_des_jetons_negatifs_sont_une_erreur() -> None:
    with pytest.raises(ValueError, match="négatif"):
        cout_nano(SIMPLE, -1, 0)


def test_additionner_beaucoup_de_petits_appels_reste_exact() -> None:
    """Avec des flottants, cette somme dériverait."""
    total = sum(cout_nano(AVEC_PALIER, 7, 3) for _ in range(1_000_000))
    assert nano_en_usd(total) == Decimal("2.2")


def test_conversions_usd() -> None:
    assert usd_en_nano(Decimal("5.00")) == 5_000_000_000
    assert formater_usd(1_234_567) == "0.001235"


@pytest.mark.parametrize(("texte", "jetons"), [("", 0), ("a", 1), ("abc", 1), ("abcd", 2)])
def test_estimation_des_jetons(texte: str, jetons: int) -> None:
    assert estimer_jetons(texte) == jetons
