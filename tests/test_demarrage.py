"""Configuration, choix des fournisseurs, ligne de commande, historique de démonstration."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from routeur_ia import cli
from routeur_ia.composition import depuis_environnement
from routeur_ia.config import CHEMIN_PAR_DEFAUT, ConfigInvalide, charger_config, lire_config
from routeur_ia.demo import peupler
from routeur_ia.fournisseurs.anthropique import FournisseurAnthropic
from routeur_ia.fournisseurs.fabrique import ModeInvalide, creer_fournisseurs
from routeur_ia.fournisseurs.faux import FauxFournisseur
from routeur_ia.fournisseurs.google import FournisseurGoogle
from routeur_ia.journal import Journal
from tests.aides import config_brute, creer_config


def test_la_configuration_livree_est_valide() -> None:
    config = charger_config()
    assert config.modeles["claude-opus-5-5"].fournisseur == "anthropic"
    assert config.niveaux[0].modeles[0] == "claude-haiku-5-5"
    fournisseurs = {modele.fournisseur for modele in config.modeles.values()}
    assert fournisseurs == {"anthropic", "google"}


def test_chaque_niveau_livre_propose_les_deux_fournisseurs() -> None:
    """Sans cela, aucune bascule entre fournisseurs ne serait possible."""
    config = charger_config()
    for niveau in config.niveaux:
        assert {config.modeles[m].fournisseur for m in niveau.modeles} == {"anthropic", "google"}


def casser(section: str, cle: str, valeur: object) -> dict[str, Any]:
    brut = config_brute()
    brut[section][cle] = valeur
    return brut


@pytest.mark.parametrize(
    "brut",
    [
        {},
        casser("routage", "niveau_par_tache", {"general": "inconnu"}),
        casser("routage", "niveau_par_tache", {"code": "eco"}),
        casser("budget", "plafond_mensuel_usd", 5.0),  # un flottant perdrait l'exactitude
        casser("budget", "plafond_mensuel_usd", "-1"),
        casser("budget", "seuil_critique", 0.9),
        casser("routage", "seuil_long", 50),
        casser("tentatives", "max_essais", 0),
        casser("pannes", "echecs_avant_panne", 0),
        {**config_brute(), "niveaux": []},
        {**config_brute(), "niveaux": [{"nom": "eco", "modeles": []}]},
        {**config_brute(), "niveaux": [{"nom": "eco", "modeles": ["fantome"]}]},
    ],
)
def test_une_configuration_incoherente_est_refusee(brut: dict[str, Any]) -> None:
    with pytest.raises(ConfigInvalide):
        lire_config(brut)


def test_un_palier_incomplet_est_refuse() -> None:
    brut = config_brute()
    brut["modeles"][0].pop("prix_sortie_palier")
    with pytest.raises(ConfigInvalide, match="palier"):
        lire_config(brut)


def test_un_prix_negatif_est_refuse() -> None:
    brut = config_brute()
    brut["modeles"][1]["prix_entree"] = "-1"
    with pytest.raises(ConfigInvalide, match="négatif"):
        lire_config(brut)


def test_niveau_inconnu() -> None:
    with pytest.raises(KeyError):
        creer_config().niveau("inconnu")


def test_faux_par_defaut_meme_si_une_cle_est_presente() -> None:
    env = {"ANTHROPIC_API_KEY": "cle-factice", "GEMINI_API_KEY": "cle-factice"}
    fournisseurs = creer_fournisseurs(creer_config(), env)
    assert all(isinstance(f, FauxFournisseur) for f in fournisseurs.values())


def test_mode_inconnu_refuse() -> None:
    with pytest.raises(ModeInvalide):
        creer_fournisseurs(creer_config(), {"ROUTEUR_MODE": "turbo"})


@pytest.mark.parametrize("valeur", [None, ""])
def test_mode_reel_sans_cle_refuse(valeur: str | None) -> None:
    env = {"ROUTEUR_MODE": "reel"}
    if valeur is not None:
        env["ANTHROPIC_API_KEY"] = valeur
    with pytest.raises(ModeInvalide):
        creer_fournisseurs(creer_config(), env)


def test_mode_reel_ne_cree_que_les_fournisseurs_ayant_une_cle() -> None:
    env = {"ROUTEUR_MODE": "reel", "GEMINI_API_KEY": "cle-factice"}
    assert list(creer_fournisseurs(creer_config(), env)) == ["google"]
    env = {"ROUTEUR_MODE": "reel", "ANTHROPIC_API_KEY": "cle-factice"}
    assert list(creer_fournisseurs(creer_config(), env)) == ["anthropic"]


def test_mode_reel_cree_les_vrais_adaptateurs_sans_appel_reseau() -> None:
    env = {
        "ROUTEUR_MODE": "reel",
        "ANTHROPIC_API_KEY": "cle-factice",
        "GEMINI_API_KEY": "cle-factice",
    }
    fournisseurs = creer_fournisseurs(creer_config(), env)
    assert isinstance(fournisseurs["anthropic"], FournisseurAnthropic)
    assert isinstance(fournisseurs["google"], FournisseurGoogle)
    assert fournisseurs["anthropic"].nom == "anthropic"
    assert fournisseurs["google"].nom == "google"


def test_assemblage_depuis_l_environnement(tmp_path: Path) -> None:
    application = depuis_environnement(
        {"ROUTEUR_BASE": str(tmp_path / "j.sqlite"), "ROUTEUR_CONFIG": str(CHEMIN_PAR_DEFAUT)}
    )
    assert application.mode_faux
    assert application.jeton_api is None


def test_ecouter_hors_machine_locale_exige_un_jeton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ROUTEUR_BASE", str(tmp_path / "j.sqlite"))
    monkeypatch.setattr(cli, "serve", lambda *_, **__: pytest.fail("ne doit pas démarrer"))
    assert cli.main(["serve", "--hote", "0.0.0.0"]) == 2  # noqa: S104
    assert "ROUTEUR_JETON_API" in capsys.readouterr().err


def test_ecouter_hors_machine_locale_avec_un_jeton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROUTEUR_BASE", str(tmp_path / "j.sqlite"))
    monkeypatch.setenv("ROUTEUR_JETON_API", "jeton-factice")
    lancements: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "serve", lambda _, **options: lancements.append(options))
    assert cli.main(["serve", "--hote", "0.0.0.0", "--port", "9"]) == 0  # noqa: S104
    assert lancements == [{"host": "0.0.0.0", "port": 9}]  # noqa: S104


def test_la_commande_demo_cree_son_historique_une_seule_fois(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Même avec une clé et le mode réel dans l'environnement, la démo reste sans appel réel.
    monkeypatch.setenv("ROUTEUR_MODE", "reel")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "cle-factice")
    applications: list[Any] = []
    monkeypatch.setattr(cli, "serve", lambda app, **_: applications.append(app))

    assert cli.main(["demo"]) == 0
    lignes = Journal(tmp_path / cli.BASE_DEMO).derniers_appels(100_000)
    assert lignes
    assert cli.main(["demo"]) == 0
    assert len(Journal(tmp_path / cli.BASE_DEMO).derniers_appels(100_000)) == len(lignes)
    client = applications[0].test_client()
    assert client.get("/sante").json["mode"] == "faux"


def test_l_historique_de_demonstration_est_realiste_et_reproductible(tmp_path: Path) -> None:
    config = charger_config()
    maintenant = datetime(2026, 3, 15, 12, tzinfo=UTC)
    nombre = peupler(config, tmp_path / "a.sqlite", jours=14, maintenant=maintenant)
    peupler(config, tmp_path / "b.sqlite", jours=14, maintenant=maintenant)

    journal = Journal(tmp_path / "a.sqlite")
    lignes = journal.derniers_appels(100_000)
    assert nombre > 100
    assert any(ligne.bascule for ligne in lignes), "des bascules doivent apparaître"
    assert any(ligne.statut == "erreur" for ligne in lignes)
    assert {ligne.fournisseur for ligne in lignes} == {"anthropic", "google"}
    assert {ligne.horodatage.date() for ligne in lignes} == {
        (maintenant - timedelta(days=rang)).date() for rang in range(14)
    }
    depuis = maintenant.date() - timedelta(days=30)
    assert journal.depense_depuis(depuis) == Journal(tmp_path / "b.sqlite").depense_depuis(depuis)
