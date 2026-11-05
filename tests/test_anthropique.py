"""Adaptateur Claude : le vrai SDK, sur un transport HTTP simulé. Aucun appel ne sort.

Ces tests vérifient la forme des requêtes et la lecture des réponses à travers le SDK officiel. Ils
ne prouvent pas que l'API réelle les accepte : aucun appel réel n'a été fait.
"""

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from routeur_ia.domaine import (
    AppelOutil,
    DefinitionOutil,
    ErreurFournisseur,
    ErreurIndisponible,
    ErreurRequete,
    ErreurTransitoire,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    RequeteModele,
    ResultatOutil,
)
from routeur_ia.fournisseurs.anthropique import FournisseurAnthropic

Gestionnaire = Callable[[httpx2.Request], httpx2.Response]


def fournisseur(gestionnaire: Gestionnaire) -> FournisseurAnthropic:
    client = anthropic.Anthropic(
        api_key="cle-factice",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(gestionnaire)),
    )
    return FournisseurAnthropic(client)


def message_api(contenu: list[dict[str, Any]], arret: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": contenu,
        "stop_reason": arret,
        "stop_sequence": None,
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }


def requete(**surcharges: Any) -> RequeteModele:
    valeurs: dict[str, Any] = {
        "modele": "claude-sonnet-5-5",
        "messages": (MessageUtilisateur("bonjour"),),
        "max_jetons": 50,
    }
    return RequeteModele(**{**valeurs, **surcharges})


def capturer(reponse: dict[str, Any]) -> tuple[Gestionnaire, list[dict[str, Any]]]:
    corps: list[dict[str, Any]] = []

    def gestionnaire(demande: httpx2.Request) -> httpx2.Response:
        corps.append(json.loads(demande.content))
        return httpx2.Response(200, json=reponse)

    return gestionnaire, corps


def test_requete_minimale_et_lecture_de_la_reponse() -> None:
    gestionnaire, corps = capturer(message_api([{"type": "text", "text": "salut"}]))

    reponse = fournisseur(gestionnaire).generer(requete())

    assert corps[0] == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 50,
        "messages": [{"role": "user", "content": "bonjour"}],
    }
    assert (reponse.texte, reponse.jetons_entree, reponse.jetons_sortie) == ("salut", 11, 7)
    assert reponse.arret == "fin"


def test_consigne_effort_et_outils_sont_transmis() -> None:
    gestionnaire, corps = capturer(message_api([{"type": "text", "text": "ok"}]))
    outil = DefinitionOutil("calculer", "Calcule", {"type": "object", "properties": {}})

    fournisseur(gestionnaire).generer(requete(systeme="Sois bref", effort="low", outils=(outil,)))

    assert corps[0]["system"] == "Sois bref"
    assert corps[0]["output_config"] == {"effort": "low"}
    assert corps[0]["tools"][0]["name"] == "calculer"
    assert corps[0]["tools"][0]["input_schema"] == {"type": "object", "properties": {}}


def test_aucun_reglage_refuse_par_les_modeles_recents_n_est_envoye() -> None:
    """temperature, thinking désactivé et tool_choice forcé renvoient une erreur 400."""
    gestionnaire, corps = capturer(message_api([{"type": "text", "text": "ok"}]))
    fournisseur(gestionnaire).generer(requete())
    assert not {"temperature", "top_p", "top_k", "thinking", "tool_choice"} & corps[0].keys()


def test_lecture_d_un_appel_d_outil_en_ignorant_la_reflexion() -> None:
    contenu: list[dict[str, Any]] = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "je calcule"},
        {"type": "tool_use", "id": "tu_1", "name": "calculer", "input": {"expression": "1+1"}},
    ]
    gestionnaire, _ = capturer(message_api(contenu, arret="tool_use"))

    reponse = fournisseur(gestionnaire).generer(requete())

    assert reponse.arret == "outils"
    assert reponse.texte == "je calcule"
    assert reponse.appels == (AppelOutil("tu_1", "calculer", {"expression": "1+1"}),)


def test_les_blocs_de_reflexion_repartent_intacts_au_tour_suivant() -> None:
    contenu: list[dict[str, Any]] = [
        {"type": "thinking", "thinking": "", "signature": "signature-a-conserver"},
        {"type": "tool_use", "id": "tu_1", "name": "calculer", "input": {}},
    ]
    gestionnaire, corps = capturer(message_api(contenu, arret="tool_use"))
    adaptateur = fournisseur(gestionnaire)
    premier = adaptateur.generer(requete())

    adaptateur.generer(
        requete(
            messages=(
                MessageUtilisateur("q"),
                MessageAssistant("", premier.appels, premier.brut, "anthropic"),
                MessageResultats((ResultatOutil("tu_1", "calculer", "2"),)),
            )
        )
    )

    assistant = corps[1]["messages"][1]
    assert assistant["content"][0]["signature"] == "signature-a-conserver"
    assert corps[1]["messages"][2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": "2",
        "is_error": False,
    }


def test_un_tour_venu_d_un_autre_fournisseur_devient_du_texte() -> None:
    gestionnaire, corps = capturer(message_api([{"type": "text", "text": "ok"}]))
    fournisseur(gestionnaire).generer(
        requete(
            messages=(
                MessageUtilisateur("q"),
                MessageAssistant("", (AppelOutil("g-1", "calculer", {}),), "brut", "google"),
                MessageResultats((ResultatOutil("g-1", "calculer", "2"),)),
            )
        )
    )
    roles = [message["role"] for message in corps[0]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert "calculer" in corps[0]["messages"][1]["content"]
    assert corps[0]["messages"][2]["content"] == "[résultat de l'outil calculer : 2]"


@pytest.mark.parametrize(
    ("arret_api", "arret"),
    [
        ("end_turn", "fin"),
        ("stop_sequence", "fin"),
        ("max_tokens", "limite"),
        ("refusal", "refus"),
        ("pause_turn", "autre"),
    ],
)
def test_traduction_des_raisons_d_arret(arret_api: str, arret: str) -> None:
    gestionnaire, _ = capturer(message_api([{"type": "text", "text": "x"}], arret=arret_api))
    assert fournisseur(gestionnaire).generer(requete()).arret == arret


@pytest.mark.parametrize(
    ("statut", "classe"),
    [
        (429, ErreurTransitoire),
        (500, ErreurTransitoire),
        (503, ErreurTransitoire),
        (529, ErreurTransitoire),
        (400, ErreurRequete),
        (413, ErreurRequete),
        (401, ErreurIndisponible),
        (402, ErreurIndisponible),
        (403, ErreurIndisponible),
        (404, ErreurIndisponible),
    ],
)
def test_classement_des_erreurs_http(statut: int, classe: type[ErreurFournisseur]) -> None:
    def gestionnaire(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(statut, json={"type": "error", "error": {"message": "secret"}})

    with pytest.raises(classe) as erreur:
        fournisseur(gestionnaire).generer(requete())
    assert erreur.value.code == f"http_{statut}"
    assert "secret" not in str(erreur.value)


def test_retry_after_est_lu() -> None:
    def gestionnaire(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, headers={"retry-after": "7"}, json={})

    with pytest.raises(ErreurTransitoire) as erreur:
        fournisseur(gestionnaire).generer(requete())
    assert erreur.value.attente_suggeree == 7.0


def test_le_sdk_ne_refait_pas_de_tentatives_de_son_cote() -> None:
    appels: list[int] = []

    def gestionnaire(_: httpx2.Request) -> httpx2.Response:
        appels.append(1)
        return httpx2.Response(503, json={})

    with pytest.raises(ErreurTransitoire):
        fournisseur(gestionnaire).generer(requete())
    assert len(appels) == 1


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx2.ReadTimeout("lent"), "delai_depasse"),
        (httpx2.ConnectError("coupure"), "connexion"),
    ],
)
def test_erreurs_reseau(exception: Exception, code: str) -> None:
    def gestionnaire(_: httpx2.Request) -> httpx2.Response:
        raise exception

    with pytest.raises(ErreurTransitoire) as erreur:
        fournisseur(gestionnaire).generer(requete())
    assert erreur.value.code == code


def test_une_reponse_illisible_est_transitoire() -> None:
    def gestionnaire(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"pas du json", headers={"content-type": "text/plain"})

    client = anthropic.Anthropic(
        api_key="cle-factice",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(gestionnaire)),
        _strict_response_validation=True,
    )
    with pytest.raises(ErreurTransitoire) as erreur:
        FournisseurAnthropic(client).generer(requete())
    assert erreur.value.code == "reponse_illisible"
