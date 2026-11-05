"""Assemblage de l'application : c'est ici, et seulement ici, que les pièces se rencontrent."""

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from routeur_ia.agent.boucle import Agent
from routeur_ia.agent.outils import outils_par_defaut
from routeur_ia.budget import Budget
from routeur_ia.config import CHEMIN_PAR_DEFAUT, Config, charger_config
from routeur_ia.couts import usd_en_nano
from routeur_ia.domaine import Fournisseur
from routeur_ia.fournisseurs.fabrique import MODE_FAUX, creer_fournisseurs, lire_mode
from routeur_ia.journal import Journal
from routeur_ia.sante import SanteFournisseurs
from routeur_ia.service import ServiceRoutage

BASE_PAR_DEFAUT = Path("donnees/journal.sqlite")


def maintenant_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Application:
    config: Config
    mode: str
    fournisseurs: Mapping[str, Fournisseur]
    journal: Journal
    budget: Budget
    sante: SanteFournisseurs
    service: ServiceRoutage
    agent: Agent
    jeton_api: str | None
    horloge: Callable[[], datetime]

    @property
    def mode_faux(self) -> bool:
        return self.mode == MODE_FAUX


def assembler(
    config: Config,
    fournisseurs: Mapping[str, Fournisseur],
    chemin_base: Path,
    mode: str = MODE_FAUX,
    jeton_api: str | None = None,
    horloge: Callable[[], datetime] = maintenant_utc,
    dormir: Callable[[float], None] = time.sleep,
    horloge_sante: Callable[[], float] = time.monotonic,
) -> Application:
    """Relie les composants. Horloges et attente sont injectées pour rester testables."""
    journal = Journal(chemin_base)
    budget = Budget(usd_en_nano(config.budget.plafond_mensuel_usd), journal.depense_depuis, horloge)
    sante = SanteFournisseurs(config.pannes, horloge_sante)
    service = ServiceRoutage(config, fournisseurs, journal, budget, sante, horloge, dormir)
    agent = Agent(service, outils_par_defaut(horloge))
    return Application(
        config=config,
        mode=mode,
        fournisseurs=fournisseurs,
        journal=journal,
        budget=budget,
        sante=sante,
        service=service,
        agent=agent,
        jeton_api=jeton_api,
        horloge=horloge,
    )


def depuis_environnement(env: Mapping[str, str] | None = None) -> Application:
    """Construit l'application depuis les variables d'environnement."""
    env = os.environ if env is None else env
    config = charger_config(Path(env.get("ROUTEUR_CONFIG") or CHEMIN_PAR_DEFAUT))
    return assembler(
        config=config,
        fournisseurs=creer_fournisseurs(config, env),
        chemin_base=Path(env.get("ROUTEUR_BASE") or BASE_PAR_DEFAUT),
        mode=lire_mode(env),
        jeton_api=env.get("ROUTEUR_JETON_API") or None,
    )
