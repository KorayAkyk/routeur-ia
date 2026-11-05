"""Validation des corps JSON reçus par l'API."""

from pydantic import BaseModel, ConfigDict, Field

LONGUEUR_MAX_MESSAGE = 400_000
LONGUEUR_MAX_SYSTEME = 20_000
MAX_JETONS_PLAFOND = 16_000


class _Corps(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpsDemande(_Corps):
    tache: str = Field(default="general", max_length=64)
    message: str = Field(min_length=1, max_length=LONGUEUR_MAX_MESSAGE)
    systeme: str | None = Field(default=None, max_length=LONGUEUR_MAX_SYSTEME)
    max_jetons: int = Field(default=1024, ge=1, le=MAX_JETONS_PLAFOND)


class CorpsSimulation(_Corps):
    tache: str = Field(default="general", max_length=64)
    message: str = Field(min_length=1, max_length=LONGUEUR_MAX_MESSAGE)


class CorpsAgent(_Corps):
    objectif: str = Field(min_length=1, max_length=4_000)


class CorpsPanne(_Corps):
    fournisseur: str = Field(max_length=64)
    active: bool
