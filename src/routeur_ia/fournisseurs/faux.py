"""Faux fournisseur : réponses déterministes, sans réseau et sans clé.

Il fait tourner le service, la page de suivi et les tests. On peut lui programmer une suite de
réponses ou d'erreurs, ou simuler une panne franche.
"""

import re
import threading
from collections import deque

from routeur_ia.couts import estimer_jetons
from routeur_ia.domaine import (
    AppelOutil,
    Arret,
    ErreurFournisseur,
    ErreurTransitoire,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ReponseModele,
    RequeteModele,
)

_EXPRESSION = re.compile(r"\d[\d\s.+\-*/()%]*[\d)]")


class FauxFournisseur:
    def __init__(self, nom: str) -> None:
        self._nom = nom
        self._script: deque[ReponseModele | ErreurFournisseur] = deque()
        self._verrou = threading.Lock()
        self._en_panne = False
        self.requetes: list[RequeteModele] = []

    @property
    def nom(self) -> str:
        return self._nom

    @property
    def en_panne(self) -> bool:
        return self._en_panne

    def programmer(self, *suite: ReponseModele | ErreurFournisseur) -> None:
        """Les prochains appels renverront ces réponses ou lèveront ces erreurs, dans l'ordre."""
        with self._verrou:
            self._script.extend(suite)

    def simuler_panne(self, active: bool = True) -> None:
        self._en_panne = active

    def generer(self, requete: RequeteModele) -> ReponseModele:
        with self._verrou:
            self.requetes.append(requete)
            prochain = self._script.popleft() if self._script else None
        if self._en_panne:
            raise ErreurTransitoire("panne_simulee")
        if isinstance(prochain, ErreurFournisseur):
            raise prochain
        if prochain is not None:
            return prochain
        return self._reponse_par_defaut(requete)

    def _reponse_par_defaut(self, requete: RequeteModele) -> ReponseModele:
        jetons_entree = sum(estimer_jetons(_texte(message)) for message in requete.messages)
        jetons_entree += estimer_jetons(requete.systeme or "")
        appel = _appel_outil_prevu(requete)
        if appel is not None:
            return self._repondre(requete, "", jetons_entree, "outils", (appel,))
        return self._repondre(requete, _texte_final(requete), jetons_entree, "fin", ())

    def _repondre(
        self,
        requete: RequeteModele,
        texte: str,
        jetons_entree: int,
        arret: Arret,
        appels: tuple[AppelOutil, ...],
    ) -> ReponseModele:
        jetons_sortie = min(requete.max_jetons, 40 + jetons_entree // 2)
        return ReponseModele(
            texte=texte,
            jetons_entree=jetons_entree,
            jetons_sortie=jetons_sortie,
            arret=arret,
            appels=appels,
            brut={"simule": True},
        )


def _texte(message: Message) -> str:
    match message:
        case MessageUtilisateur(texte=texte) | MessageAssistant(texte=texte):
            return texte
        case MessageResultats(resultats=resultats):
            return " ".join(resultat.contenu for resultat in resultats)


def _appel_outil_prevu(requete: RequeteModele) -> AppelOutil | None:
    """Imite un modèle qui appelle un outil une fois, si la question s'y prête."""
    if any(isinstance(message, MessageResultats) for message in requete.messages):
        return None
    disponibles = {outil.nom for outil in requete.outils}
    question = _texte(requete.messages[-1])
    expression = _EXPRESSION.search(question)
    if "calculer" in disponibles and expression:
        return AppelOutil("faux-1", "calculer", {"expression": expression.group().strip()})
    if "date_du_jour" in disponibles and "date" in question.lower():
        return AppelOutil("faux-1", "date_du_jour", {})
    return None


def _texte_final(requete: RequeteModele) -> str:
    derniers = [m for m in requete.messages if isinstance(m, MessageResultats)]
    if derniers:
        contenu = "; ".join(resultat.contenu for resultat in derniers[-1].resultats)
        return f"[réponse simulée par {requete.modele}] Résultat de l'outil : {contenu}"
    return f"[réponse simulée par {requete.modele}] Aucun vrai modèle n'a été appelé."
