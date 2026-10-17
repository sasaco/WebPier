"""Shared helpers for the JRSNAP export tests: input variants, the 0710 / 0720 chains and the Example2 NDU files.

``EXAMPLE2_LONGITUDINAL`` / ``EXAMPLE2_TRANSVERSE`` are the NDU files of Example2 as JRSNAP saved them
(.claude/docs/Example橋脚2/10_線路(耐震)/線路方向_朝里川温泉P1.ndu, 11_直角(耐震)/直角方向_朝里川温泉P1.ndu, version
5.1.10). Their section, reinforcement, springs, analysis settings and load titles are expected values; values
that differ for a documented reason are listed in each test. They are read here by a plain key=value split,
independent of the writer and the validator.
"""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

from webpier.calc.column_rebar import column_layout
from webpier.calc.embedment import calculate_embedment
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.calc.transverse import calculate_transverse
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, build_ndu
from webpier.inputs import parse_input

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
EXAMPLE2_DIR = ROOT / ".claude" / "docs" / "Example橋脚2"
EXAMPLE2_FILES = {"longitudinal": EXAMPLE2_DIR / "10_線路(耐震)" / "線路方向_朝里川温泉P1.ndu",
                  "transverse": EXAMPLE2_DIR / "11_直角(耐震)" / "直角方向_朝里川温泉P1.ndu"}

DIMS = {"B": "下部構造/寸法/側面/", "W": "下部構造/寸法/正面/", "H": "下部構造/寸法/高さ/"}
PEDESTAL = {DIMS["B"] + "B2": 0.5, DIMS["B"] + "B3": 1.0, DIMS["W"] + "W2": 1.0, DIMS["W"] + "W3": 7.0,
            DIMS["H"] + "H1": 0.3}
ROW0, ROW1 = "鉄筋/柱/main_rows/0", "鉄筋/柱/main_rows/1"


def example2(direction):
    """{key: [fields]} of an Example2 NDU, in file order (continuation lines of CHOKU_KISO are skipped)."""
    records = {}
    for line in EXAMPLE2_FILES[direction].read_bytes().decode("cp932").split("\r\n"):
        if "=" in line and not line.startswith(" "):
            key, body = line.split("=", 1)
            records[key] = body.split(",")
    return records


def document(**changes):
    """current.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def results(direction, data=None):
    """(pier, foundation, embedment, layout, seismic result) of one direction for a document."""
    p = parse_input(data if data is not None else document())
    foundation = calculate_foundation(p)
    reaction = calculate_reaction(p)
    if direction == "longitudinal":
        seismic = calculate_seismic_longitudinal(p, foundation, reaction,
                                                 calculate_longitudinal(p, foundation, reaction))
    else:
        seismic = calculate_seismic_transverse(p, foundation, reaction, calculate_transverse(p, foundation, reaction))
    return p, foundation, calculate_embedment(p, foundation), column_layout(p), seismic


PROFILES = {"longitudinal": LONGITUDINAL, "transverse": TRANSVERSE}


def model(direction, data=None, **changes):
    p, foundation, embedment, layout, seismic = results(direction, data if data is not None else document(**changes))
    return build_ndu(PROFILES[direction], p, foundation, embedment, layout, seismic)


def D(value):
    """The decimal a person reads from a printed or written number."""
    return Decimal(repr(float(getattr(value, "value", value))))
