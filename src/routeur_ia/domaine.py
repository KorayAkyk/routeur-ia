"""Types communs à tous les fournisseurs : conversation, requête, réponse, erreurs."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

Arret = Literal["fin", "outils", "limite", "refus", "autre"]


@dataclass(frozen=True)
class AppelOutil:
    id: str
    nom: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ResultatOutil:
    id_appel: str
    nom: str
    contenu: str
    est_erreur: bool = False


@dataclass(frozen=True)
class DefinitionOutil:
    nom: str
    description: str
    schema: Mapping[str, object]


@dataclass(frozen=True)
class MessageUtilisateur:
    texte: str


@dataclass(frozen=True)
class MessageAssistant:
    """Tour du modèle. `brut` garde la réponse d'origine du fournisseur.

    Elle est renvoyée telle quelle au même fournisseur : Claude exige ses blocs de réflexion
    intacts et Gemini ses signatures, que le format commun ne sait pas représenter.
    """

    texte: str
    appels: tuple[AppelOutil, ...] = ()
    brut: object = None
    fournisseur: str | None = None


@dataclass(frozen=True)
class MessageResultats:
    resultats: tuple[ResultatOutil, ...]


Message = MessageUtilisateur | MessageAssistant | MessageResultats


@dataclass(frozen=True)
class RequeteModele:
    modele: str
    messages: tuple[Message, ...]
    max_jetons: int
    systeme: str | None = None
    outils: tuple[DefinitionOutil, ...] = ()
    effort: str | None = None


@dataclass(frozen=True)
class ReponseModele:
    texte: str
    jetons_entree: int
    jetons_sortie: int
    arret: Arret = "fin"
    appels: tuple[AppelOutil, ...] = field(default=())
    brut: object = None


class Fournisseur(Protocol):
    """Interface que chaque adaptateur de fournisseur implémente."""

    @property
    def nom(self) -> str: ...

    def generer(self, requete: RequeteModele) -> ReponseModele: ...


class ErreurFournisseur(Exception):
    """Échec d'un appel. `code` est court et sans donnée sensible : il va dans le journal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ErreurTransitoire(ErreurFournisseur):
    """Surcharge, délai, coupure réseau : une nouvelle tentative a des chances d'aboutir."""

    def __init__(self, code: str, attente_suggeree: float | None = None) -> None:
        super().__init__(code)
        self.attente_suggeree = attente_suggeree


class ErreurIndisponible(ErreurFournisseur):
    """Clé refusée, modèle absent : réessayer ne sert à rien, on passe au modèle suivant."""


class ErreurRequete(ErreurFournisseur):
    """La demande elle-même est invalide : ni nouvelle tentative, ni bascule."""
