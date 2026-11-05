"""Règles de routage : chacune isolée, puis leur enchaînement."""

import pytest

from routeur_ia.routage import EntreeRoutage, EtatRoutage, TacheInconnue, decider
from tests.aides import creer_config

CONFIG = creer_config()
SAIN = EtatRoutage(part_budget_restante=1.0)


def ids(decision_candidats: tuple[object, ...]) -> list[str]:
    return [modele.id for modele in decision_candidats]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("tache", "niveau", "premier"),
    [
        ("classification", "eco", "a-eco"),
        ("resume", "standard", "a-std"),
        ("code", "expert", "a-exp"),
    ],
)
def test_le_type_de_tache_donne_le_niveau(tache: str, niveau: str, premier: str) -> None:
    decision = decider(EntreeRoutage(tache, 500), SAIN, CONFIG)
    assert decision.niveau == niveau
    assert decision.candidats[0].id == premier


def test_une_tache_inconnue_est_refusee() -> None:
    with pytest.raises(TacheInconnue):
        decider(EntreeRoutage("astrologie", 10), SAIN, CONFIG)


def test_une_demande_generale_courte_va_au_niveau_le_moins_cher() -> None:
    assert decider(EntreeRoutage("general", 99), SAIN, CONFIG).niveau == "eco"


def test_le_seuil_court_est_exclusif() -> None:
    assert decider(EntreeRoutage("general", 100), SAIN, CONFIG).niveau == "standard"


def test_une_tache_precise_courte_garde_son_niveau() -> None:
    assert decider(EntreeRoutage("code", 5), SAIN, CONFIG).niveau == "expert"


def test_un_texte_long_ne_reste_pas_au_niveau_le_plus_bas() -> None:
    assert decider(EntreeRoutage("classification", 1000), SAIN, CONFIG).niveau == "standard"
    assert decider(EntreeRoutage("classification", 999), SAIN, CONFIG).niveau == "eco"


@pytest.mark.parametrize(
    ("part", "niveau"),
    [
        (1.0, "expert"),
        (0.30, "expert"),  # le seuil lui-même ne déclenche rien
        (0.29, "standard"),
        (0.10, "standard"),
        (0.09, "eco"),
        (0.0, "eco"),
    ],
)
def test_le_budget_restant_fait_descendre_le_niveau(part: float, niveau: str) -> None:
    etat = EtatRoutage(part_budget_restante=part)
    assert decider(EntreeRoutage("code", 500), etat, CONFIG).niveau == niveau


def test_le_budget_ne_fait_pas_descendre_sous_le_plus_bas_niveau() -> None:
    etat = EtatRoutage(part_budget_restante=0.2)
    assert decider(EntreeRoutage("classification", 50), etat, CONFIG).niveau == "eco"


def test_le_budget_l_emporte_sur_la_longueur() -> None:
    etat = EtatRoutage(part_budget_restante=0.05)
    assert decider(EntreeRoutage("classification", 2000), etat, CONFIG).niveau == "eco"


def test_ordre_de_configuration_hors_texte_tres_long() -> None:
    decision = decider(EntreeRoutage("resume", 4999), SAIN, CONFIG)
    assert ids(decision.candidats) == ["a-std", "g-std"]


def test_texte_tres_long_le_moins_cher_en_entree_d_abord() -> None:
    decision = decider(EntreeRoutage("resume", 5000), SAIN, CONFIG)
    assert ids(decision.candidats) == ["g-std", "a-std"]


def test_le_palier_de_prix_compte_dans_le_tri() -> None:
    """a-eco coûte 1 sous son palier, mais 2 au-delà : g-eco (1,5) devient moins cher."""
    etat = EtatRoutage(part_budget_restante=0.05)
    decision = decider(EntreeRoutage("classification", 6000), etat, CONFIG)
    assert ids(decision.candidats) == ["g-eco", "a-eco"]


def test_un_fournisseur_en_panne_est_ecarte() -> None:
    etat = EtatRoutage(1.0, frozenset({"anthropic"}))
    decision = decider(EntreeRoutage("resume", 500), etat, CONFIG)
    assert ids(decision.candidats) == ["g-std"]
    assert "anthropic" in decision.etapes[-1].effet


def test_tous_les_fournisseurs_en_panne_ne_laisse_aucun_candidat() -> None:
    etat = EtatRoutage(1.0, frozenset({"anthropic", "google"}))
    assert decider(EntreeRoutage("resume", 500), etat, CONFIG).candidats == ()


def test_la_trace_explique_chaque_regle_dans_l_ordre() -> None:
    decision = decider(EntreeRoutage("code", 500), EtatRoutage(0.2), CONFIG)
    assert [etape.regle for etape in decision.etapes] == [
        "tache",
        "longueur",
        "budget",
        "candidats",
        "pannes",
    ]
    assert "niveau standard" in decision.etapes[2].effet
    assert "20 %" in decision.etapes[2].effet.replace("%", " %").replace("  ", " ")


def test_la_decision_est_deterministe() -> None:
    entree = EntreeRoutage("resume", 500)
    assert decider(entree, SAIN, CONFIG) == decider(entree, SAIN, CONFIG)
