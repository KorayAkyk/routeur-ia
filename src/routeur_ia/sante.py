"""État de santé des fournisseurs : un disjoncteur simple, en mémoire.

Après plusieurs appels perdus de suite, le fournisseur est écarté pendant un temps : on évite de
faire attendre chaque demande sur des reprises vouées à l'échec. À la fin de ce temps, un seul
nouvel échec suffit à l'écarter de nouveau.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from routeur_ia.config import ConfigPannes


@dataclass
class _Etat:
    echecs: int = 0
    en_panne_jusqua: float | None = None


class SanteFournisseurs:
    def __init__(self, config: ConfigPannes, horloge: Callable[[], float]) -> None:
        self._config = config
        self._horloge = horloge
        self._etats: dict[str, _Etat] = {}
        self._verrou = threading.Lock()

    def signaler_succes(self, nom: str) -> None:
        with self._verrou:
            self._etats[nom] = _Etat()

    def signaler_echec(self, nom: str) -> None:
        with self._verrou:
            etat = self._etats.setdefault(nom, _Etat())
            self._fermer_si_expire(etat)
            etat.echecs += 1
            if etat.echecs >= self._config.echecs_avant_panne:
                etat.en_panne_jusqua = self._horloge() + self._config.duree_panne_s

    def est_disponible(self, nom: str) -> bool:
        with self._verrou:
            etat = self._etats.get(nom)
            if etat is None:
                return True
            self._fermer_si_expire(etat)
            return etat.en_panne_jusqua is None

    def indisponibles(self, noms: frozenset[str]) -> frozenset[str]:
        return frozenset(nom for nom in noms if not self.est_disponible(nom))

    def reinitialiser(self, nom: str) -> None:
        self.signaler_succes(nom)

    def _fermer_si_expire(self, etat: _Etat) -> None:
        if etat.en_panne_jusqua is not None and self._horloge() >= etat.en_panne_jusqua:
            etat.en_panne_jusqua = None
            etat.echecs = self._config.echecs_avant_panne - 1
