"""Page de suivi rendue côté serveur, et calculs de présentation."""

from datetime import date
from pathlib import Path

import pytest

from routeur_ia.journal import CoutJourModele
from routeur_ia.web import creer_app
from routeur_ia.web.presentation import (
    construire_graphique,
    echelle_ronde,
    entier,
    totaux_par_modele,
    usd_axe,
    usd_court,
)
from tests.aides import creer_application, demande, faux_fournisseurs

SERIES = {"a": 0, "b": 1}


def ligne(jour: int, modele: str = "a", cout: int = 1_000_000) -> CoutJourModele:
    return CoutJourModele(date(2026, 3, jour), modele, 2, 1, 10, 5, cout)


@pytest.mark.parametrize(
    ("nano", "texte"),
    [
        (0, "0 $"),
        (5, "0,000000 $"),
        (4_200_000, "0,0042 $"),
        (1_250_000_000, "1,25 $"),
    ],
)
def test_format_des_montants(nano: int, texte: str) -> None:
    assert usd_court(nano) == texte


@pytest.mark.parametrize(
    ("nano", "texte"), [(0, "0 $"), (250_000_000, "0,25 $"), (2_000_000_000, "2 $")]
)
def test_format_des_graduations(nano: int, texte: str) -> None:
    assert usd_axe(nano) == texte


def test_format_des_entiers() -> None:
    assert entier(180142) == "180\u202f142"
    assert entier(12) == "12"


@pytest.mark.parametrize(
    ("maximum", "echelle"),
    [(0, 1), (1, 1), (2, 2), (3, 4), (5, 8), (9, 10), (120, 200), (4_999, 8_000)],
)
def test_echelle_ronde(maximum: int, echelle: int) -> None:
    assert echelle_ronde(maximum) == echelle


def test_les_jours_sans_appel_gardent_leur_colonne() -> None:
    graphique = construire_graphique([ligne(3)], date(2026, 3, 1), date(2026, 3, 7), SERIES)
    assert len(graphique.colonnes) == 7
    assert [len(colonne.segments) for colonne in graphique.colonnes] == [0, 0, 1, 0, 0, 0, 0]


def test_la_couleur_suit_le_modele_et_non_le_rang() -> None:
    lignes = [ligne(1, "b"), ligne(2, "a"), ligne(2, "b")]
    graphique = construire_graphique(lignes, date(2026, 3, 1), date(2026, 3, 2), SERIES)
    assert graphique.colonnes[0].segments[0].serie == 1
    assert [s.serie for s in graphique.colonnes[1].segments] == [0, 1]


def test_un_cout_nul_ne_dessine_rien() -> None:
    graphique = construire_graphique([ligne(1, cout=0)], date(2026, 3, 1), date(2026, 3, 1), SERIES)
    assert graphique.colonnes[0].segments == ()


def test_les_barres_restent_dans_le_cadre() -> None:
    graphique = construire_graphique(
        [ligne(1, "a", 900), ligne(1, "b", 100)], date(2026, 3, 1), date(2026, 3, 1), SERIES
    )
    plafond = graphique.graduations[-1].y
    for segment in graphique.colonnes[0].segments:
        ordonnee_haute = float(segment.chemin.split("Q")[1].split()[1])
        assert ordonnee_haute >= plafond


def test_totaux_par_modele_du_plus_cher_au_moins_cher() -> None:
    totaux = totaux_par_modele([ligne(1, "a", 5), ligne(2, "a", 5), ligne(1, "b", 50)], SERIES)
    assert [(t.modele, t.cout_nano, t.appels) for t in totaux] == [("b", 50, 2), ("a", 10, 4)]


def test_page_vide(tmp_path: Path) -> None:
    client = creer_app(creer_application(tmp_path / "j.sqlite")).test_client()
    page = client.get("/").get_data(as_text=True)
    assert "Aucun appel sur cette période." in page
    assert "Mode démonstration" in page


def test_page_avec_des_appels(tmp_path: Path) -> None:
    application = creer_application(tmp_path / "j.sqlite")
    application.service.executer(demande())
    page = creer_app(application).test_client().get("/").get_data(as_text=True)
    assert "Aucun appel" not in page
    assert "a-std" in page
    assert 'class="serie-2"' in page  # a-std est le troisième modèle de la configuration


def test_periode_invalide_revient_a_la_valeur_par_defaut(tmp_path: Path) -> None:
    client = creer_app(creer_application(tmp_path / "j.sqlite")).test_client()
    page = client.get("/?jours=12345").get_data(as_text=True)
    assert "Coût sur 30 jours" in page
    assert "Coût sur 7 jours" in client.get("/?jours=7").get_data(as_text=True)


def test_en_mode_reel_ni_bandeau_ni_commandes_de_demonstration(tmp_path: Path) -> None:
    application = creer_application(
        tmp_path / "j.sqlite", fournisseurs=faux_fournisseurs(), mode="reel"
    )
    page = creer_app(application).test_client().get("/").get_data(as_text=True)
    assert "Mode démonstration" not in page
    assert "essai.js" not in page
    assert "Simuler une panne" not in page


def test_aucun_script_ni_style_en_ligne(tmp_path: Path) -> None:
    """La politique de sécurité les bloquerait : la page ne doit pas en dépendre."""
    client = creer_app(creer_application(tmp_path / "j.sqlite")).test_client()
    page = client.get("/").get_data(as_text=True)
    assert "style=" not in page
    assert "<script>" not in page
    assert "onclick" not in page


def test_les_fichiers_statiques_sont_servis(tmp_path: Path) -> None:
    client = creer_app(creer_application(tmp_path / "j.sqlite")).test_client()
    assert client.get("/static/suivi.css").status_code == 200
    assert client.get("/static/essai.js").status_code == 200
