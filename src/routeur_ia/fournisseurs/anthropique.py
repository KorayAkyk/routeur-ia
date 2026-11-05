"""Adaptateur Claude, sur le SDK officiel `anthropic`.

Les reprises du SDK sont désactivées à la création du client : c'est le routeur qui les gère, sinon
les deux niveaux se multiplient. Les blocs de réflexion restent dans `brut` et repartent inchangés
au tour suivant, comme l'exige l'API.
"""

from typing import Any

import anthropic

from routeur_ia.domaine import (
    AppelOutil,
    Arret,
    DefinitionOutil,
    ErreurTransitoire,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ReponseModele,
    RequeteModele,
)
from routeur_ia.fournisseurs.conversation import adapter_historique
from routeur_ia.fournisseurs.erreurs_http import erreur_depuis_statut, lire_retry_after

NOM = "anthropic"

_ARRETS: dict[str, Arret] = {
    "end_turn": "fin",
    "stop_sequence": "fin",
    "tool_use": "outils",
    "max_tokens": "limite",
    "refusal": "refus",
}


def creer_client(cle: str, delai_s: float) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=cle, max_retries=0, timeout=delai_s)


class FournisseurAnthropic:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    @property
    def nom(self) -> str:
        return NOM

    def generer(self, requete: RequeteModele) -> ReponseModele:
        parametres = _parametres(requete)
        try:
            message = self._client.messages.create(**parametres)
        except anthropic.APITimeoutError as erreur:
            raise ErreurTransitoire("delai_depasse") from erreur
        except anthropic.APIConnectionError as erreur:
            raise ErreurTransitoire("connexion") from erreur
        except anthropic.APIStatusError as erreur:
            attente = lire_retry_after(erreur.response.headers.get("retry-after"))
            raise erreur_depuis_statut(erreur.status_code, attente) from erreur
        except anthropic.APIError as erreur:
            raise ErreurTransitoire("reponse_illisible") from erreur
        return _lire_reponse(message)


def _parametres(requete: RequeteModele) -> dict[str, Any]:
    parametres: dict[str, Any] = {
        "model": requete.modele,
        "max_tokens": requete.max_jetons,
        "messages": [_message(message) for message in adapter_historique(requete.messages, NOM)],
    }
    if requete.systeme:
        parametres["system"] = requete.systeme
    if requete.outils:
        parametres["tools"] = [_outil(outil) for outil in requete.outils]
    if requete.effort:
        parametres["output_config"] = {"effort": requete.effort}
    return parametres


def _outil(outil: DefinitionOutil) -> dict[str, object]:
    return {"name": outil.nom, "description": outil.description, "input_schema": outil.schema}


def _message(message: Message) -> dict[str, object]:
    match message:
        case MessageUtilisateur(texte=texte):
            return {"role": "user", "content": texte}
        case MessageAssistant(fournisseur=fournisseur, brut=brut) if fournisseur == NOM:
            return {"role": "assistant", "content": brut}
        case MessageAssistant(texte=texte):
            return {"role": "assistant", "content": texte}
        case MessageResultats(resultats=resultats):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": resultat.id_appel,
                        "content": resultat.contenu,
                        "is_error": resultat.est_erreur,
                    }
                    for resultat in resultats
                ],
            }


def _lire_reponse(message: anthropic.types.Message) -> ReponseModele:
    textes: list[str] = []
    appels: list[AppelOutil] = []
    for bloc in message.content:
        if bloc.type == "text":
            textes.append(bloc.text)
        elif bloc.type == "tool_use":
            appels.append(AppelOutil(bloc.id, bloc.name, dict(bloc.input)))
    return ReponseModele(
        texte="".join(textes),
        jetons_entree=message.usage.input_tokens,
        jetons_sortie=message.usage.output_tokens,
        arret=_ARRETS.get(message.stop_reason or "", "autre"),
        appels=tuple(appels),
        brut=message.content,
    )
