"""A cast-in-place pile of the example's kind for the tests of the pile body (decision 91): tests/fixtures/inputs/pile.json (D 1.0 m,
f'ck 18.8 N/mm2, 自然泥水) with 20-D32 (SD345, 100 mm of cover) and D16 hoops at 200 mm, and the PIK lines of its pile rows."""

import io
from copy import deepcopy
from pathlib import Path

from reportlab.pdfgen import canvas

from webpier.calc.pile_body import PointForces, SectionForce
from webpier.calc.pile_cast import assemble, section, select
from webpier.core.integrity import load_json
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parent / "fixtures"
BARS = {"軸方向鉄筋": {"径": 32, "本数": 20, "材質": "SD345", "純かぶり": 100.0},
        "帯鉄筋": {"径": 16, "材質": "SD345", "間隔": 200.0}}


def _pdf(text: str, pages: int) -> bytes:
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for number in range(1, pages + 1):
        page.drawString(60, 780, f"{text} {number}/{pages}")
        page.showPage()
    page.save()
    return stream.getvalue()


# Capacita's pages of the two checks as the stand-in returns them: 1 page of bending and 2 of shear
PAGES = {"bending_safety_destruction": _pdf("CAPACITA bending", 1), "shear_safety_destruction": _pdf("CAPACITA shear", 2)}


def cast_input(**changes):
    """pile.json with the bars of the pile body, each ``changes`` key an item of 場所打ち杭 (or its group, as a dict)."""
    data = deepcopy(load_json((FIXTURES / "inputs" / "pile.json").read_bytes()))
    data["杭基礎"]["場所打ち杭"].update(deepcopy(BARS))
    data["杭基礎"]["場所打ち杭"].update(changes)
    return parse_input(data)


def line(focus, point, distance, largest, smallest):
    return PointForces(focus, point, distance, SectionForce(*largest), SectionForce(*smallest))


# The bundled member of a row of three piles, FEMPython's sign (compression negative): the head is the joint's, and below it
# the largest moment is |1500| at 3.0 m (case 5), the largest shear |450| at 3.0 m (case 7), the largest compression -4800 at the
# tip (case 10) and the largest tension 600 at the tip (case 9).
LINES = [
    line("M", "ITAN", 0.0, (900.0, 0.0, -2400.0, 1), (-600.0, 0.0, -2400.0, 2)),
    line("M", "4", 3.0, (1500.0, 200.0, -3000.0, 5), (-1200.0, 100.0, -2800.0, 6)),
    line("S", "4", 3.0, (900.0, 450.0, -2900.0, 7), (-100.0, -300.0, -2500.0, 8)),
    line("N", "JTAN", 19.0, (50.0, 20.0, 600.0, 9), (30.0, 10.0, -4800.0, 10)),
]
# The same without a tension anywhere
COMPRESSED = [LINES[0], LINES[1], LINES[2], line("N", "JTAN", 19.0, (50.0, 20.0, -300.0, 9), (30.0, 10.0, -4800.0, 10))]


def cast_result(lines=LINES, skipped=(), pages=None):
    pier = cast_input()
    rows = [select(1, 7, 3, lines), select(2, 8, 2, lines)]
    return assemble(section(pier), rows, "5.0.1", "ab" * 32, skipped,
                    dict(PAGES if pages is None else pages))
