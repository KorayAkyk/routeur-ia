"""Adaptateur Gemini, sur le SDK officiel `google-genai`.

Le SDK ne fait aucune reprise par défaut, et l'appel automatique d'outils est désactivé : la boucle
d'agent reste la nôtre. Le `Content` renvoyé par le modèle est conservé entier dans `brut`, car il
porte les signatures de réflexion à rendre au tour suivant. Le réglage `effort` ne concerne que
Claude et n'est pas transmis ici.
"""

import httpx
import httpx2
from google import genai
from google.genai import errors, types

from routeur_ia.domaine import (
    AppelOutil,
    Arret,
    ErreurFournisseur,
    ErreurIndisponible,
    ErreurTransitoire,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ReponseModele,
    RequeteModele,
)
from routeur_ia.fournisseurs.conversation import adapter_historique
from routeur_ia.fournisseurs.erreurs_http import erreur_depuis_statut

NOM = "google"

_REFUS = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.SPII,
        types.FinishReason.RECITATION,
    }
)


def creer_client(cle: str, delai_s: float) -> genai.Client:
    return genai.Client(api_key=cle, http_options=types.HttpOptions(timeout=int(delai_s * 1000)))


class FournisseurGoogle:
    def __init__(self, client: genai.Client) -> None:
        self._client = client

    @property
    def nom(self) -> str:
        return NOM

    def generer(self, requete: RequeteModele) -> ReponseModele:
        contenus = [_contenu(m) for m in adapter_historique(requete.messages, NOM)]
        configuration = _configuration(requete)
        try:
            reponse = self._client.models.generate_content(
                model=requete.modele, contents=contenus, config=configuration
            )
        except errors.APIError as erreur:
            raise _traduire(erreur) from erreur
        except ValueError as erreur:  # corps de réponse qui n'est pas du JSON attendu
            raise ErreurTransitoire("reponse_illisible") from erreur
        except (httpx.TimeoutException, httpx2.TimeoutException) as erreur:
            raise ErreurTransitoire("delai_depasse") from erreur
        except (httpx.TransportError, httpx2.TransportError) as erreur:
            raise ErreurTransitoire("connexion") from erreur
        return _lire_reponse(reponse)


def _traduire(erreur: errors.APIError) -> ErreurFournisseur:
    # L'API répond 400, et non 401, à une clé invalide : la demande n'y est pour rien.
    if erreur.code == 400 and "API_KEY_INVALID" in str(erreur.details):
        return ErreurIndisponible("cle_refusee")
    return erreur_depuis_statut(erreur.code)


def _configuration(requete: RequeteModele) -> types.GenerateContentConfig:
    outils = [
        types.FunctionDeclaration(
            name=outil.nom, description=outil.description, parameters_json_schema=outil.schema
        )
        for outil in requete.outils
    ]
    return types.GenerateContentConfig(
        system_instruction=requete.systeme,
        max_output_tokens=requete.max_jetons,
        tools=[types.Tool(function_declarations=outils)] if outils else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _contenu(message: Message) -> types.Content:
    match message:
        case MessageUtilisateur(texte=texte):
            return types.Content(role="user", parts=[types.Part(text=texte)])
        case MessageAssistant(brut=types.Content() as brut, fournisseur=fournisseur) if (
            fournisseur == NOM
        ):
            return brut
        case MessageAssistant(texte=texte):
            return types.Content(role="model", parts=[types.Part(text=texte)])
        case MessageResultats(resultats=resultats):
            parties = [
                types.Part(
                    function_response=types.FunctionResponse(
                        id=resultat.id_appel,
                        name=resultat.nom,
                        response={"error" if resultat.est_erreur else "output": resultat.contenu},
                    )
                )
                for resultat in resultats
            ]
            return types.Content(role="user", parts=parties)
    raise TypeError(f"message inattendu : {type(message).__name__}")


def _lire_reponse(reponse: types.GenerateContentResponse) -> ReponseModele:
    usage = reponse.usage_metadata
    jetons_entree = (usage.prompt_token_count or 0) if usage else 0
    jetons_entree += (usage.tool_use_prompt_token_count or 0) if usage else 0
    # La réflexion est comptée à part par l'API, mais facturée au tarif de sortie.
    jetons_sortie = (usage.candidates_token_count or 0) if usage else 0
    jetons_sortie += (usage.thoughts_token_count or 0) if usage else 0

    candidat = reponse.candidates[0] if reponse.candidates else None
    contenu = candidat.content if candidat else None
    textes: list[str] = []
    appels: list[AppelOutil] = []
    for rang, partie in enumerate((contenu.parts or []) if contenu else []):
        appel = partie.function_call
        if appel and appel.name:
            appels.append(
                AppelOutil(appel.id or f"google-{rang}", appel.name, dict(appel.args or {}))
            )
        elif partie.text and not partie.thought:
            textes.append(partie.text)
    return ReponseModele(
        texte="".join(textes),
        jetons_entree=jetons_entree,
        jetons_sortie=jetons_sortie,
        arret=_arret(candidat, bool(appels)),
        appels=tuple(appels),
        brut=contenu,
    )


def _arret(candidat: types.Candidate | None, a_des_appels: bool) -> Arret:
    if candidat is None:
        return "refus"  # demande bloquée avant toute génération
    if a_des_appels:
        return "outils"
    if candidat.finish_reason in _REFUS:
        return "refus"
    if candidat.finish_reason == types.FinishReason.MAX_TOKENS:
        return "limite"
    return "fin" if candidat.finish_reason == types.FinishReason.STOP else "autre"
