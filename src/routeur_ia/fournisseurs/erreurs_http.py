"""Classement commun des statuts HTTP renvoyés par les fournisseurs."""

from routeur_ia.domaine import (
    ErreurFournisseur,
    ErreurIndisponible,
    ErreurRequete,
    ErreurTransitoire,
)

_TRANSITOIRES = frozenset({408, 409, 425, 429})
_REQUETE_INVALIDE = frozenset({400, 413, 422})


def erreur_depuis_statut(statut: int, attente: float | None = None) -> ErreurFournisseur:
    """Traduit un statut HTTP. Le code ne contient que le statut, jamais le corps de la réponse."""
    code = f"http_{statut}"
    if statut in _TRANSITOIRES or statut >= 500:
        return ErreurTransitoire(code, attente)
    if statut in _REQUETE_INVALIDE:
        return ErreurRequete(code)
    return ErreurIndisponible(code)


def lire_retry_after(valeur: str | None) -> float | None:
    """Lit un en-tête `retry-after` exprimé en secondes. Toute autre forme est ignorée."""
    if valeur is None:
        return None
    try:
        secondes = float(valeur)
    except ValueError:
        return None
    return secondes if secondes >= 0 else None
