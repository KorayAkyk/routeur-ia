"""Disjoncteur par fournisseur."""

from routeur_ia.config import ConfigPannes
from routeur_ia.sante import SanteFournisseurs


class Temps:
    def __init__(self) -> None:
        self.valeur = 0.0

    def __call__(self) -> float:
        return self.valeur


def creer() -> tuple[SanteFournisseurs, Temps]:
    temps = Temps()
    return SanteFournisseurs(ConfigPannes(echecs_avant_panne=3, duree_panne_s=60.0), temps), temps


def test_un_fournisseur_inconnu_est_disponible() -> None:
    sante, _ = creer()
    assert sante.est_disponible("a")


def test_disponible_tant_que_le_seuil_n_est_pas_atteint() -> None:
    sante, _ = creer()
    sante.signaler_echec("a")
    sante.signaler_echec("a")
    assert sante.est_disponible("a")


def test_en_panne_au_seuil() -> None:
    sante, _ = creer()
    for _ in range(3):
        sante.signaler_echec("a")
    assert not sante.est_disponible("a")
    assert sante.indisponibles(frozenset({"a", "b"})) == frozenset({"a"})


def test_un_succes_remet_le_compteur_a_zero() -> None:
    sante, _ = creer()
    sante.signaler_echec("a")
    sante.signaler_echec("a")
    sante.signaler_succes("a")
    sante.signaler_echec("a")
    sante.signaler_echec("a")
    assert sante.est_disponible("a")


def test_la_panne_expire() -> None:
    sante, temps = creer()
    for _ in range(3):
        sante.signaler_echec("a")
    temps.valeur = 59.9
    assert not sante.est_disponible("a")
    temps.valeur = 60.0
    assert sante.est_disponible("a")


def test_apres_expiration_un_seul_echec_suffit_a_ecarter_de_nouveau() -> None:
    sante, temps = creer()
    for _ in range(3):
        sante.signaler_echec("a")
    temps.valeur = 60.0
    sante.signaler_echec("a")
    assert not sante.est_disponible("a")
    temps.valeur = 119.9
    assert not sante.est_disponible("a")


def test_un_fournisseur_ne_penalise_pas_l_autre() -> None:
    sante, _ = creer()
    for _ in range(3):
        sante.signaler_echec("a")
    assert sante.est_disponible("b")


def test_reinitialiser() -> None:
    sante, _ = creer()
    for _ in range(3):
        sante.signaler_echec("a")
    sante.reinitialiser("a")
    assert sante.est_disponible("a")
