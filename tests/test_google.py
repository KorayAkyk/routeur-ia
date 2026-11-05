"""Adaptateur Gemini : le vrai SDK, sur un transport HTTP simulé. Aucun appel ne sort.

Ces tests vérifient la forme des requêtes et la lecture des réponses à travers le SDK officiel. Ils
ne prouvent pas que l'API réelle les accepte : aucun appel réel n'a été fait.
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import types

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
from routeur_ia.fournisseurs.google import FournisseurGoogle

Gestionnaire = Callable[[httpx.Request], httpx.Response]


def fournisseur(gestionnaire: Gestionnaire) -> FournisseurGoogle:
    client = genai.Client(
        api_key="cle-factice",
        http_options=types.HttpOptions(
            httpx_client=httpx.Client(transport=httpx.MockTransport(gestionnaire))
        ),
    )
    return FournisseurGoogle(client)


def reponse_api(parties: list[dict[str, Any]], fin: str = "STOP") -> dict[str, Any]:
    return {
        "candidates": [{"content": {"role": "model", "parts": parties}, "finishReason": fin}],
        "usageMetadata": {
            "promptTokenCount": 11,
            "candidatesTokenCount": 7,
            "thoughtsTokenCount": 5,
        },
    }


def requete(**surcharges: Any) -> RequeteModele:
    valeurs: dict[str, Any] = {
        "modele": "gemini-3.8-flash",
        "messages": (MessageUtilisateur("bonjour"),),
        "max_jetons": 50,
    }
    return RequeteModele(**{**valeurs, **surcharges})


def capturer(reponse: dict[str, Any]) -> tuple[Gestionnaire, list[httpx.Request]]:
    demandes: list[httpx.Request] = []

    def gestionnaire(demande: httpx.Request) -> httpx.Response:
        demandes.append(demande)
        return httpx.Response(200, json=reponse)

    return gestionnaire, demandes


def test_requete_et_lecture_de_la_reponse() -> None:
    gestionnaire, demandes = capturer(reponse_api([{"text": "salut"}]))

    reponse = fournisseur(gestionnaire).generer(requete(systeme="Sois bref"))

    assert "gemini-3.8-flash:generateContent" in str(demandes[0].url)
    corps = json.loads(demandes[0].content)
    assert corps["contents"] == [{"role": "user", "parts": [{"text": "bonjour"}]}]
    assert corps["generationConfig"]["maxOutputTokens"] == 50
    assert corps["systemInstruction"]["parts"][0]["text"] == "Sois bref"
    assert reponse.texte == "salut"
    assert reponse.arret == "fin"


def test_la_reflexion_est_comptee_en_sortie() -> None:
    """L'API la compte à part, mais la facture au tarif de sortie."""
    gestionnaire, _ = capturer(reponse_api([{"text": "x"}]))
    reponse = fournisseur(gestionnaire).generer(requete())
    assert (reponse.jetons_entree, reponse.jetons_sortie) == (11, 12)


def test_le_texte_de_reflexion_n_est_pas_rendu() -> None:
    gestionnaire, _ = capturer(reponse_api([{"text": "pensée", "thought": True}, {"text": "fin"}]))
    assert fournisseur(gestionnaire).generer(requete()).texte == "fin"


def test_l_effort_n_est_pas_transmis_a_gemini() -> None:
    gestionnaire, demandes = capturer(reponse_api([{"text": "x"}]))
    fournisseur(gestionnaire).generer(requete(effort="high"))
    assert "effort" not in demandes[0].content.decode()


def test_declaration_et_lecture_d_un_appel_d_outil() -> None:
    parties = [{"functionCall": {"name": "calculer", "args": {"expression": "1+1"}}}]
    gestionnaire, demandes = capturer(reponse_api(parties))
    schema = {"type": "object", "properties": {"expression": {"type": "string"}}}

    reponse = fournisseur(gestionnaire).generer(
        requete(outils=(DefinitionOutil("calculer", "Calcule", schema),))
    )

    declaration = json.loads(demandes[0].content)["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "calculer"
    assert declaration["parameters_json_schema"] == schema
    assert reponse.arret == "outils"
    assert reponse.appels == (AppelOutil("google-0", "calculer", {"expression": "1+1"}),)


def test_la_signature_de_reflexion_repart_au_tour_suivant() -> None:
    signature = "c2lnbmF0dXJl"
    parties = [{"functionCall": {"name": "calculer", "args": {}}, "thoughtSignature": signature}]
    gestionnaire, demandes = capturer(reponse_api(parties))
    adaptateur = fournisseur(gestionnaire)
    premier = adaptateur.generer(requete())

    adaptateur.generer(
        requete(
            messages=(
                MessageUtilisateur("q"),
                MessageAssistant("", premier.appels, premier.brut, "google"),
                MessageResultats((ResultatOutil("google-0", "calculer", "2"),)),
            )
        )
    )

    contenus = json.loads(demandes[1].content)["contents"]
    assert contenus[1]["parts"][0]["thoughtSignature"] == signature
    reponse_outil = contenus[2]["parts"][0]["functionResponse"]
    assert (reponse_outil["name"], reponse_outil["response"]) == ("calculer", {"output": "2"})


def test_une_erreur_d_outil_est_signalee_au_modele() -> None:
    gestionnaire, demandes = capturer(reponse_api([{"text": "x"}]))
    fournisseur(gestionnaire).generer(
        requete(
            messages=(
                MessageUtilisateur("q"),
                MessageAssistant("", (AppelOutil("i", "calculer", {}),), None, "google"),
                MessageResultats((ResultatOutil("i", "calculer", "non", est_erreur=True),)),
            )
        )
    )
    corps = json.loads(demandes[0].content)["contents"][2]["parts"][0]
    assert corps["functionResponse"]["response"] == {"error": "non"}


@pytest.mark.parametrize(
    ("fin", "arret"),
    [
        ("STOP", "fin"),
        ("MAX_TOKENS", "limite"),
        ("SAFETY", "refus"),
        ("PROHIBITED_CONTENT", "refus"),
        ("OTHER", "autre"),
    ],
)
def test_traduction_des_raisons_d_arret(fin: str, arret: str) -> None:
    gestionnaire, _ = capturer(reponse_api([{"text": "x"}], fin=fin))
    assert fournisseur(gestionnaire).generer(requete()).arret == arret


def test_une_demande_bloquee_sans_candidat_est_un_refus() -> None:
    gestionnaire, _ = capturer({"promptFeedback": {"blockReason": "SAFETY"}})
    reponse = fournisseur(gestionnaire).generer(requete())
    assert reponse.arret == "refus"
    assert (reponse.texte, reponse.jetons_entree, reponse.jetons_sortie) == ("", 0, 0)


def erreur_api(statut: int, raison: str = "AUTRE") -> httpx.Response:
    return httpx.Response(
        statut,
        json={
            "error": {
                "code": statut,
                "message": "secret",
                "status": "X",
                "details": [{"reason": raison}],
            }
        },
    )


@pytest.mark.parametrize(
    ("statut", "classe"),
    [
        (429, ErreurTransitoire),
        (500, ErreurTransitoire),
        (503, ErreurTransitoire),
        (400, ErreurRequete),
        (401, ErreurIndisponible),
        (403, ErreurIndisponible),
        (404, ErreurIndisponible),
    ],
)
def test_classement_des_erreurs_http(statut: int, classe: type[ErreurFournisseur]) -> None:
    with pytest.raises(classe) as erreur:
        fournisseur(lambda _: erreur_api(statut)).generer(requete())
    assert erreur.value.code == f"http_{statut}"
    assert "secret" not in str(erreur.value)


def test_une_cle_invalide_en_400_n_est_pas_une_demande_invalide() -> None:
    with pytest.raises(ErreurIndisponible) as erreur:
        fournisseur(lambda _: erreur_api(400, "API_KEY_INVALID")).generer(requete())
    assert erreur.value.code == "cle_refusee"


def test_le_sdk_ne_refait_pas_de_tentatives_de_son_cote() -> None:
    appels: list[int] = []

    def gestionnaire(_: httpx.Request) -> httpx.Response:
        appels.append(1)
        return erreur_api(503)

    with pytest.raises(ErreurTransitoire):
        fournisseur(gestionnaire).generer(requete())
    assert len(appels) == 1


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ReadTimeout("lent"), "delai_depasse"),
        (httpx.ConnectError("coupure"), "connexion"),
    ],
)
def test_erreurs_reseau(exception: Exception, code: str) -> None:
    def gestionnaire(_: httpx.Request) -> httpx.Response:
        raise exception

    with pytest.raises(ErreurTransitoire) as erreur:
        fournisseur(gestionnaire).generer(requete())
    assert erreur.value.code == code


def test_une_reponse_illisible_est_transitoire() -> None:
    reponse = httpx.Response(200, content=b"pas du json")
    with pytest.raises(ErreurTransitoire) as erreur:
        fournisseur(lambda _: reponse).generer(requete())
    assert erreur.value.code == "reponse_illisible"
