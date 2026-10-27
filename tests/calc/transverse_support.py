"""Shared helpers for the 0620 tests: Example2 09 lookups, the calculation chain and hand rounding."""

import json

from reaction_support import FIXTURES, D, pier, q
from webpier.calc.foundation import calculate_foundation
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse

T09 = json.loads((FIXTURES / "example2" / "transverse.json").read_text(encoding="utf-8"))
SECTIONS = {section["key"]: section for section in T09["sections"]}
DIMS = {"B": "下部構造/寸法/側面/", "W": "下部構造/寸法/正面/", "H": "下部構造/寸法/高さ/"}
DF1, DF2 = "下部構造/土かぶり/起点側_df1", "下部構造/土かぶり/終点側_df2"
# Example2 8-28 / 9-12: Df − H6 = 1.080, so the ground is 1.080 above the footing top (current.json has 2.000).
EXAMPLE2_GROUND = {DF1: 1.08, DF2: 1.08}
# Example2 row keys of the bearing tables, by (side, input slot).
BEARING_KEYS = {("origin", 0): "RB_G1", ("origin", 1): "RB_G2", ("origin", 2): "RB_G3", ("origin", 3): "RB_G4",
                ("end", 0): "RC_G1", ("end", 1): "RC_G2"}


def dims(**sizes):
    return {DIMS[key[0]] + key: size for key, size in sizes.items()}


def chain(p=None):
    """0500, 0600 and 0620 for one input; returns (pier, reaction, result)."""
    p = p or pier()
    reaction = calculate_reaction(p)
    return p, reaction, calculate_transverse(p, calculate_foundation(p), reaction)


def transverse(p=None):
    return chain(p)[2]


def items(section):
    return {item["key"]: item for item in SECTIONS[section]["items"] if "value" in item}


def table(section, key=None):
    """{row key: [cell values]} of a printed table; None for a '-' cell."""
    tables = SECTIONS[section]["tables"]
    chosen = tables[0] if key is None else next(t for t in tables if t["key"] == key)
    return {row["key"]: [None if cell is None else cell["value"] for cell in row["cells"]] for row in chosen["rows"]}


def diagram(case):
    """Printed values of one load diagram case (9-9 to 9-12), by key."""
    found = next(c for c in SECTIONS["load_diagrams"]["cases"] if c["case"] == case)
    return {item["key"]: item["value"] for item in found["items"]}


def key(row):
    return BEARING_KEYS[(row.item.value, row.slot)]


def product(a, b, digits=2):
    """a × b from the printed operands, rounded half away from zero."""
    return q(D(a) * D(b), digits)


def points(action):
    """{node: (N, H, M)} of the point loads of one action; a node carries at most one point."""
    found = {}
    for point in action.points:
        assert point.node not in found
        found[point.node] = (point.n.value, point.h.value, point.m.value)
    return found


# Example2's 9-14 (H16) makes each check with the train for one loading only and has one vehicle lateral load; WebPier
# makes both loadings with the vehicle lateral load of two tracks in 複線 (decision 106).
def _example2_loadings():
    from webpier.calc.transverse import Check, Loading  # noqa: PLC0415

    double, single = Loading.DOUBLE, Loading.SINGLE
    return {Check.FAILURE_TRAIN_MAX: double, Check.FAILURE_LATERAL_MAX: double, Check.CRACK_PERMANENT_VARIABLE: double,
            Check.CRACK_VARIABLE: single, Check.DAMAGE_TRAIN_MAX: double, Check.STABILITY_TRAIN_MAX: double,
            Check.STABILITY_LATERAL_MAX: double, Check.SUPPORT_SHORT_TERM_LOW_WATER: single,
            Check.SUPPORT_SHORT_TERM_HIGH_WATER: single}


def example2_combinations(result):
    """The combinations Example2's 9-14 prints, in its order (its Nos 1-16)."""
    loadings = _example2_loadings()
    return [c for c in result.combinations if c.loading is None or c.loading is loadings[c.check]]


def by_define(result, combination):
    """{Define: coefficient} of *combination*."""
    return dict(zip((d.define for d in result.define_cases), combination.coefficients, strict=True))


def example2_coefficients(result, combination):
    """*combination*'s coefficients by Example2's Define cases: the vehicle lateral load of two tracks in the column of
    Example2's one."""
    from webpier.calc.transverse import Define  # noqa: PLC0415

    found = by_define(result, combination)
    if found.get(Define.LATERAL_DOUBLE) is not None:
        found[Define.LATERAL] = found[Define.LATERAL_DOUBLE]
    return [coefficient for define, coefficient in found.items() if define is not Define.LATERAL_DOUBLE]


def example2_case(case):
    """Example2's number of a basic case: those after the vehicle lateral load of two tracks are one less."""
    from webpier.calc.transverse import BasicCase  # noqa: PLC0415

    return case.value - (case.value > BasicCase.LATERAL_DOUBLE.value)
