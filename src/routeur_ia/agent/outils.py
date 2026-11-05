"""Outils de l'agent : aucun accès au réseau, aux fichiers ni au système.

`calculer` lit l'arbre syntaxique de l'expression et n'autorise que des nombres et des opérateurs.
Il n'y a pas de `eval` : une expression hostile est refusée avant toute exécution.
"""

import ast
import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from routeur_ia.domaine import DefinitionOutil

LONGUEUR_MAX_EXPRESSION = 200
EXPOSANT_MAX = 64
BASE_MAX = 1_000_000

Nombre = int | float

_BINAIRES: dict[type[ast.operator], Callable[[Nombre, Nombre], Nombre]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}


class ErreurOutil(ValueError):
    """Argument refusé par un outil. Le message est renvoyé au modèle pour qu'il corrige."""


@dataclass(frozen=True)
class Outil:
    definition: DefinitionOutil
    executer: Callable[[Mapping[str, object]], str]


def calculer(expression: str) -> Nombre:
    """Évalue une expression arithmétique. Lève `ErreurOutil` pour tout le reste."""
    if len(expression) > LONGUEUR_MAX_EXPRESSION:
        raise ErreurOutil("expression trop longue")
    try:
        arbre = ast.parse(expression, mode="eval")
        return _evaluer(arbre.body)
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError, MemoryError) as erreur:
        raise ErreurOutil(f"expression invalide : {type(erreur).__name__}") from erreur


def _evaluer(noeud: ast.expr) -> Nombre:
    match noeud:
        case ast.Constant(value=int() | float() as valeur) if not isinstance(valeur, bool):
            return valeur
        case ast.UnaryOp(op=ast.USub(), operand=operande):
            return -_evaluer(operande)
        case ast.UnaryOp(op=ast.UAdd(), operand=operande):
            return _evaluer(operande)
        case ast.BinOp(left=gauche, op=ast.Pow(), right=droite):
            return _puissance(_evaluer(gauche), _evaluer(droite))
        case ast.BinOp(left=gauche, op=op, right=droite) if type(op) in _BINAIRES:
            return _BINAIRES[type(op)](_evaluer(gauche), _evaluer(droite))
    raise ErreurOutil("seuls les nombres et les opérateurs + - * / // % ** sont acceptés")


def _puissance(base: Nombre, exposant: Nombre) -> Nombre:
    if abs(exposant) > EXPOSANT_MAX or abs(base) > BASE_MAX:
        raise ErreurOutil("puissance trop grande")
    resultat: Nombre = base**exposant
    if isinstance(resultat, complex):
        raise ErreurOutil("résultat hors des nombres réels")
    return resultat


def _outil_calculer(arguments: Mapping[str, object]) -> str:
    expression = arguments.get("expression")
    if not isinstance(expression, str):
        raise ErreurOutil("l'argument 'expression' doit être une chaîne")
    return str(calculer(expression))


def outils_par_defaut(horloge: Callable[[], datetime]) -> tuple[Outil, ...]:
    return (
        Outil(
            DefinitionOutil(
                nom="calculer",
                description="Calcule une expression arithmétique, par exemple (2 + 3) * 4.",
                schema={
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Expression à calculer"}
                    },
                    "required": ["expression"],
                },
            ),
            _outil_calculer,
        ),
        Outil(
            DefinitionOutil(
                nom="date_du_jour",
                description="Donne la date du jour au format AAAA-MM-JJ, en UTC.",
                schema={"type": "object", "properties": {}},
            ),
            lambda _: horloge().date().isoformat(),
        ),
    )
