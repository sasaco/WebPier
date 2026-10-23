"""Shared helpers for the 0500 杭基礎 tests: variants of tests/fixtures/inputs/pile.json (the SOIL-JR 5.2 sample, a 場所打ち杭
of 3 × 3 piles with the middle one left out, in six layers) and the layers as a sheet."""

import json
from copy import deepcopy
from pathlib import Path

from webpier.inputs import parse_input

PILE = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "pile.json").read_text(encoding="utf-8"))


def pile_document(**changes):
    """pile.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(PILE)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def pile_pier(**changes):
    return parse_input(pile_document(**changes))


def layer(name, thickness, soil="砂質土", n=10, phi=30.0, c=None, wet=18.0, submerged=8.0, ed=10000, de=None):
    return {"層番": name, "層厚": thickness, "土質区分": soil, "N値": n, "単位体積重量": {"湿潤": wet, "水中": submerged},
            "内部摩擦角_φd": phi, "内部摩擦角の上限値": None, "粘着力_c": c, "変形係数_Ed": ed, "De": de}


def layers(*rows):
    """The 地盤データ.層 of a variant."""
    return {"地盤データ/層": list(rows)}
