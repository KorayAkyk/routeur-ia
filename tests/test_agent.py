"""Boucle d'agent sur faux fournisseur, y compris une bascule en cours de boucle."""

from pathlib import Path

from routeur_ia.agent.boucle import Agent
from routeur_ia.agent.outils import outils_par_defaut
from routeur_ia.domaine import (
    AppelOutil,
    ErreurTransitoire,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ReponseModele,
)
from tests.aides import INSTANT, creer_application, faux_fournisseurs


def appel(nom: str = "calculer", **arguments: object) -> ReponseModele:
    return ReponseModele(
        texte="je calcule",
        jetons_entree=10,
        jetons_sortie=5,
        arret="outils",
        appels=(AppelOutil("id-1", nom, arguments),),
        brut=["bloc-brut"],
    )


def test_un_tour_d_outil_puis_la_reponse(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(
        appel(expression="6 * 7"), ReponseModele("Le résultat est 42.", 20, 8)
    )
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)

    resultat = application.agent.executer("Combien font 6 fois 7 ?")

    assert resultat.arret == "termine"
    assert resultat.texte == "Le résultat est 42."
    assert resultat.etapes[0].resultats[0].contenu == "42"
    assert resultat.cout_nano == application.budget.etat().depense_nano


def test_le_second_tour_recoit_l_historique_complet(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(appel(expression="1 + 1"), ReponseModele("2", 1, 1))
    creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs).agent.executer("1 + 1 ?")

    messages = fournisseurs["anthropic"].requetes[1].messages
    assert isinstance(messages[0], MessageUtilisateur)
    assert isinstance(messages[1], MessageAssistant)
    assert messages[1].brut == ["bloc-brut"]
    assert messages[1].fournisseur == "anthropic"
    assert isinstance(messages[2], MessageResultats)
    assert messages[2].resultats[0].contenu == "2"


def test_les_definitions_d_outils_sont_transmises(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs).agent.executer("bonjour")
    noms = {outil.nom for outil in fournisseurs["anthropic"].requetes[0].outils}
    assert noms == {"calculer", "date_du_jour"}


def test_une_erreur_d_outil_est_rendue_au_modele(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(appel(expression="1 / 0"), ReponseModele("désolé", 1, 1))
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)

    resultat = application.agent.executer("divise")

    sortie = resultat.etapes[0].resultats[0]
    assert sortie.est_erreur
    assert "ZeroDivisionError" in sortie.contenu
    assert resultat.arret == "termine"


def test_un_outil_inconnu_n_arrete_pas_la_boucle(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(appel(nom="effacer_tout"), ReponseModele("ok", 1, 1))
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)

    sortie = application.agent.executer("efface").etapes[0].resultats[0]

    assert sortie.est_erreur
    assert sortie.contenu == "outil inconnu"


def test_le_nombre_de_tours_est_borne(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(*(appel(expression="1 + 1") for _ in range(20)))
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)

    agent = Agent(application.service, outils_par_defaut(lambda: INSTANT), max_etapes=3)
    resultat = agent.executer("boucle sans fin")

    assert resultat.arret == "limite_etapes"
    assert len(resultat.etapes) == 3
    assert len(fournisseurs["anthropic"].requetes) == 3


def test_bascule_en_cours_de_boucle(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(
        appel(expression="2 + 2"), *(ErreurTransitoire("http_529") for _ in range(3))
    )
    fournisseurs["google"].programmer(ReponseModele("4, sur Gemini", 5, 5))
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)

    resultat = application.agent.executer("2 + 2 ?")

    assert resultat.texte == "4, sur Gemini"
    assert [etape.modele for etape in resultat.etapes] == ["a-std", "g-std"]


def test_le_faux_fournisseur_suffit_a_faire_tourner_l_agent(tmp_path: Path) -> None:
    application = creer_application(tmp_path / "j.sqlite")
    resultat = application.agent.executer("Combien font 12 * 12 ?")
    assert resultat.arret == "termine"
    assert "144" in resultat.texte
    assert application.agent.executer("Quelle date sommes-nous ?").etapes[0].resultats[
        0
    ].contenu == ("2026-03-15")
