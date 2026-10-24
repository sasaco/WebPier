"""The input of Capacita's ``run-pile-joint`` (HsCalc: the joint of a steel pipe pile with the footing, decision 90).

mm, N/mm2, kN. The pipe is the corroded one (D and t after the deduction); ``edgeDistance`` is from the outer edge of the pipe to the
centroid of the bars. The safety factors are the ones that make HsCalc's Mu agree with the example's Mud (the example prints
the pipe's γs 1.05 beside them, which the resistance does not use): γc 1.3, bars 1.0, pipe 1.0. WebPier gives no f'cc nor ε'cu:
HsCalc finds the confinement itself. A row of the input is a pile row; its id is the row's number.
"""

from __future__ import annotations

from collections.abc import Sequence
import json

from ...calc.pile_joint import GAMMA_C, JointRowForces, JointSection

GAMMA_BAR = 1.0
GAMMA_PIPE = 1.0


def row_id(row: int) -> str:
    return str(row)


def build(joint: JointSection, rows: Sequence[JointRowForces]) -> dict[str, object]:
    return {
        "pipe": {"outerDiameter": joint.diameter.value, "thickness": joint.thickness.value, "fsyk": joint.pipe_strength.value},
        "rebar": {"diameter": joint.bar_diameter.value, "count": joint.bar_count, "fsyk": joint.bar_strength.value,
                  "edgeDistance": joint.centroid.value},
        "concrete": {"fck": joint.fck.value},
        "safety": {"gammaC": GAMMA_C.value, "gammaS": GAMMA_BAR, "gammaPipe": GAMMA_PIPE},
        "rows": [{"id": row_id(row.row), "axialForce": row.forces.nd} for row in rows]}


def write(joint: JointSection, rows: Sequence[JointRowForces]) -> bytes:
    return json.dumps(build(joint, rows), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
