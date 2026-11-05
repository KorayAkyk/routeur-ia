"""Orchestration d'une demande : routage, réservation, reprises, bascule, journal."""

import random
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import partial

from routeur_ia.budget import Budget
from routeur_ia.config import Config, Modele
from routeur_ia.couts import cout_maximal_nano, cout_nano, estimer_jetons
from routeur_ia.domaine import (
    DefinitionOutil,
    ErreurFournisseur,
    ErreurRequete,
    Fournisseur,
    Message,
    MessageAssistant,
    MessageResultats,
    MessageUtilisateur,
    ReponseModele,
    RequeteModele,
)
from routeur_ia.journal import EntreeJournal, Journal, Statut
from routeur_ia.routage import Decision, EntreeRoutage, EtatRoutage, decider
from routeur_ia.sante import SanteFournisseurs
from routeur_ia.tentatives import PolitiqueReprise, executer_avec_reprises


@dataclass(frozen=True)
class Demande:
    tache: str
    messages: tuple[Message, ...]
    max_jetons: int
    systeme: str | None = None
    outils: tuple[DefinitionOutil, ...] = ()


@dataclass(frozen=True)
class Essai:
    modele: str
    numero: int
    statut: Statut
    code_erreur: str | None = None


@dataclass(frozen=True)
class Resultat:
    id_demande: str
    reponse: ReponseModele
    modele: Modele
    decision: Decision
    essais: tuple[Essai, ...]
    cout_nano: int

    @property
    def bascule(self) -> bool:
        return self.modele.id != self.decision.candidats[0].id


class BudgetEpuise(Exception):
    """Aucun candidat ne tient dans le budget restant. Aucun appel n'a été fait."""


class AucunFournisseur(Exception):
    """Tous les candidats ont échoué ou sont en panne."""

    def __init__(self, essais: tuple[Essai, ...] = ()) -> None:
        super().__init__("aucun fournisseur disponible")
        self.essais = essais


@dataclass(frozen=True)
class _Appel:
    """Contexte commun aux essais d'une même demande sur un même modèle."""

    id_demande: str
    demande: Demande
    decision: Decision
    modele: Modele
    requete: RequeteModele
    bascule: bool


class ServiceRoutage:
    def __init__(
        self,
        config: Config,
        fournisseurs: Mapping[str, Fournisseur],
        journal: Journal,
        budget: Budget,
        sante: SanteFournisseurs,
        horloge: Callable[[], datetime],
        dormir: Callable[[float], None] = time.sleep,
        alea: Callable[[], float] = random.random,
    ) -> None:
        self._config = config
        self._fournisseurs = fournisseurs
        self._journal = journal
        self._budget = budget
        self._sante = sante
        self._horloge = horloge
        self._dormir = dormir
        self._alea = alea
        tentatives = config.tentatives
        self._politique = PolitiqueReprise(
            max_essais=tentatives.max_essais,
            attente_initiale_s=tentatives.attente_initiale_s,
            facteur=tentatives.facteur,
            attente_max_s=tentatives.attente_max_s,
            gigue=tentatives.gigue,
        )

    def decider(self, tache: str, jetons_estimes: int) -> Decision:
        """Applique les règles de routage sans appeler aucun modèle."""
        configures = frozenset(self._fournisseurs)
        tous = frozenset(m.fournisseur for m in self._config.modeles.values())
        etat = EtatRoutage(
            part_budget_restante=self._budget.etat().part_restante,
            fournisseurs_indisponibles=(tous - configures) | self._sante.indisponibles(configures),
        )
        return decider(EntreeRoutage(tache, jetons_estimes), etat, self._config)

    def executer(self, demande: Demande) -> Resultat:
        """Essaie les candidats dans l'ordre jusqu'à obtenir une réponse exploitable."""
        jetons = _jetons_estimes(demande)
        decision = self.decider(demande.tache, jetons)
        id_demande = uuid.uuid4().hex
        essais: list[Essai] = []
        cout_total = 0
        dernier_refus: tuple[ReponseModele, Modele] | None = None
        hors_budget = 0

        for modele in decision.candidats:
            plafond = cout_maximal_nano(modele, jetons, demande.max_jetons)
            if not self._budget.reserver(plafond):
                hors_budget += 1
                continue
            appel = _Appel(
                id_demande=id_demande,
                demande=demande,
                decision=decision,
                modele=modele,
                requete=self._requete(demande, modele, decision),
                bascule=modele.id != decision.candidats[0].id,
            )
            try:
                reponse = executer_avec_reprises(
                    partial(self._essayer, appel, essais),
                    self._politique,
                    self._dormir,
                    self._alea,
                )
            except ErreurRequete:
                raise
            except ErreurFournisseur:
                self._sante.signaler_echec(modele.fournisseur)
                continue
            finally:
                self._budget.liberer(plafond)

            self._sante.signaler_succes(modele.fournisseur)
            cout_total += cout_nano(modele, reponse.jetons_entree, reponse.jetons_sortie)
            if reponse.arret == "refus":
                dernier_refus = (reponse, modele)
                continue
            return Resultat(id_demande, reponse, modele, decision, tuple(essais), cout_total)

        if dernier_refus is not None:
            reponse, modele = dernier_refus
            return Resultat(id_demande, reponse, modele, decision, tuple(essais), cout_total)
        if decision.candidats and hors_budget == len(decision.candidats):
            raise BudgetEpuise
        raise AucunFournisseur(tuple(essais))

    def _requete(self, demande: Demande, modele: Modele, decision: Decision) -> RequeteModele:
        return RequeteModele(
            modele=modele.id,
            messages=demande.messages,
            max_jetons=demande.max_jetons,
            systeme=demande.systeme,
            outils=demande.outils,
            effort=self._config.niveau(decision.niveau).effort,
        )

    def _essayer(self, appel: _Appel, essais: list[Essai], numero: int) -> ReponseModele:
        fournisseur = self._fournisseurs[appel.modele.fournisseur]
        debut = time.monotonic()
        try:
            reponse = fournisseur.generer(appel.requete)
        except ErreurFournisseur as erreur:
            self._noter(appel, numero, "erreur", erreur.code, None, debut, essais)
            raise
        statut: Statut = "refus" if reponse.arret == "refus" else "ok"
        self._noter(appel, numero, statut, None, reponse, debut, essais)
        return reponse

    def _noter(
        self,
        appel: _Appel,
        numero: int,
        statut: Statut,
        code_erreur: str | None,
        reponse: ReponseModele | None,
        debut: float,
        essais: list[Essai],
    ) -> None:
        entree = reponse.jetons_entree if reponse else 0
        sortie = reponse.jetons_sortie if reponse else 0
        self._journal.ajouter(
            EntreeJournal(
                horodatage=self._horloge(),
                id_demande=appel.id_demande,
                tache=appel.demande.tache,
                niveau=appel.decision.niveau,
                fournisseur=appel.modele.fournisseur,
                modele=appel.modele.id,
                essai=numero,
                bascule=appel.bascule,
                statut=statut,
                code_erreur=code_erreur,
                jetons_entree=entree,
                jetons_sortie=sortie,
                cout_nano=cout_nano(appel.modele, entree, sortie),
                duree_ms=round((time.monotonic() - debut) * 1000),
            )
        )
        essais.append(Essai(appel.modele.id, numero, statut, code_erreur))


def _jetons_estimes(demande: Demande) -> int:
    morceaux = [demande.systeme or ""]
    for message in demande.messages:
        match message:
            case MessageUtilisateur(texte=texte) | MessageAssistant(texte=texte):
                morceaux.append(texte)
            case MessageResultats(resultats=resultats):
                morceaux.extend(resultat.contenu for resultat in resultats)
    return sum(estimer_jetons(morceau) for morceau in morceaux)
