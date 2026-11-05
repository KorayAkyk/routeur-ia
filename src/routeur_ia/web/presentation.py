"""Mise en forme des données du journal pour la page de suivi : calculs purs, sans Flask."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from routeur_ia.couts import nano_en_usd
from routeur_ia.journal import CoutJourModele

LARGEUR = 760
HAUTEUR = 260
MARGE_GAUCHE = 64
MARGE_BAS = 24
MARGE_HAUT = 8
ESPACE_SEGMENTS = 2
RAYON = 4


def usd_court(montant_nano: int) -> str:
    """Montant à la française, avec les décimales utiles : 0,0042 $ ou 1,25 $."""
    if montant_nano == 0:
        return "0 $"
    montant = nano_en_usd(montant_nano)
    decimales = 2 if abs(montant) >= 1 else 4 if abs(montant) >= Decimal("0.0001") else 6
    return f"{montant:.{decimales}f} $".replace(".", ",")


def usd_axe(montant_nano: int) -> str:
    """Graduation d'axe, sans zéro inutile : 0,25 $ plutôt que 0,2500 $."""
    if montant_nano == 0:
        return "0 $"
    return f"{format(nano_en_usd(montant_nano).normalize(), 'f')} $".replace(".", ",")


def entier(valeur: int) -> str:
    """Nombre entier à la française, milliers séparés par une espace insécable fine."""
    return f"{valeur:,}".replace(",", "\u202f")


@dataclass(frozen=True)
class Segment:
    modele: str
    serie: int
    chemin: str
    titre: str


@dataclass(frozen=True)
class Colonne:
    jour: date
    segments: tuple[Segment, ...]
    x_etiquette: float
    etiquette: str | None


@dataclass(frozen=True)
class Graduation:
    y: float
    texte: str


@dataclass(frozen=True)
class Graphique:
    largeur: int
    hauteur: int
    x_debut: int
    x_fin: int
    colonnes: tuple[Colonne, ...]
    graduations: tuple[Graduation, ...]


@dataclass(frozen=True)
class TotalModele:
    modele: str
    serie: int
    appels: int
    echecs: int
    jetons_entree: int
    jetons_sortie: int
    cout_nano: int


def echelle_ronde(maximum_nano: int) -> int:
    """Plus petit nombre de la forme 1, 2, 4 ou 8 x 10^k supérieur ou égal au maximum.

    Ces valeurs se divisent en quatre graduations rondes, sans laisser la moitié du cadre vide.
    """
    if maximum_nano <= 0:
        return 1
    puissance = 1
    while True:
        for facteur in (1, 2, 4, 8):
            if facteur * puissance >= maximum_nano:
                return facteur * puissance
        puissance *= 10


def construire_graphique(
    lignes: Sequence[CoutJourModele],
    debut: date,
    fin: date,
    series: dict[str, int],
) -> Graphique:
    """Colonnes empilées par jour et par modèle. Les jours sans appel gardent leur place."""
    nb_jours = (fin - debut).days + 1
    par_jour: dict[date, list[CoutJourModele]] = defaultdict(list)
    for ligne in lignes:
        par_jour[ligne.jour].append(ligne)
    totaux = [sum(ligne.cout_nano for ligne in par_jour[d]) for d in par_jour]
    echelle = echelle_ronde(max(totaux, default=0))

    x_fin = LARGEUR - 8
    bande = (x_fin - MARGE_GAUCHE) / nb_jours
    largeur_barre = max(2.0, bande * 0.7)
    hauteur_trace = HAUTEUR - MARGE_BAS - MARGE_HAUT
    pas_etiquettes = max(1, nb_jours // 7)

    colonnes = []
    for rang in range(nb_jours):
        jour = debut + timedelta(days=rang)
        x = MARGE_GAUCHE + rang * bande + (bande - largeur_barre) / 2
        segments = _segments(
            par_jour.get(jour, []), x, largeur_barre, echelle, hauteur_trace, series
        )
        etiquette = jour.strftime("%d/%m") if (nb_jours - 1 - rang) % pas_etiquettes == 0 else None
        colonnes.append(Colonne(jour, segments, x + largeur_barre / 2, etiquette))

    graduations = tuple(
        Graduation(
            y=MARGE_HAUT + hauteur_trace * (1 - quart / 4),
            texte=usd_axe(echelle * quart // 4),
        )
        for quart in range(5)
    )
    return Graphique(LARGEUR, HAUTEUR, MARGE_GAUCHE, x_fin, tuple(colonnes), graduations)


def _segments(
    lignes: Sequence[CoutJourModele],
    x: float,
    largeur: float,
    echelle: int,
    hauteur_trace: float,
    series: dict[str, int],
) -> tuple[Segment, ...]:
    y_bas = float(HAUTEUR - MARGE_BAS)
    visibles = [
        ligne
        for ligne in sorted(lignes, key=lambda ligne: series.get(ligne.modele, len(series)))
        if ligne.cout_nano > 0
    ]
    segments = []
    for rang, ligne in enumerate(visibles):
        hauteur = max(1.0, ligne.cout_nano / echelle * hauteur_trace)
        est_sommet = rang == len(visibles) - 1
        haut_visible = y_bas - hauteur
        rayon = min(RAYON, largeur / 2, hauteur) if est_sommet else 0.0
        segments.append(
            Segment(
                modele=ligne.modele,
                serie=series.get(ligne.modele, len(series)),
                chemin=_chemin(x, haut_visible, largeur, hauteur, rayon, rang > 0),
                titre=(
                    f"{ligne.jour:%d/%m} - {ligne.modele} : {usd_court(ligne.cout_nano)}, "
                    f"{ligne.appels} appels, {ligne.echecs} échecs"
                ),
            )
        )
        y_bas = haut_visible
    return tuple(segments)


def _chemin(x: float, y: float, large: float, h: float, r: float, espace_bas: bool) -> str:
    """Rectangle au sommet arrondi. L'espace laisse le fond visible entre deux segments."""
    bas = y + h - (ESPACE_SEGMENTS if espace_bas and h > ESPACE_SEGMENTS else 0)
    return (
        f"M{x:.1f} {bas:.1f}V{y + r:.1f}Q{x:.1f} {y:.1f} {x + r:.1f} {y:.1f}"
        f"H{x + large - r:.1f}Q{x + large:.1f} {y:.1f} {x + large:.1f} {y + r:.1f}V{bas:.1f}Z"
    )


def totaux_par_modele(
    lignes: Sequence[CoutJourModele], series: dict[str, int]
) -> tuple[TotalModele, ...]:
    cumul: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    for ligne in lignes:
        valeurs = cumul[ligne.modele]
        valeurs[0] += ligne.appels
        valeurs[1] += ligne.echecs
        valeurs[2] += ligne.jetons_entree
        valeurs[3] += ligne.jetons_sortie
        valeurs[4] += ligne.cout_nano
    totaux = [
        TotalModele(modele, series.get(modele, len(series)), *valeurs)
        for modele, valeurs in cumul.items()
    ]
    return tuple(sorted(totaux, key=lambda t: t.cout_nano, reverse=True))
