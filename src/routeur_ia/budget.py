"""Budget plafond mensuel, avec réservation avant chaque appel.

Le coût réel n'est connu qu'après l'appel. Si plusieurs demandes vérifiaient le solde en même temps,
toutes passeraient et le plafond serait dépassé. Chaque appel réserve donc d'abord son coût maximal,
sous verrou, puis libère cette réservation une fois le coût réel écrit au journal.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class EtatBudget:
    plafond_nano: int
    depense_nano: int
    reserve_nano: int

    @property
    def restant_nano(self) -> int:
        return max(0, self.plafond_nano - self.depense_nano - self.reserve_nano)

    @property
    def part_restante(self) -> float:
        if self.plafond_nano == 0:
            return 0.0
        return self.restant_nano / self.plafond_nano


class Budget:
    def __init__(
        self,
        plafond_nano: int,
        depense_depuis: Callable[[date], int],
        horloge: Callable[[], datetime],
    ) -> None:
        self._plafond_nano = plafond_nano
        self._depense_depuis = depense_depuis
        self._horloge = horloge
        self._reserve_nano = 0
        self._verrou = threading.Lock()

    def etat(self) -> EtatBudget:
        with self._verrou:
            return self._etat()

    def reserver(self, montant_nano: int) -> bool:
        """Réserve le montant s'il tient dans le solde. Renvoie False sinon, sans rien changer."""
        with self._verrou:
            if montant_nano > self._etat().restant_nano:
                return False
            self._reserve_nano += montant_nano
            return True

    def liberer(self, montant_nano: int) -> None:
        with self._verrou:
            self._reserve_nano = max(0, self._reserve_nano - montant_nano)

    def _etat(self) -> EtatBudget:
        debut_du_mois = self._horloge().date().replace(day=1)
        return EtatBudget(
            plafond_nano=self._plafond_nano,
            depense_nano=self._depense_depuis(debut_du_mois),
            reserve_nano=self._reserve_nano,
        )
