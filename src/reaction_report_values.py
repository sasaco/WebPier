"""Resolve display-only worksheet references without changing calculation results.

The calculator's cells remain authoritative. This small, restricted expression
reader fills the repeated substitutions and captions of the reference report;
it does not run Python eval or open the source workbook.
"""

from __future__ import annotations

import ast
from functools import lru_cache
import json
import math
import operator
from pathlib import Path
import re
from typing import Any

from .reaction_math import excel_round


_TOKEN = re.compile(
    r'"(?:""|[^"])*"|(?:\'[^\']+\'|[\w]+)!\$?[A-Z]+\$?\d+'
    r'|\$?[A-Z]+\$?\d+|(?:\d+(?:\.\d*)?|\.\d+)(?:E[+-]?\d+)?'
    r'|[A-Z]+|<>|<=|>=|[+*/^(),:<>=$-]'
)
_REFERENCE = re.compile(r"(?:(.+)!)?(\$?[A-Z]+\$?\d+)$")
_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow,
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}


@lru_cache(maxsize=1)
def load_content() -> dict[str, Any]:
    """Load the pure value/formula/number-format contract, without page geometry."""
    path = Path(__file__).parent / "reporting/reaction_content.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _reference(token: str, sheet: str) -> tuple[str, str]:
    match = _REFERENCE.fullmatch(token)
    if not match:
        raise ValueError(f"0600帳票の参照式が不正: {token}")
    return (match[1].strip("'") if match[1] else sheet, match[2].replace("$", ""))


@lru_cache(maxsize=2048)
def _expression(formula: str, sheet: str) -> ast.Expression:
    """Translate only the Excel tokens used by the bundled 0600 display cells."""
    body = formula.removeprefix("=")
    tokens = []
    cursor = 0
    while cursor < len(body):
        if body[cursor].isspace():
            cursor += 1
            continue
        match = _TOKEN.match(body, cursor)
        if not match:
            raise ValueError(f"0600帳票に未対応の表示式: {formula}")
        tokens.append(match[0])
        cursor = match.end()
    converted = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith('"'):
            converted.append(repr(token[1:-1].replace('""', '"')))
        elif _REFERENCE.fullmatch(token):
            ref_sheet, address = _reference(token, sheet)
            if index + 2 < len(tokens) and tokens[index + 1] == ":":
                end_sheet, end_address = _reference(tokens[index + 2], ref_sheet)
                if end_sheet != ref_sheet:
                    raise ValueError("0600帳票は同一シート内の範囲だけを参照します")
                converted.append(f"RANGE({ref_sheet!r},{address!r},{end_address!r})")
                index += 2
            else:
                converted.append(f"CELL({ref_sheet!r},{address!r})")
        else:
            converted.append({"^": "**", "=": "==", "<>": "!="}.get(token, token))
        index += 1
    return ast.parse("".join(converted), mode="eval")


def _coordinate(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", address)
    if not match:
        raise ValueError(f"0600帳票のセル番地が不正: {address}")
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - ord("A") + 1
    return column, int(match[2])


def _address(column: int, row: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"{letters}{row}"


class _DisplayCells:
    def __init__(self, values: dict, formulas: dict) -> None:
        self.values = values
        self.formulas = formulas
        self.active: set[tuple[str, str]] = set()

    def cell(self, sheet: str, address: str) -> Any:
        values = self.values.setdefault(sheet, {})
        if address in values:
            return values[address] if values[address] is not None else 0
        formula = self.formulas.get(sheet, {}).get(address)
        if formula is None:
            return 0  # Unoccupied cells in merged ranges are empty in Excel.
        key = (sheet, address)
        if key in self.active:
            raise ValueError(f"0600帳票の表示式が循環参照: {sheet}!{address}")
        self.active.add(key)
        try:
            value = self.evaluate(_expression(formula, sheet).body)
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise ValueError(f"0600帳票の表示式を解決できません: {sheet}!{address} {formula}") from exc
        finally:
            self.active.remove(key)
        values[address] = value
        return value

    def evaluate(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](self.evaluate(node.left), self.evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = self.evaluate(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _OPERATORS:
            return _OPERATORS[type(node.ops[0])](self.evaluate(node.left), self.evaluate(node.comparators[0]))
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.keywords:
            raise ValueError("0600帳票に未対応の表示式構文です")
        name = node.func.id
        if name == "IF" and len(node.args) == 3:
            return self.evaluate(node.args[1] if self.evaluate(node.args[0]) else node.args[2])
        args = [self.evaluate(arg) for arg in node.args]
        if name == "CELL" and len(args) == 2:
            return self.cell(*args)
        if name == "RANGE" and len(args) == 3:
            sheet, first, last = args
            left, top = _coordinate(first)
            right, bottom = _coordinate(last)
            return [self.cell(sheet, _address(col, row)) for row in range(top, bottom + 1)
                    for col in range(left, right + 1)]
        flat = [item for arg in args for item in (arg if isinstance(arg, list) else [arg])]
        numeric = [item for item in flat if isinstance(item, (int, float))]
        if name == "SUM":
            total = 0.0
            for item in numeric:
                total += item
            return total
        if name in ("MAX", "MIN"):
            return (max if name == "MAX" else min)(numeric, default=0)
        if name == "AND":
            return all(flat)
        if name == "ROUND" and len(args) == 2:
            return excel_round(args[0], int(args[1]))
        if name == "ABS" and len(args) == 1:
            return abs(args[0])
        if name == "SQRT" and len(args) == 1:
            return math.sqrt(args[0])
        raise ValueError(f"0600帳票に未対応の表示関数: {name}")


def build_display_values(result: dict) -> dict[str, dict[str, Any]]:
    """Copy authoritative results and resolve the reference's display cells."""
    layout = load_content()
    values = {sheet: dict(cells) for sheet, cells in layout["constants"].items()}
    inputs = result["input"]
    values["列車荷重"].update(dict(zip(("AC34", "AC36", "AC38", "AC40"), result["moving_train"]["reactions"])))
    values["線路荷重"].update(N4=inputs["spans"]["b"]["bearing"], N5=inputs["spans"]["c"]["bearing"])
    values["直角荷重"].update(K10=inputs["train"]["height_wind"],
                               K11=inputs["train"]["height_centrifugal"],
                               K12=inputs["train"]["height_seismic"])
    for sheet, cells in result["cells"].items():
        values.setdefault(sheet, {}).update(cells)
    resolver = _DisplayCells(values, layout["formulas"])
    for sheet, formulas in layout["formulas"].items():
        for address in formulas:
            resolver.cell(sheet, address)
    return values
