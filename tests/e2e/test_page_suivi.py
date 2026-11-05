"""Parcours dans un vrai navigateur, contre un vrai serveur local, sur le faux fournisseur."""

import re
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import ConsoleMessage, Page, expect
from werkzeug.serving import make_server

from routeur_ia.config import Config
from routeur_ia.web import creer_app
from tests.aides import creer_application, creer_config

pytestmark = pytest.mark.navigateur

Lanceur = Callable[[Config | None], str]


@pytest.fixture
def lancer(tmp_path: Path) -> Iterator[Lanceur]:
    serveurs = []

    def demarrer(config: Config | None = None) -> str:
        application = creer_application(tmp_path / "journal.sqlite", config)
        serveur = make_server("127.0.0.1", 0, creer_app(application), threaded=True)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        serveurs.append(serveur)
        return f"http://127.0.0.1:{serveur.server_port}"

    yield demarrer
    for serveur in serveurs:
        serveur.shutdown()


@pytest.fixture
def erreurs_console(page: Page) -> list[str]:
    """Une violation de la politique de sécurité apparaîtrait ici."""
    erreurs: list[str] = []

    def noter(message: ConsoleMessage) -> None:
        if message.type == "error":
            erreurs.append(message.text)

    page.on("console", noter)
    page.on("pageerror", lambda erreur: erreurs.append(str(erreur)))
    return erreurs


def envoyer(page: Page, tache: str, message: str = "x" * 600) -> None:
    page.get_by_test_id("essai-tache").select_option(tache)
    page.get_by_test_id("essai-message").fill(message)
    page.get_by_test_id("essai-envoyer").click()


def test_de_la_page_vide_a_la_bascule(
    page: Page, lancer: Lanceur, erreurs_console: list[str]
) -> None:
    page.goto(lancer(None))

    # Page vide : le mode démonstration est annoncé, aucun graphique.
    expect(page.get_by_test_id("bandeau-demo")).to_contain_text("aucun vrai modèle appelé")
    expect(page.get_by_test_id("vide")).to_be_visible()
    expect(page.get_by_test_id("graphique")).to_have_count(0)
    expect(page.get_by_test_id("appels-periode")).to_have_text("0")

    # Une tâche de code part sur le modèle le plus capable.
    envoyer(page, "code")
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("Modèle a-exp (niveau expert)")
    expect(page.get_by_test_id("appels-periode")).to_have_text("1")
    expect(page.get_by_test_id("vide")).to_have_count(0)
    expect(page.get_by_test_id("graphique").locator("path[data-modele='a-exp']")).to_have_count(1)
    expect(page.get_by_test_id("table-modeles")).to_contain_text("a-exp")

    # Une classification part sur le moins cher : le coût suit le modèle, tâche par tâche.
    envoyer(page, "classification", "x" * 30)
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("Modèle a-eco (niveau eco)")
    expect(page.get_by_test_id("table-modeles").locator("tbody tr")).to_have_count(2)

    # Panne simulée de Claude : la demande réussit sur Gemini, et la bascule se voit.
    bouton_panne = page.get_by_test_id("fournisseur-anthropic").get_by_role("button")
    expect(bouton_panne).to_have_text("Simuler une panne")
    bouton_panne.click()
    expect(bouton_panne).to_have_text("Rétablir")
    envoyer(page, "resume")
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("g-std")
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("après bascule")
    expect(page.get_by_test_id("bascule").first).to_be_visible()
    expect(page.get_by_test_id("table-derniers")).to_contain_text("panne_simulee")

    # Après trois appels perdus, le fournisseur est marqué en panne.
    envoyer(page, "resume")
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("g-std")
    envoyer(page, "resume")
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("g-std")
    expect(page.get_by_test_id("fournisseur-anthropic")).to_contain_text("en panne")

    # Le rétablissement remet Claude en premier choix.
    bouton_panne.click()
    expect(page.get_by_test_id("fournisseur-anthropic")).to_contain_text("disponible")
    envoyer(page, "resume")
    expect(page.get_by_test_id("essai-resultat")).to_contain_text("Modèle a-std")

    assert erreurs_console == []


def test_changement_de_periode(page: Page, lancer: Lanceur) -> None:
    page.goto(lancer(None))
    envoyer(page, "resume")
    expect(page.get_by_test_id("appels-periode")).to_have_text("1")

    page.get_by_role("link", name="7 jours").click()

    expect(page).to_have_url(re.compile(r"\?jours=7$"))
    expect(page.get_by_role("heading", name="Coût sur 7 jours")).to_be_visible()
    expect(page.get_by_role("link", name="7 jours")).to_have_attribute("aria-current", "true")
    # Horloge de test fixée en mars 2026 : le journal reste lu sur la bonne période.
    expect(page.get_by_test_id("appels-periode")).to_have_text("1")


def test_budget_epuise_affiche_a_l_utilisateur(page: Page, lancer: Lanceur) -> None:
    page.goto(lancer(creer_config(budget={"plafond_mensuel_usd": "0"})))

    envoyer(page, "resume")

    expect(page.get_by_test_id("essai-resultat")).to_contain_text("Échec (402) : budget_epuise")
    expect(page.get_by_test_id("appels-periode")).to_have_text("0")
