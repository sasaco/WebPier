"""The frame of a pile foundation analyzed by the real FEMPython runner against Example橋脚4's own diagrams (decision 88).

Skipped without a FEMPython runner. The fixed and the additional dead load (D1, D2) are the load cases whose values the example
prints in its section force diagrams (III-75, III-76; tests/fixtures/example4/frame_responses.json) and that do not depend on the
train load: the axial force of the piles at their heads and the reaction of their tips follow from the stiffness of the piles
and the springs alone. The springs are those the real SOIL-JR 5.2 returned (tests/fixtures/soiljr/pile_steel_grid.sdc).

The head forces agree with the example to 0.01 %, the tips to 0.02 %: the last layer (4-2) has the vertical shear spring of the
pull side, which the example's table III-21 shows (P5, owner; the push side alone gave tips 9 % and 4 % larger).
"""

import json
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.core.integrity import load_json
from webpier.export.frameweb import build_frameweb
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
EXAMPLE = json.loads((FIXTURES / "example4" / "frame_responses.json").read_text(encoding="utf-8"))
SDC = (FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes()


def document():
    """The FrameWeb input of the longitudinal frame of Example橋脚4 with the springs of the sdc, its D1 and D2 as the only
    load cases of one pickup."""
    pier = parse_input(load_json((FIXTURES / "inputs" / "example4.json").read_bytes()))
    result = calculate_longitudinal(pier, PileFoundation(calculate_pile_ground(pier), parse_sdc(SDC)),
                                    calculate_reaction(pier))
    found = build_frameweb(result)
    assert [(case["symbol"], case["name"]) for case in list(found["load"].values())[:2]] == [
        ("D1", "固定死荷重"), ("D2", "付加死荷重")]
    found["define"] = {"1": {"row": 1, "C1": 1}, "2": {"row": 2, "C1": 2}}
    found["combine"] = {"1": {"row": 1, "name": "D1", "C1": 1}, "2": {"row": 2, "name": "D2", "C2": 1}}
    found["pickup"] = {"1": {"row": 1, "name": "D1 D2", "C1": 1, "C2": 2}}
    return found, result


def reactions(found, runner: Path) -> dict[tuple[str, int], float]:
    """The vertical reaction at each node of the pickup, by load (D1 is the maximum, D2 the minimum of the pickup)."""
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "pile.json"
        path.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            [str(runner), "run", "--input", str(path), "--output-dir", str(Path(work) / "out"), "--generate-pdf", "false",
             "--generate-pik", "true", "--generate-pickup-reaction-csv", "true"], capture_output=True, check=True)
        assert json.loads(done.stdout.decode("utf-8-sig"))["ok"] is True
        lines = (Path(work) / "out" / "pickup-reaction.csv").read_text(encoding="utf-8-sig").splitlines()
        pik = (Path(work) / "out" / "pickup.pik").read_text(encoding="utf-8-sig").splitlines()
    header = [name.split(" ")[0] for name in lines[0].split(",")]
    found_values = {}
    for line in lines[1:]:
        cells = line.split(",")
        row = dict(zip(header, cells))
        if row["focus_component"] == "fy":
            found_values[("min", int(row["node_id"]))] = float(row["min_fy"])
            found_values[("max", int(row["node_id"]))] = float(row["max_fy"])
    return found_values, pik


def head_axial_forces(pik: list[str], members: list[int]) -> list[float]:
    """The axial force at the head (i end) of each pile row's member: the Nd columns (max, min) of its first line."""
    forces = []
    for member in members:
        row = next(line.split() for line in pik if line.split()[:3] == ["1", "M", str(member)] and line.split()[5] == "ITAN")
        forces.append(min(float(row[9]), float(row[12])))  # the largest compression
    return forces


def test_the_heads_and_the_tips_of_the_piles_carry_what_the_example_prints(real_fempython_runner):
    found, result = document()
    nodes = result.frame.pile_nodes
    reaction, pik = reactions(found, real_fempython_runner)
    d1 = EXAMPLE["section_force_diagrams"]["longitudinal"][0]
    d2 = EXAMPLE["section_force_diagrams"]["longitudinal"][1]
    heads = sorted(-force for force in head_axial_forces(pik, [n.member for n in nodes]))
    assert heads == pytest.approx(sorted([5635.32, 5765.44]), abs=0.2)  # III-75: the axial force at the heads, D1
    assert -5635.32 in d1["N_values_kN"] and -5765.44 in d1["N_values_kN"]
    tips = sorted(-reaction[("min", n.tip)] for n in nodes)  # D1 is the largest compression of the pickup: its minimum
    assert tips == pytest.approx(sorted([931.65, 953.16]), rel=0.0005)  # III-75: the last layer has the pull side's shear spring
    assert -931.65 in d1["N_values_kN"] and -953.16 in d1["N_values_kN"]
    d2_tips = sorted(-reaction[("max", n.tip)] for n in nodes)
    assert d2_tips == pytest.approx(sorted([157.14, 164.51]), abs=0.05)  # III-76
    assert -157.14 in d2["N_values_kN"] and -164.51 in d2["N_values_kN"]
