"""Journal des appels en SQLite : une ligne par essai, jetons et coût en nano-dollars.

Le contenu des demandes et des réponses n'est jamais enregistré : le journal sert à suivre les
coûts, il n'a pas à conserver des données d'utilisateurs.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

Statut = Literal["ok", "erreur", "refus"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS appels (
    id INTEGER PRIMARY KEY,
    horodatage TEXT NOT NULL,
    jour TEXT NOT NULL,
    id_demande TEXT NOT NULL,
    tache TEXT NOT NULL,
    niveau TEXT NOT NULL,
    fournisseur TEXT NOT NULL,
    modele TEXT NOT NULL,
    essai INTEGER NOT NULL,
    bascule INTEGER NOT NULL,
    statut TEXT NOT NULL,
    code_erreur TEXT,
    jetons_entree INTEGER NOT NULL,
    jetons_sortie INTEGER NOT NULL,
    cout_nano INTEGER NOT NULL,
    duree_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS appels_jour ON appels (jour);
"""


@dataclass(frozen=True)
class EntreeJournal:
    horodatage: datetime
    id_demande: str
    tache: str
    niveau: str
    fournisseur: str
    modele: str
    essai: int
    bascule: bool
    statut: Statut
    code_erreur: str | None
    jetons_entree: int
    jetons_sortie: int
    cout_nano: int
    duree_ms: int


@dataclass(frozen=True)
class CoutJourModele:
    jour: date
    modele: str
    appels: int
    echecs: int
    jetons_entree: int
    jetons_sortie: int
    cout_nano: int


class Journal:
    """Une connexion par opération : simple, et sûr quand plusieurs fils écrivent."""

    def __init__(self, chemin: Path) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._chemin = chemin
        with self._connexion() as base:
            base.execute("PRAGMA journal_mode=WAL")
            base.executescript(_SCHEMA)

    def ajouter(self, entree: EntreeJournal) -> None:
        with self._connexion() as base:
            base.execute(
                """INSERT INTO appels (horodatage, jour, id_demande, tache, niveau, fournisseur,
                modele, essai, bascule, statut, code_erreur, jetons_entree, jetons_sortie,
                cout_nano, duree_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entree.horodatage.isoformat(),
                    entree.horodatage.date().isoformat(),
                    entree.id_demande,
                    entree.tache,
                    entree.niveau,
                    entree.fournisseur,
                    entree.modele,
                    entree.essai,
                    int(entree.bascule),
                    entree.statut,
                    entree.code_erreur,
                    entree.jetons_entree,
                    entree.jetons_sortie,
                    entree.cout_nano,
                    entree.duree_ms,
                ),
            )

    def depense_depuis(self, jour: date) -> int:
        """Somme des coûts, en nano-dollars, à partir du jour donné inclus."""
        with self._connexion() as base:
            ligne = base.execute(
                "SELECT COALESCE(SUM(cout_nano), 0) FROM appels WHERE jour >= ?",
                (jour.isoformat(),),
            ).fetchone()
        return int(ligne[0])

    def couts_par_jour_et_modele(self, depuis: date) -> list[CoutJourModele]:
        with self._connexion() as base:
            lignes = base.execute(
                """SELECT jour, modele, COUNT(*), SUM(statut = 'erreur'), SUM(jetons_entree),
                SUM(jetons_sortie), SUM(cout_nano) FROM appels WHERE jour >= ?
                GROUP BY jour, modele ORDER BY jour, modele""",
                (depuis.isoformat(),),
            ).fetchall()
        return [
            CoutJourModele(
                jour=date.fromisoformat(ligne[0]),
                modele=ligne[1],
                appels=ligne[2],
                echecs=ligne[3],
                jetons_entree=ligne[4],
                jetons_sortie=ligne[5],
                cout_nano=ligne[6],
            )
            for ligne in lignes
        ]

    def derniers_appels(self, limite: int = 20) -> list[EntreeJournal]:
        with self._connexion() as base:
            lignes = base.execute(
                """SELECT horodatage, id_demande, tache, niveau, fournisseur, modele, essai,
                bascule, statut, code_erreur, jetons_entree, jetons_sortie, cout_nano, duree_ms
                FROM appels ORDER BY id DESC LIMIT ?""",
                (limite,),
            ).fetchall()
        return [
            EntreeJournal(
                horodatage=datetime.fromisoformat(ligne[0]),
                id_demande=ligne[1],
                tache=ligne[2],
                niveau=ligne[3],
                fournisseur=ligne[4],
                modele=ligne[5],
                essai=ligne[6],
                bascule=bool(ligne[7]),
                statut=ligne[8],
                code_erreur=ligne[9],
                jetons_entree=ligne[10],
                jetons_sortie=ligne[11],
                cout_nano=ligne[12],
                duree_ms=ligne[13],
            )
            for ligne in lignes
        ]

    @contextmanager
    def _connexion(self) -> Iterator[sqlite3.Connection]:
        base = sqlite3.connect(self._chemin, timeout=10)
        try:
            with base:
                yield base
        finally:
            base.close()
