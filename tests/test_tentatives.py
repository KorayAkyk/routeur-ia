"""Nouvelles tentatives et attente croissante."""

import pytest

from routeur_ia.domaine import ErreurIndisponible, ErreurRequete, ErreurTransitoire
from routeur_ia.tentatives import PolitiqueReprise, calculer_attente, executer_avec_reprises
from tests.aides import Dormeur

POLITIQUE = PolitiqueReprise(max_essais=3, attente_initiale_s=1.0, facteur=2.0, attente_max_s=8.0)


@pytest.mark.parametrize(
    ("echec", "attente"), [(1, 1.0), (2, 2.0), (3, 4.0), (4, 8.0), (5, 8.0), (20, 8.0)]
)
def test_l_attente_croit_puis_plafonne(echec: int, attente: float) -> None:
    assert calculer_attente(POLITIQUE, echec) == attente


def test_la_gigue_retire_une_part_de_l_attente() -> None:
    politique = PolitiqueReprise(3, 1.0, 2.0, 8.0, gigue=0.5)
    assert calculer_attente(politique, 2, alea=0.0) == 2.0
    assert calculer_attente(politique, 2, alea=0.5) == 1.5


def test_l_attente_demandee_par_le_fournisseur_sert_de_minimum() -> None:
    assert calculer_attente(POLITIQUE, 1, attente_suggeree=5.0) == 5.0
    assert calculer_attente(POLITIQUE, 3, attente_suggeree=1.0) == 4.0


def test_l_attente_demandee_ne_depasse_pas_le_plafond() -> None:
    assert calculer_attente(POLITIQUE, 1, attente_suggeree=3600.0) == 8.0


def appel_scripte(*suite: object) -> tuple[object, list[int]]:
    essais: list[int] = []
    reste = list(suite)

    def appel(numero: int) -> object:
        essais.append(numero)
        prochain = reste.pop(0)
        if isinstance(prochain, Exception):
            raise prochain
        return prochain

    return appel, essais


def test_reussite_du_premier_coup_sans_attente() -> None:
    appel, essais = appel_scripte("ok")
    dormeur = Dormeur()
    assert executer_avec_reprises(appel, POLITIQUE, dormeur, lambda: 0.0) == "ok"  # type: ignore[arg-type]
    assert essais == [1]
    assert dormeur.attentes == []


def test_une_erreur_transitoire_est_reessayee_avec_attente_croissante() -> None:
    appel, essais = appel_scripte(ErreurTransitoire("a"), ErreurTransitoire("b"), "ok")
    dormeur = Dormeur()
    assert executer_avec_reprises(appel, POLITIQUE, dormeur, lambda: 0.0) == "ok"  # type: ignore[arg-type]
    assert essais == [1, 2, 3]
    assert dormeur.attentes == [1.0, 2.0]


def test_apres_le_dernier_essai_l_erreur_remonte_sans_attente_inutile() -> None:
    appel, essais = appel_scripte(*(ErreurTransitoire(str(i)) for i in range(3)))
    dormeur = Dormeur()
    with pytest.raises(ErreurTransitoire, match="2"):
        executer_avec_reprises(appel, POLITIQUE, dormeur, lambda: 0.0)  # type: ignore[arg-type]
    assert essais == [1, 2, 3]
    assert len(dormeur.attentes) == 2


@pytest.mark.parametrize("erreur", [ErreurIndisponible("x"), ErreurRequete("x")])
def test_une_erreur_definitive_n_est_pas_reessayee(erreur: Exception) -> None:
    appel, essais = appel_scripte(erreur, "jamais")
    dormeur = Dormeur()
    with pytest.raises(type(erreur)):
        executer_avec_reprises(appel, POLITIQUE, dormeur, lambda: 0.0)  # type: ignore[arg-type]
    assert essais == [1]
    assert dormeur.attentes == []


def test_un_seul_essai_autorise() -> None:
    appel, essais = appel_scripte(ErreurTransitoire("x"))
    politique = PolitiqueReprise(1, 1.0, 2.0, 8.0)
    with pytest.raises(ErreurTransitoire):
        executer_avec_reprises(appel, politique, Dormeur(), lambda: 0.0)  # type: ignore[arg-type]
    assert essais == [1]
