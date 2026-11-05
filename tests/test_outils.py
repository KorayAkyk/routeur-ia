"""Outils de l'agent : ce qui est permis, et surtout ce qui ne l'est pas."""

import pytest

from routeur_ia.agent.outils import ErreurOutil, calculer, outils_par_defaut
from tests.aides import INSTANT


@pytest.mark.parametrize(
    ("expression", "attendu"),
    [
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("10 / 4", 2.5),
        ("10 // 4", 2),
        ("10 % 4", 2),
        ("2 ** 10", 1024),
        ("-3 + 5", 2),
        ("+7", 7),
        ("1.5 * 2", 3.0),
    ],
)
def test_calculs_valides(expression: str, attendu: float) -> None:
    assert calculer(expression) == attendu


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('true')",
        "open('/etc/passwd')",
        "().__class__",
        "abs(-1)",
        "[1, 2]",
        "'texte'",
        "True + 1",
        "1 if 1 else 2",
        "x + 1",
        "lambda: 1",
        "1 +",
        "",
        "1 / 0",
        "9 ** 9 ** 9",
        "2 ** 1000",
        "10000000 ** 2",
        "(-8) ** 0.5",
        "1" * 201,
    ],
)
def test_expressions_refusees(expression: str) -> None:
    with pytest.raises(ErreurOutil):
        calculer(expression)


def test_outil_calculer_verifie_son_argument() -> None:
    outil = outils_par_defaut(lambda: INSTANT)[0]
    assert outil.executer({"expression": "6 * 7"}) == "42"
    with pytest.raises(ErreurOutil):
        outil.executer({})
    with pytest.raises(ErreurOutil):
        outil.executer({"expression": 42})


def test_outil_date() -> None:
    outil = outils_par_defaut(lambda: INSTANT)[1]
    assert outil.executer({}) == "2026-03-15"
