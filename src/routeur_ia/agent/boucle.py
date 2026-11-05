"""Boucle d'agent : le modèle demande des outils, on les exécute, on lui rend les résultats.

Chaque tour passe par le service de routage. L'agent profite donc sans code en plus de la bascule,
du budget et du journal. Le nombre de tours est borné pour que le coût reste borné.
"""

from dataclasses import dataclass
from typing import Literal

from routeur_ia.agent.outils import ErreurOutil, Outil
from routeur_ia.domaine import (
    AppelOutil,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ResultatOutil,
)
from routeur_ia.service import Demande, ServiceRoutage

_CONSIGNE = (
    "Tu réponds à l'objectif de l'utilisateur. Utilise les outils quand ils sont utiles, "
    "et ne devine pas un résultat qu'un outil peut donner."
)


@dataclass(frozen=True)
class EtapeAgent:
    modele: str
    appels: tuple[AppelOutil, ...]
    resultats: tuple[ResultatOutil, ...]


@dataclass(frozen=True)
class ResultatAgent:
    texte: str
    arret: Literal["termine", "limite_etapes"]
    etapes: tuple[EtapeAgent, ...]
    cout_nano: int


class Agent:
    def __init__(
        self,
        service: ServiceRoutage,
        outils: tuple[Outil, ...],
        max_etapes: int = 5,
        max_jetons: int = 2048,
    ) -> None:
        self._service = service
        self._outils = {outil.definition.nom: outil for outil in outils}
        self._max_etapes = max_etapes
        self._max_jetons = max_jetons

    def executer(self, objectif: str) -> ResultatAgent:
        messages: list[Message] = [MessageUtilisateur(objectif)]
        etapes: list[EtapeAgent] = []
        cout = 0
        definitions = tuple(outil.definition for outil in self._outils.values())
        for _ in range(self._max_etapes):
            resultat = self._service.executer(
                Demande(
                    tache="agent",
                    messages=tuple(messages),
                    max_jetons=self._max_jetons,
                    systeme=_CONSIGNE,
                    outils=definitions,
                )
            )
            cout += resultat.cout_nano
            reponse = resultat.reponse
            if not reponse.appels:
                etapes.append(EtapeAgent(resultat.modele.id, (), ()))
                return ResultatAgent(reponse.texte, "termine", tuple(etapes), cout)
            sorties = tuple(self._executer_outil(appel) for appel in reponse.appels)
            etapes.append(EtapeAgent(resultat.modele.id, reponse.appels, sorties))
            messages.append(
                MessageAssistant(
                    texte=reponse.texte,
                    appels=reponse.appels,
                    brut=reponse.brut,
                    fournisseur=resultat.modele.fournisseur,
                )
            )
            messages.append(MessageResultats(sorties))
        return ResultatAgent("", "limite_etapes", tuple(etapes), cout)

    def _executer_outil(self, appel: AppelOutil) -> ResultatOutil:
        outil = self._outils.get(appel.nom)
        if outil is None:
            return ResultatOutil(appel.id, appel.nom, "outil inconnu", est_erreur=True)
        try:
            return ResultatOutil(appel.id, appel.nom, outil.executer(appel.arguments))
        except ErreurOutil as erreur:
            return ResultatOutil(appel.id, appel.nom, str(erreur), est_erreur=True)
