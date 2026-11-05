"""Aplatissement de l'historique quand une conversation change de fournisseur."""

from routeur_ia.domaine import (
    AppelOutil,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ResultatOutil,
)
from routeur_ia.fournisseurs.conversation import adapter_historique

HISTORIQUE: tuple[Message, ...] = (
    MessageUtilisateur("question"),
    MessageAssistant(
        texte="je cherche",
        appels=(AppelOutil("id-1", "calculer", {"expression": "1 + 1"}),),
        brut="brut-gemini",
        fournisseur="google",
    ),
    MessageResultats((ResultatOutil("id-1", "calculer", "2"),)),
)


def test_le_meme_fournisseur_recoit_l_historique_intact() -> None:
    assert adapter_historique(HISTORIQUE, "google") == HISTORIQUE


def test_un_autre_fournisseur_recoit_du_texte_sans_format_proprietaire() -> None:
    utilisateur, assistant, resultats = adapter_historique(HISTORIQUE, "anthropic")

    assert utilisateur == HISTORIQUE[0]
    assert isinstance(assistant, MessageAssistant)
    assert assistant.appels == ()
    assert assistant.brut is None
    assert "je cherche" in assistant.texte
    assert '[appel de l\'outil calculer : {"expression": "1 + 1"}]' in assistant.texte
    assert isinstance(resultats, MessageUtilisateur)
    assert resultats.texte == "[résultat de l'outil calculer : 2]"


def test_une_erreur_d_outil_reste_signalee_une_fois_aplatie() -> None:
    historique: tuple[Message, ...] = (
        MessageAssistant("", (AppelOutil("i", "calculer", {}),), fournisseur="google"),
        MessageResultats((ResultatOutil("i", "calculer", "refusé", est_erreur=True),)),
    )
    _, resultats = adapter_historique(historique, "anthropic")
    assert isinstance(resultats, MessageUtilisateur)
    assert "(erreur)" in resultats.texte


def test_histoire_mixte_seuls_les_tours_etrangers_sont_aplatis() -> None:
    historique: tuple[Message, ...] = (
        *HISTORIQUE,
        MessageAssistant(
            "suite", (AppelOutil("id-2", "calculer", {}),), brut="brut", fournisseur="anthropic"
        ),
        MessageResultats((ResultatOutil("id-2", "calculer", "3"),)),
    )
    sortie = adapter_historique(historique, "anthropic")
    assert isinstance(sortie[3], MessageAssistant)
    assert sortie[3].brut == "brut"
    assert isinstance(sortie[4], MessageResultats)
