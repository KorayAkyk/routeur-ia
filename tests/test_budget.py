"""Budget plafond : solde, réservations, changement de mois, accès concurrents."""

import threading
from datetime import UTC, date, datetime
from pathlib import Path

from routeur_ia.budget import Budget, EtatBudget
from routeur_ia.domaine import ReponseModele
from routeur_ia.service import AucunFournisseur, BudgetEpuise
from tests.aides import Horloge, creer_application, creer_config, demande, faux_fournisseurs


def budget_simple(plafond: int = 1000, depense: int = 0) -> Budget:
    return Budget(plafond, lambda _: depense, Horloge())


def test_part_restante() -> None:
    assert EtatBudget(1000, 250, 250).part_restante == 0.5


def test_le_restant_ne_descend_jamais_sous_zero() -> None:
    etat = EtatBudget(1000, 1500, 0)
    assert etat.restant_nano == 0
    assert etat.part_restante == 0.0


def test_un_plafond_nul_ne_laisse_rien() -> None:
    assert EtatBudget(0, 0, 0).part_restante == 0.0


def test_une_reservation_diminue_le_solde() -> None:
    budget = budget_simple()
    assert budget.reserver(400)
    assert budget.etat().restant_nano == 600


def test_une_reservation_trop_grande_est_refusee_sans_effet() -> None:
    budget = budget_simple()
    assert budget.reserver(600)
    assert not budget.reserver(401)
    assert budget.etat().reserve_nano == 600


def test_on_peut_reserver_exactement_le_solde() -> None:
    assert budget_simple().reserver(1000)


def test_liberer_rend_le_solde() -> None:
    budget = budget_simple()
    budget.reserver(400)
    budget.liberer(400)
    assert budget.etat().restant_nano == 1000


def test_le_mois_est_compte_depuis_le_premier() -> None:
    jours_demandes: list[date] = []

    def depense(jour: date) -> int:
        jours_demandes.append(jour)
        return 0

    Budget(1000, depense, Horloge()).etat()
    assert str(jours_demandes[0]) == "2026-03-01"


def test_le_budget_repart_a_zero_le_mois_suivant(tmp_path: Path) -> None:
    horloge = Horloge()
    application = creer_application(tmp_path / "j.sqlite", horloge=horloge)
    application.service.executer(demande())
    assert application.budget.etat().depense_nano > 0

    horloge.instant = datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert application.budget.etat().depense_nano == 0


def test_le_plafond_tient_sous_des_demandes_simultanees(tmp_path: Path) -> None:
    """Sans réservation, tous les fils verraient le même solde et le plafond serait dépassé."""
    fournisseurs = faux_fournisseurs()
    # Chaque appel coûte exactement son maximum réservé : 300 x 3 $/M + 100 x 15 $/M = 2 400 $/M.
    reponses = [ReponseModele("ok", 200, 100) for _ in range(200)]
    fournisseurs["anthropic"].programmer(*reponses)
    config = creer_config(budget={"plafond_mensuel_usd": "0.01"})
    application = creer_application(tmp_path / "j.sqlite", config, fournisseurs)

    acceptees: list[int] = []
    refusees: list[int] = []

    def travailler() -> None:
        try:
            application.service.executer(demande())
            acceptees.append(1)
        except (BudgetEpuise, AucunFournisseur):
            refusees.append(1)

    fils = [threading.Thread(target=travailler) for _ in range(40)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert refusees, "le plafond aurait dû bloquer une partie des demandes"
    assert application.budget.etat().depense_nano <= 10_000_000
    assert application.budget.etat().reserve_nano == 0
