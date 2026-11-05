"""Orchestration : reprises, bascule, refus, budget, journal."""

from pathlib import Path

import pytest

from routeur_ia.domaine import (
    ErreurIndisponible,
    ErreurRequete,
    ErreurTransitoire,
    ReponseModele,
)
from routeur_ia.service import AucunFournisseur, BudgetEpuise
from tests.aides import (
    Dormeur,
    Horloge,
    creer_application,
    creer_config,
    demande,
    faux_fournisseurs,
)

REFUS = ReponseModele("", 10, 2, arret="refus")


@pytest.fixture
def chemin(tmp_path: Path) -> Path:
    return tmp_path / "journal.sqlite"


def surcharges() -> list[ErreurTransitoire]:
    return [ErreurTransitoire("http_529") for _ in range(3)]


def test_cas_nominal_premier_candidat(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(ReponseModele("bonjour", 1000, 500))
    application = creer_application(chemin, fournisseurs=fournisseurs)

    resultat = application.service.executer(demande())

    assert resultat.reponse.texte == "bonjour"
    assert resultat.modele.id == "a-std"
    assert not resultat.bascule
    assert resultat.cout_nano == 10_500_000  # 1000 x 3 $/M + 500 x 15 $/M
    assert fournisseurs["google"].requetes == []


def test_le_niveau_transmet_son_effort(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    creer_application(chemin, fournisseurs=fournisseurs).service.executer(demande("code"))
    assert fournisseurs["anthropic"].requetes[0].effort == "high"


def test_une_surcharge_passagere_est_reessayee_sur_le_meme_modele(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(ErreurTransitoire("http_529"))
    dormeur = Dormeur()
    application = creer_application(chemin, fournisseurs=fournisseurs, dormeur=dormeur)

    resultat = application.service.executer(demande())

    assert resultat.modele.id == "a-std"
    assert [(e.numero, e.statut) for e in resultat.essais] == [(1, "erreur"), (2, "ok")]
    assert dormeur.attentes == [1.0]
    assert fournisseurs["google"].requetes == []


def test_bascule_apres_epuisement_des_essais(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(*surcharges())
    application = creer_application(chemin, fournisseurs=fournisseurs)

    resultat = application.service.executer(demande())

    assert resultat.modele.id == "g-std"
    assert resultat.bascule
    assert len(fournisseurs["anthropic"].requetes) == 3
    assert [e.modele for e in resultat.essais] == ["a-std"] * 3 + ["g-std"]


def test_une_cle_refusee_bascule_sans_reessayer(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(ErreurIndisponible("http_401"))
    dormeur = Dormeur()
    application = creer_application(chemin, fournisseurs=fournisseurs, dormeur=dormeur)

    assert application.service.executer(demande()).modele.id == "g-std"
    assert len(fournisseurs["anthropic"].requetes) == 1
    assert dormeur.attentes == []


def test_une_demande_invalide_ne_bascule_pas(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(ErreurRequete("http_400"))
    application = creer_application(chemin, fournisseurs=fournisseurs)

    with pytest.raises(ErreurRequete):
        application.service.executer(demande())
    assert fournisseurs["google"].requetes == []
    assert application.budget.etat().reserve_nano == 0
    assert application.sante.est_disponible("anthropic")


def test_un_refus_du_modele_bascule_et_son_cout_est_compte(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(REFUS)
    fournisseurs["google"].programmer(ReponseModele("ok", 10, 2))
    application = creer_application(chemin, fournisseurs=fournisseurs)

    resultat = application.service.executer(demande())

    assert resultat.modele.id == "g-std"
    assert [e.statut for e in resultat.essais] == ["refus", "ok"]
    # 10 x 3 + 2 x 15 $/M côté Claude, 10 x 2 + 2 x 12 $/M côté Gemini
    assert resultat.cout_nano == 60_000 + 44_000


def test_si_tout_le_monde_refuse_le_dernier_refus_est_rendu(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(REFUS)
    fournisseurs["google"].programmer(REFUS)
    application = creer_application(chemin, fournisseurs=fournisseurs)

    resultat = application.service.executer(demande())

    assert resultat.reponse.arret == "refus"
    assert resultat.modele.id == "g-std"


def test_tous_les_candidats_en_echec(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(*surcharges())
    fournisseurs["google"].programmer(*surcharges())
    application = creer_application(chemin, fournisseurs=fournisseurs)

    with pytest.raises(AucunFournisseur) as erreur:
        application.service.executer(demande())
    assert len(erreur.value.essais) == 6
    assert application.budget.etat().reserve_nano == 0


def test_le_disjoncteur_evite_d_insister_sur_un_fournisseur_en_panne(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].simuler_panne()
    horloge = Horloge()
    application = creer_application(chemin, fournisseurs=fournisseurs, horloge=horloge)

    for _ in range(3):
        application.service.executer(demande())
    appels_avant = len(fournisseurs["anthropic"].requetes)
    assert not application.sante.est_disponible("anthropic")

    resultat = application.service.executer(demande())

    assert resultat.modele.id == "g-std"
    assert not resultat.bascule  # écarté dès le routage : Gemini est le premier candidat
    assert len(fournisseurs["anthropic"].requetes) == appels_avant

    horloge.secondes += 61
    fournisseurs["anthropic"].simuler_panne(False)
    assert application.service.executer(demande()).modele.id == "a-std"


def test_tout_en_panne_sans_aucun_appel(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    application = creer_application(chemin, fournisseurs=fournisseurs)
    for nom in fournisseurs:
        for _ in range(3):
            application.sante.signaler_echec(nom)

    with pytest.raises(AucunFournisseur):
        application.service.executer(demande())
    assert fournisseurs["anthropic"].requetes == []
    assert fournisseurs["google"].requetes == []


def test_un_fournisseur_sans_cle_n_est_jamais_candidat(chemin: Path) -> None:
    fournisseurs = {"google": faux_fournisseurs()["google"]}
    application = creer_application(chemin, fournisseurs=fournisseurs)
    assert application.service.executer(demande()).modele.id == "g-std"


def test_budget_epuise_aucun_appel(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    config = creer_config(budget={"plafond_mensuel_usd": "0"})
    application = creer_application(chemin, config, fournisseurs)

    with pytest.raises(BudgetEpuise):
        application.service.executer(demande())
    assert fournisseurs["anthropic"].requetes == []
    assert fournisseurs["google"].requetes == []


def test_un_candidat_trop_cher_cede_la_place_au_suivant(chemin: Path) -> None:
    """Maximum réservé : a-std 20 000 x 15 $/M = 0,30 $, g-std 20 000 x 12 $/M = 0,24 $."""
    fournisseurs = faux_fournisseurs()
    config = creer_config(budget={"plafond_mensuel_usd": "0.25"})
    application = creer_application(chemin, config, fournisseurs)

    resultat = application.service.executer(demande("resume", "x", max_jetons=20_000))

    assert resultat.modele.id == "g-std"
    assert fournisseurs["anthropic"].requetes == []
    assert resultat.essais[0].modele == "g-std"


def test_le_cout_reel_est_ecrit_et_la_reservation_rendue(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(ReponseModele("ok", 1000, 500))
    application = creer_application(chemin, fournisseurs=fournisseurs)

    application.service.executer(demande(max_jetons=4000))

    etat = application.budget.etat()
    assert etat.depense_nano == 10_500_000
    assert etat.reserve_nano == 0


def test_chaque_essai_a_sa_ligne_de_journal(chemin: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(*surcharges())
    fournisseurs["google"].programmer(ReponseModele("ok", 100, 50))
    application = creer_application(chemin, fournisseurs=fournisseurs)

    application.service.executer(demande())

    lignes = list(reversed(application.journal.derniers_appels()))
    assert [(ligne.modele, ligne.essai, ligne.statut) for ligne in lignes] == [
        ("a-std", 1, "erreur"),
        ("a-std", 2, "erreur"),
        ("a-std", 3, "erreur"),
        ("g-std", 1, "ok"),
    ]
    assert [ligne.bascule for ligne in lignes] == [False, False, False, True]
    assert lignes[0].code_erreur == "http_529"
    assert lignes[0].cout_nano == 0
    assert lignes[3].cout_nano == 800_000  # 100 x 2 $/M + 50 x 12 $/M
    assert len({ligne.id_demande for ligne in lignes}) == 1
