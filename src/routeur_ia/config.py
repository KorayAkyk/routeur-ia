"""Lecture et validation du fichier de configuration TOML."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

CHEMIN_PAR_DEFAUT = Path(__file__).resolve().parents[2] / "config" / "routeur.toml"


class ConfigInvalide(ValueError):
    """Le fichier de configuration est incohérent."""


@dataclass(frozen=True)
class Modele:
    id: str
    fournisseur: str
    prix_entree: Decimal
    prix_sortie: Decimal
    palier_jetons: int | None = None
    prix_entree_palier: Decimal | None = None
    prix_sortie_palier: Decimal | None = None


@dataclass(frozen=True)
class Niveau:
    nom: str
    modeles: tuple[str, ...]
    effort: str | None = None


@dataclass(frozen=True)
class ConfigBudget:
    plafond_mensuel_usd: Decimal
    seuil_economie: float
    seuil_critique: float


@dataclass(frozen=True)
class ConfigTentatives:
    max_essais: int
    attente_initiale_s: float
    facteur: float
    attente_max_s: float
    gigue: float
    delai_appel_s: float


@dataclass(frozen=True)
class ConfigPannes:
    echecs_avant_panne: int
    duree_panne_s: float


@dataclass(frozen=True)
class ConfigRoutage:
    seuil_court: int
    seuil_long: int
    seuil_tres_long: int
    niveau_par_tache: Mapping[str, str]


@dataclass(frozen=True)
class Config:
    budget: ConfigBudget
    tentatives: ConfigTentatives
    pannes: ConfigPannes
    routage: ConfigRoutage
    niveaux: tuple[Niveau, ...]
    modeles: Mapping[str, Modele]

    def niveau(self, nom: str) -> Niveau:
        for niveau in self.niveaux:
            if niveau.nom == nom:
                return niveau
        raise KeyError(nom)


def charger_config(chemin: Path = CHEMIN_PAR_DEFAUT) -> Config:
    """Lit un fichier TOML et renvoie une configuration validée."""
    with chemin.open("rb") as fichier:
        return lire_config(tomllib.load(fichier))


def lire_config(brut: Mapping[str, Any]) -> Config:
    """Construit la configuration depuis un dictionnaire déjà décodé."""
    try:
        config = _construire(brut)
    except (KeyError, TypeError, ArithmeticError) as erreur:
        raise ConfigInvalide(f"configuration incomplète ou mal typée : {erreur!r}") from erreur
    _valider(config)
    return config


def _construire(brut: Mapping[str, Any]) -> Config:
    budget = brut["budget"]
    routage = brut["routage"]
    return Config(
        budget=ConfigBudget(
            plafond_mensuel_usd=_decimal(budget["plafond_mensuel_usd"]),
            seuil_economie=float(budget["seuil_economie"]),
            seuil_critique=float(budget["seuil_critique"]),
        ),
        tentatives=ConfigTentatives(**brut["tentatives"]),
        pannes=ConfigPannes(**brut["pannes"]),
        routage=ConfigRoutage(
            seuil_court=int(routage["seuil_court"]),
            seuil_long=int(routage["seuil_long"]),
            seuil_tres_long=int(routage["seuil_tres_long"]),
            niveau_par_tache=dict(routage["niveau_par_tache"]),
        ),
        niveaux=tuple(
            Niveau(nom=n["nom"], modeles=tuple(n["modeles"]), effort=n.get("effort"))
            for n in brut["niveaux"]
        ),
        modeles={m["id"]: _lire_modele(m) for m in brut["modeles"]},
    )


def _lire_modele(brut: Mapping[str, Any]) -> Modele:
    return Modele(
        id=brut["id"],
        fournisseur=brut["fournisseur"],
        prix_entree=_decimal(brut["prix_entree"]),
        prix_sortie=_decimal(brut["prix_sortie"]),
        palier_jetons=brut.get("palier_jetons"),
        prix_entree_palier=_decimal_optionnel(brut.get("prix_entree_palier")),
        prix_sortie_palier=_decimal_optionnel(brut.get("prix_sortie_palier")),
    )


def _decimal(valeur: object) -> Decimal:
    if not isinstance(valeur, str):
        raise TypeError(f"montant attendu en chaîne, pour rester exact : {valeur!r}")
    return Decimal(valeur)


def _decimal_optionnel(valeur: object) -> Decimal | None:
    return None if valeur is None else _decimal(valeur)


def _valider(config: Config) -> None:
    if not config.niveaux:
        raise ConfigInvalide("au moins un niveau est requis")
    noms = {niveau.nom for niveau in config.niveaux}
    for tache, niveau in config.routage.niveau_par_tache.items():
        if niveau not in noms:
            raise ConfigInvalide(f"tâche {tache!r} : niveau inconnu {niveau!r}")
    if "general" not in config.routage.niveau_par_tache:
        raise ConfigInvalide("la tâche 'general' est requise")
    for niveau_config in config.niveaux:
        if not niveau_config.modeles:
            raise ConfigInvalide(f"niveau {niveau_config.nom!r} sans modèle")
        for id_modele in niveau_config.modeles:
            if id_modele not in config.modeles:
                raise ConfigInvalide(f"niveau {niveau_config.nom!r} : modèle inconnu {id_modele!r}")
    for modele in config.modeles.values():
        _valider_modele(modele)
    _valider_seuils(config)


def _valider_modele(modele: Modele) -> None:
    if modele.prix_entree < 0 or modele.prix_sortie < 0:
        raise ConfigInvalide(f"modèle {modele.id!r} : prix négatif")
    champs = (modele.palier_jetons, modele.prix_entree_palier, modele.prix_sortie_palier)
    if any(champ is not None for champ in champs) and any(champ is None for champ in champs):
        raise ConfigInvalide(f"modèle {modele.id!r} : palier de prix incomplet")


def _valider_seuils(config: Config) -> None:
    budget = config.budget
    if budget.plafond_mensuel_usd < 0:
        raise ConfigInvalide("plafond de budget négatif")
    if not 0 <= budget.seuil_critique <= budget.seuil_economie <= 1:
        raise ConfigInvalide("seuils de budget : 0 <= critique <= économie <= 1 attendu")
    routage = config.routage
    if not 0 <= routage.seuil_court <= routage.seuil_long <= routage.seuil_tres_long:
        raise ConfigInvalide("seuils de longueur : court <= long <= très long attendu")
    if config.tentatives.max_essais < 1:
        raise ConfigInvalide("au moins un essai est requis")
    if config.pannes.echecs_avant_panne < 1:
        raise ConfigInvalide("echecs_avant_panne doit valoir au moins 1")
