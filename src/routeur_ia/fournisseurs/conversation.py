"""Préparation de l'historique quand une conversation change de fournisseur en cours de route.

Un appel d'outil produit par Gemini n'a pas de sens pour Claude, et inversement : identifiants,
blocs de réflexion et signatures ne se transposent pas. Les tours d'un autre fournisseur sont donc
aplatis en texte ordinaire. L'information reste, sans format propriétaire à reproduire.
"""

import json

from routeur_ia.domaine import (
    AppelOutil,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ResultatOutil,
)


def adapter_historique(messages: tuple[Message, ...], fournisseur: str) -> tuple[Message, ...]:
    """Remplace par du texte les appels d'outils venus d'un autre fournisseur et leurs résultats."""
    sortie: list[Message] = []
    identifiants_aplatis: set[str] = set()
    for message in messages:
        if isinstance(message, MessageAssistant) and message.fournisseur != fournisseur:
            identifiants_aplatis.update(appel.id for appel in message.appels)
            sortie.append(MessageAssistant(texte=_assistant_en_texte(message)))
        elif isinstance(message, MessageResultats) and all(
            resultat.id_appel in identifiants_aplatis for resultat in message.resultats
        ):
            sortie.append(MessageUtilisateur(texte=_resultats_en_texte(message.resultats)))
        else:
            sortie.append(message)
    return tuple(sortie)


def _assistant_en_texte(message: MessageAssistant) -> str:
    morceaux = [message.texte] if message.texte else []
    morceaux.extend(_appel_en_texte(appel) for appel in message.appels)
    return "\n".join(morceaux)


def _appel_en_texte(appel: AppelOutil) -> str:
    return f"[appel de l'outil {appel.nom} : {json.dumps(appel.arguments, ensure_ascii=False)}]"


def _resultats_en_texte(resultats: tuple[ResultatOutil, ...]) -> str:
    return "\n".join(
        f"[résultat de l'outil {r.nom}{' (erreur)' if r.est_erreur else ''} : {r.contenu}]"
        for r in resultats
    )
