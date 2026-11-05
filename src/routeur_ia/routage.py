"""Règles de routage : fonctions pures, appliquées dans l'ordre, chacune laissant une trace.

Aucun réseau, aucune horloge, aucune base : tout ce qui compte arrive en paramètre. On peut donc
tester chaque règle seule, et expliquer après coup pourquoi un modèle a été choisi.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

from routeur_ia.config import Config, Modele
from routeur_ia.couts import cout_entree_nano


class TacheInconnue(ValueError):
    """Le type de tâche demandé n'existe pas dans la configuration."""


@dataclass(frozen=True)
class EntreeRoutage:
    tache: str
    jetons_estimes: int


@dataclass(frozen=True)
class EtatRoutage:
    part_budget_restante: float
    fournisseurs_indisponibles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EtapeRoutage:
    regle: str
    effet: str


@dataclass(frozen=True)
class Decision:
    niveau: str
    candidats: tuple[Modele, ...]
    etapes: tuple[EtapeRoutage, ...]


@dataclass(frozen=True)
class _Brouillon:
    rang: int = 0
    candidats: tuple[Modele, ...] = ()
    etapes: tuple[EtapeRoutage, ...] = ()

    def note(self, regle: str, effet: str) -> "_Brouillon":
        return replace(self, etapes=(*self.etapes, EtapeRoutage(regle, effet)))


def _noms(config: Config) -> tuple[str, ...]:
    return tuple(niveau.nom for niveau in config.niveaux)


def regle_tache(entree: EntreeRoutage, _: EtatRoutage, config: Config, b: _Brouillon) -> _Brouillon:
    """Le type de tâche donne le niveau de départ."""
    niveau = config.routage.niveau_par_tache.get(entree.tache)
    if niveau is None:
        raise TacheInconnue(entree.tache)
    return replace(b, rang=_noms(config).index(niveau)).note(
        "tache", f"« {entree.tache} » : niveau {niveau}"
    )


def regle_longueur(
    entree: EntreeRoutage, _: EtatRoutage, config: Config, b: _Brouillon
) -> _Brouillon:
    """Une demande générale très courte descend ; un texte long ne reste pas au plus bas niveau."""
    seuils = config.routage
    if entree.tache == "general" and entree.jetons_estimes < seuils.seuil_court and b.rang > 0:
        niveau = _noms(config)[0]
        return replace(b, rang=0).note(
            "longueur", f"demande générale courte ({entree.jetons_estimes} jetons) : {niveau}"
        )
    if entree.jetons_estimes >= seuils.seuil_long and b.rang == 0 and len(config.niveaux) > 1:
        niveau = _noms(config)[1]
        return replace(b, rang=1).note(
            "longueur", f"texte long ({entree.jetons_estimes} jetons) : {niveau}"
        )
    return b.note("longueur", "sans effet")


def regle_budget(_: EntreeRoutage, etat: EtatRoutage, config: Config, b: _Brouillon) -> _Brouillon:
    """Moins il reste de budget, moins le modèle choisi coûte cher."""
    part = etat.part_budget_restante
    pourcentage = f"{part:.0%} de budget restant"
    if part < config.budget.seuil_critique:
        rang = 0
    elif part < config.budget.seuil_economie:
        rang = max(0, b.rang - 1)
    else:
        return b.note("budget", f"{pourcentage} : sans effet")
    if rang == b.rang:
        return b.note("budget", f"{pourcentage} : déjà au niveau autorisé")
    return replace(b, rang=rang).note("budget", f"{pourcentage} : niveau {_noms(config)[rang]}")


def regle_candidats(
    entree: EntreeRoutage, _: EtatRoutage, config: Config, b: _Brouillon
) -> _Brouillon:
    """Le niveau donne les candidats ; sur un texte très long, le moins cher en entrée d'abord."""
    niveau = config.niveaux[b.rang]
    candidats = tuple(config.modeles[id_modele] for id_modele in niveau.modeles)
    if entree.jetons_estimes < config.routage.seuil_tres_long:
        return replace(b, candidats=candidats).note("candidats", "ordre de la configuration")
    tries = tuple(sorted(candidats, key=lambda m: cout_entree_nano(m, entree.jetons_estimes)))
    return replace(b, candidats=tries).note(
        "candidats", f"texte très long : {tries[0].id} d'abord, moins cher en entrée"
    )


def regle_pannes(_: EntreeRoutage, etat: EtatRoutage, __: Config, b: _Brouillon) -> _Brouillon:
    """Un fournisseur en panne ou non configuré est écarté avant même d'essayer."""
    gardes = tuple(m for m in b.candidats if m.fournisseur not in etat.fournisseurs_indisponibles)
    ecartes = sorted({m.fournisseur for m in b.candidats} & etat.fournisseurs_indisponibles)
    if not ecartes:
        return replace(b, candidats=gardes).note("pannes", "sans effet")
    return replace(b, candidats=gardes).note("pannes", f"écartés : {', '.join(ecartes)}")


Regle = Callable[[EntreeRoutage, EtatRoutage, Config, _Brouillon], _Brouillon]

REGLES: tuple[Regle, ...] = (
    regle_tache,
    regle_longueur,
    regle_budget,
    regle_candidats,
    regle_pannes,
)


def decider(entree: EntreeRoutage, etat: EtatRoutage, config: Config) -> Decision:
    """Applique les règles dans l'ordre et renvoie la décision et sa trace."""
    brouillon = _Brouillon()
    for regle in REGLES:
        brouillon = regle(entree, etat, config, brouillon)
    return Decision(
        niveau=config.niveaux[brouillon.rang].nom,
        candidats=brouillon.candidats,
        etapes=brouillon.etapes,
    )
