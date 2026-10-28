"""配筋図 (decision 73, CONTEXT.md 配筋図・中間帯鉄筋): the beam, column and footing sections drawn with ezdxf.

The input is current.json (the column and beam bars of the sample Example橋脚2 06_照査の前提.pdf 6.1) with the footing
bars of the sample's 6.1 (3) (upper face 線路 D25@125 at 79 outside, 直角 D25@125 at 104; lower face 線路 D25@125 at
100 outside, 直角 D29@125 at 127; stirrups D16 2本/m @250, 12_フーチング.pdf 255). The expected positions, counts and
printed numbers are hand calculation from those inputs; nothing is computed by the code under test. The text is
checked in the DXF (the PDF draws it as lines).
"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import ezdxf
import pymupdf
import pytest
from ezdxf.fonts import fonts

from webpier.core.errors import InputError
from webpier.export.drawing import FIGURES, drawing_dxf, drawing_figures
from webpier.export.drawing import beam, column, footing
from webpier.export.drawing import sheet as sheet_module
from webpier.export.drawing.sheet import Sheet, Vec2, mm, scale_for
from webpier.inputs import parse_input

ROOT = Path(__file__).parents[2]
CURRENT = json.loads((ROOT / "tests" / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def _bars(diameter, pitch, center):
    return {"diameter_mm": diameter, "pitch_mm": pitch, "cover_mode": "指定", "center_mm": center, "inner_layers": []}


def _stirrup():
    return {"diameter_mm": 16, "pitch_mm": 250, "distribution_mode": "密度", "width_pitch_mm": None,
            "density_per_m": 2}


FOOTING = {"materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
           "pure_cover_mm": None,
           "faces": {"上": {"outer_direction": "線路", "線路": _bars(25, 125, 79), "直角": _bars(25, 125, 104)},
                     "下": {"outer_direction": "線路", "線路": _bars(25, 125, 100), "直角": _bars(29, 125, 127)}},
           "stirrups": {"線路": _stirrup(), "直角": _stirrup()}}


def document(**changes):
    """current.json with the sample's footing bars, then each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    data["鉄筋"]["フーチング"] = deepcopy(FOOTING)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def pier(**changes):
    return parse_input(document(**changes))


def drawn(draw, figure, scale):
    sheet = Sheet(scale)
    draw(sheet, figure, Vec2(0, 0))
    return sheet


def texts(msp) -> list[str]:
    return [entity.dxf.text for entity in msp.query("TEXT")]


def dimensions(msp) -> list[str]:
    return [mtext.plain_text() for dim in msp.query("DIMENSION") for mtext in dim.get_geometry_block().query("MTEXT")]


def circles(msp) -> set[tuple[float, float, float]]:
    return {(round(c.dxf.center.x, 1), round(c.dxf.center.y, 1), c.dxf.radius) for c in msp.query("CIRCLE")}


def lines(msp, layer="鉄筋") -> set[tuple[float, float, float, float]]:
    return {(round(line.dxf.start.x, 1), round(line.dxf.start.y, 1), round(line.dxf.end.x, 1),
             round(line.dxf.end.y, 1)) for line in msp.query(f'LINE[layer=="{layer}"]')}

def bands(msp) -> set[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) of each closed polyline of the bars without bends (a bar drawn along its length)."""
    found = set()
    for polyline in msp.query('LWPOLYLINE[layer=="鉄筋"]'):
        points = list(polyline.get_points())
        if not any(point[4] for point in points):
            xs, ys = [point[0] for point in points], [point[1] for point in points]
            found.add((round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)))
    return found


def read(data: bytes):
    return ezdxf.read(io.StringIO(data.decode("utf-8")))


@pytest.fixture(scope="module")
def sample():
    return pier()


# --- the column: W6 4500 × B6 2700; model y = 2700 − Y ---

def test_the_column_bars_are_the_layout_of_the_input(sample):
    msp = drawn(column.draw_column, column.column_figure(sample), 40).msp
    # 線路 D32: two edge bars at 108 and 4392, 27 at 150 centred (300 … 4200), on the faces at Y = 108 and 2592
    rail = [108, *range(300, 4201, 150), 4392]
    expected = {(float(x), float(y), 16.0) for x in rail for y in (108, 2592)}
    # 直角 D19 指定 102: 9 at 250 centred, Y = 350 … 2350
    expected |= {(float(x), float(y), 9.5) for x in (102, 4398) for y in range(350, 2351, 250)}
    assert circles(msp) == expected
    assert len(expected) == 76


def test_the_column_ties_hook_the_bars_nearest_the_divisions_of_the_faces(sample):
    msp = drawn(column.draw_column, column.column_figure(sample), 40).msp
    # 線路 10 legs: 4500·k/9 = 500 … 4000 → bars 450, 1050, 1500, 1950, 2550, 3000, 3450, 4050, each tie beside its
    # bar towards the middle (16 + 11 mm); 直角 6 legs: 2700·k/5 = 540 … 2160 → bars Y 600, 1100, 1600, 2100 (± 9.5 +
    # 11). They run between the outer hoop's legs: 92 − 11 = 81 from each face.
    vertical = {(float(x), 2619.0, float(x), 81.0) for x in (477, 1077, 1527, 1977, 2523, 2973, 3423, 4023)}
    horizontal = {(81.0, 2700 - y, 4419.0, 2700 - y) for y in (620.5, 1120.5, 1579.5, 2079.5)}
    assert lines(msp) == vertical | horizontal
    (hoop,) = msp.query('LWPOLYLINE[layer=="鉄筋"]')
    xs, ys = [point[0] for point in hoop.get_points()], [point[1] for point in hoop.get_points()]
    assert (min(xs), max(xs), min(ys), max(ys)) == (81, 4419, 81, 2619)


def test_the_column_dimensions_and_labels_are_the_samples(sample):
    msp = drawn(column.draw_column, column.column_figure(sample), 40).msp
    assert sorted(dimensions(msp)) == sorted(["108", "192", "26×150=3900", "192", "108", "4500", "102",
                                              "108", "242", "8×250=2000", "242", "108", "2700"])
    assert set(texts(msp)) == {"D32-29本", "D19-9本", "D22-5組@150", "D22-3組@150", "直角方向", "線路方向"}


def test_a_cover_apart_from_the_bars_along_the_face_is_in_the_chain(sample):
    """線路 29 bars at 150 centred start at (4500 − 28·150)/2 = 150, so the 直角 cover 102 joins the chain along X;
    直角 9 bars at 310 start at (2700 − 8·310)/2 = 110, so the 線路 cover 108 is dimensioned on its own along Y."""
    changed = pier(**{"鉄筋/柱/main_bars/線路/distribution/mode": "中央ピッチ",
                      "鉄筋/柱/main_bars/直角/distribution/pitch_mm": 310,
                      "鉄筋/柱/column_hoops/direction_rows/1/effective_legs": 7})
    msp = drawn(column.draw_column, column.column_figure(changed), 40).msp
    assert sorted(dimensions(msp)) == sorted(["102", "48", "28×150=4200", "48", "102", "4500",
                                              "110", "8×310=2480", "110", "2700", "108"])
    assert "D22-3.5組@150" in texts(msp)


def test_a_column_with_one_direction_and_two_layers(sample):
    changed = pier(**{"鉄筋/柱/main_bars/直角/per_face_count": 0,
                      "鉄筋/柱/column_hoops/direction_rows/1/effective_legs": 2,
                      "鉄筋/柱/main_bars/線路/inner_layers": [{"per_face_count": 15, "clear_gap_mm": 32}]})
    msp = drawn(column.draw_column, column.column_figure(changed), 40).msp
    # layer 2 at 108 + 32 + 32 = 172 takes the middle 15 of layer 1's 29 positions: 1200 … 3300
    assert {(float(x), 2700.0 - 172, 16.0) for x in range(1200, 3301, 150)} <= circles(msp)
    assert len(circles(msp)) == 2 * (29 + 15)
    assert {"1段目D32-29本", "2段目D32-15本", "D22-1組@150"} <= set(texts(msp))
    assert sorted(dimensions(msp)) == sorted(["108", "192", "26×150=3900", "192", "108", "4500",
                                              "108", "2484", "108", "2700"])


def test_the_outer_hoop_size_is_needed():
    changed = document(**{"鉄筋/柱/main_bars/線路/cover_mode": "指定", "鉄筋/柱/main_bars/線路/center_mm": 108,
                          "鉄筋/柱/column_hoops/enclosing_diameter_mm": None})
    with pytest.raises(InputError, match=re.escape("鉄筋.柱.column_hoops.enclosing_diameter_mm: 値が必要です")):
        drawing_dxf(parse_input(changed))


# --- the beam: B1 2700 × (H2 + H3) 2700; model y = 2700 − y ---

def test_the_beam_bars_are_the_layout_of_the_input(sample):
    msp = drawn(beam.draw_beam, beam.beam_figure(sample), 25).msp
    found = circles(msp)
    assert len(found) == 17 + 8 + 18 + 2 * 17
    # upper layer 1: 17 D32 from the side bars' centre 184 at (2700 − 2·184)/16 = 145.75, each to 0.1 mm
    assert {(184.0, 2592.0, 16.0), (329.8, 2592.0, 16.0), (2516.0, 2592.0, 16.0)} <= found
    # layer 2 at 108 + 32 + 32 = 172: the middle 8 of the 17, from 1350 − 4·145.75 = 767 to 1350 + 3·145.75
    assert {(767.0, 2528.0, 16.0), (1787.3, 2528.0, 16.0)} <= found
    # lower: 18 D19 at 121; side bars D22 at 184 from both sides, 350 + 125·j
    assert {(184.0, 121.0, 9.5), (2516.0, 121.0, 9.5)} <= found
    assert {(x, 2700.0 - y, 11.0) for x in (184.0, 2516.0) for y in range(350, 2351, 125)} <= found
    (stirrup,) = msp.query('LWPOLYLINE[layer=="鉄筋"]')
    xs, ys = [point[0] for point in stirrup.get_points()], [point[1] for point in stirrup.get_points()]
    # round the face bars: 184 − 16 − 11 = 157, 108 − 16 − 11 = 81 from the top, 121 − 9.5 − 11 = 100.5 from below
    assert (min(xs), max(xs), min(ys), max(ys)) == (157, 2543, 100.5, 2619)


def test_the_beam_dimensions_and_labels(sample):
    msp = drawn(beam.draw_beam, beam.beam_figure(sample), 25).msp
    # the lower layer: 18 at (2700 − 368)/17 = 137.18 → 137.2
    assert sorted(dimensions(msp)) == sorted(["184", "16×145.8=2332", "184", "2700", "184", "17×137.2=2332", "184",
                                              "64", "108", "121", "350", "16×125=2000", "350", "2700"])
    assert set(texts(msp)) == {"1段目D32-17本", "2段目D32-8本", "D19-18本", "D22-17本", "D22-2組@125"}


def test_a_beam_without_side_bars(sample):
    changed = pier(**{"鉄筋/梁/side_bars": None})
    msp = drawn(beam.draw_beam, beam.beam_figure(changed), 25).msp
    assert len(circles(msp)) == 17 + 8 + 18
    assert set(texts(msp)) == {"1段目D32-17本", "2段目D32-8本", "D19-18本", "D22-2組@125"}
    assert "16×125=2000" not in dimensions(msp)


def test_the_stirrups_of_the_beam_are_needed():
    with pytest.raises(InputError, match=re.escape("鉄筋.梁.stirrups.pitch_mm: 値が必要です")):
        drawing_figures(pier(**{"鉄筋/梁/stirrups/pitch_mm": None}))


# a hand-made 線路 table (decision 111): D32 29 at Y 108 and 2592, D19 2 at 350 between them; the 直角 table is the
# main bars' own: D19 9 at X 102 and 4398, between them the 線路 bars by X, D32 2 at 108, 300 … 4200 (at 150), 4392
HAND_MADE = {"tension_rows": 1, "rows": [{"center_mm": 108, "diameter_mm": 32, "count": 29},
                                         {"center_mm": 350, "diameter_mm": 19, "count": 2},
                                         {"center_mm": 2592, "diameter_mm": 32, "count": 29}]}
CROSS_ROWS = [102, 108, *range(300, 4201, 150), 4392, 4398]


@pytest.fixture(scope="module")
def hand_made():
    return pier(**{"鉄筋/柱/custom_tables/線路": HAND_MADE})


def test_a_column_with_a_hand_made_table_draws_the_bars_at_the_crossings_of_the_rows(hand_made):
    """Decision 116: the bars at the crossings of the rows of the two tables, of one size. The 線路 引張鉄筋 first: Y
    108 and 2592 take the 29 D32 直角 rows (108, 300 … 4200, 4392); then 直角 X 102 and 4398 (D19, 9) only cross the
    D19 row Y 350, one bar each, and the other 16 are not drawn (the tables do not agree: 線路 60, 直角 76 bars). No
    row is a line."""
    msp = drawn(column.draw_column, column.column_figure(hand_made), 40).msp
    bars = {(float(x), 2700.0 - y, 16.0) for x in CROSS_ROWS if x not in (102, 4398) for y in (108, 2592)}
    assert circles(msp) == bars | {(102.0, 2350.0, 9.5), (4398.0, 2350.0, 9.5)}
    # the ties as calc.detailing.ties puts them: 線路 (hand-made) on the 直角 rows nearest 4500·k/9 (450, 1050, 1500,
    # 1950, 2550, 3000, 3450, 4050: D32, 16 + 11 towards the middle), 直角 on its main bars (Y 600, 1100, 1600, 2100:
    # D19, 9.5 + 11); between the outer hoop's legs round the outermost rows, 108 − 16 − 11 = 81 from each face
    ties = {(float(x), 2619.0, float(x), 81.0) for x in (477, 1077, 1527, 1977, 2523, 2973, 3423, 4023)}
    ties |= {(81.0, 2700 - y, 4419.0, 2700 - y) for y in (620.5, 1120.5, 1579.5, 2079.5)}
    assert lines(msp) == ties
    (hoop,) = msp.query('LWPOLYLINE[layer=="鉄筋"]')
    xs, ys = [point[0] for point in hoop.get_points()], [point[1] for point in hoop.get_points()]
    assert (min(xs), max(xs), min(ys), max(ys)) == (81, 4419, 81, 2619)


def test_a_column_with_a_hand_made_table_is_labelled_as_the_beam(hand_made):
    """The 引張鉄筋 rows by face (one layer: without it), the other rows of each table by size with their count, the
    hoops; the chains of the rows' centres: along X 0, 102, 108, 300 … 4200, 4392, 4398, 4500, along Y 0, 108, 350,
    2592, 2700."""
    msp = drawn(column.draw_column, column.column_figure(hand_made), 40).msp
    assert sorted(texts(msp)) == sorted(["D32-29本", "D32-29本", "D19-9本", "D19-9本", "D19-2本", "D32-58本",
                                         "D22-5組@150", "D22-3組@150", "直角方向", "線路方向"])
    assert sorted(dimensions(msp)) == sorted(["102", "6", "192", "26×150=3900", "192", "6", "102", "4500",
                                              "108", "242", "2242", "108", "2700"])
    assert len(msp.query('LINE[layer=="引出線"]')) >= 2 + 2 + 3 + 3  # the hoops' leaders and two fans of three


def test_the_fans_of_a_hand_made_table_point_at_bars(hand_made):
    """Each fan stops on the circle of a bar: of the 線路 rows by size, the bar nearest the left face (Y 350: X 102);
    of the 直角 rows, the bar nearest the top (Y 108) of the three rows nearest 0.85 × 4500 = 3825 (3750, 3900,
    3600)."""
    msp = drawn(column.draw_column, column.column_figure(hand_made), 40).msp
    pointed = set()
    for leader in msp.query('LINE[layer=="引出線"]'):
        end = leader.dxf.end
        for x, y, radius in circles(msp):
            if abs(((end.x - x) ** 2 + (end.y - y) ** 2) ** 0.5 - radius) < 0.01:
                pointed.add((x, y))
    assert pointed == {(102.0, 2350.0), (3600.0, 2592.0), (3750.0, 2592.0), (3900.0, 2592.0)}


def test_a_hand_made_table_with_two_layers_names_them():
    """Layer 1 of the upper face is the first row of the table, of the lower face the last."""
    table = {"tension_rows": 2, "rows": [{"center_mm": 108, "diameter_mm": 32, "count": 29},
                                        {"center_mm": 172, "diameter_mm": 32, "count": 15},
                                        {"center_mm": 2528, "diameter_mm": 29, "count": 15},
                                        {"center_mm": 2592, "diameter_mm": 32, "count": 29}]}
    figure = column.column_figure(pier(**{"鉄筋/柱/custom_tables/線路": table}))
    assert column.table_texts(figure.tables[0]) == (["1段目D32-29本", "2段目D32-15本"],
                                                     ["1段目D32-29本", "2段目D29-15本"])
    assert {"1段目D32-29本", "2段目D32-15本", "2段目D29-15本"} <= set(texts(drawn(column.draw_column, figure, 40).msp))


def test_the_files_have_the_column_with_a_hand_made_table(hand_made):
    assert list(drawing_figures(hand_made)) == ["梁", "柱", "フーチング"]
    assert "柱（水平断面）　1:40" in texts(read(drawing_dxf(hand_made)).modelspace())


# --- the footing: (B7 + B8 + B9) 7000 × H6 2700, cut along the track ---

def test_the_footing_bars_are_the_layers_of_both_faces(sample):
    msp = drawn(footing.draw_footing, footing.footing_figure(sample), 60).msp
    # 直角 at 125 centred on 3500, between the outermost centres of the face: 3500 ± 125·k, k ≤ 27 (125 … 6875)
    stations = [3500 + 125 * k for k in range(-27, 28)]
    expected = {(float(x), 2700.0 - 104, 12.5) for x in stations} | {(float(x), 127.0, 14.5) for x in stations}
    assert circles(msp) == expected
    # 線路 bars in the plane of the section, between those centres, as bands of their diameter: upper at 79 from the
    # top, lower at 100; no single lines
    assert bands(msp) == {(79.0, 2608.5, 6921.0, 2633.5), (100.0, 87.5, 6900.0, 112.5)}
    assert not lines(msp)


def test_the_footing_dimensions_and_labels(sample):
    msp = drawn(footing.draw_footing, footing.footing_figure(sample), 60).msp
    assert sorted(dimensions(msp)) == sorted(["79", "25", "27", "100", "2700", "7000"])
    assert sorted(texts(msp)) == sorted(["線路方向", "D25-ctc125", "直角方向", "D25-ctc125", "線路方向", "D25-ctc125",
                                         "直角方向", "D29-ctc125", "線路方向", "スターラップ",
                                         "線路方向 D16-1.00組/m ctc250", "直角方向 D16-1.00組/m ctc250"])


def test_a_footing_layer_inside_is_labelled_with_its_layer(sample):
    inner = [{"pitch_mm": 250, "clear_gap_mm": 25}]
    changed = pier(**{"鉄筋/フーチング/faces/下/線路/inner_layers": inner})
    msp = drawn(footing.draw_footing, footing.footing_figure(changed), 60).msp
    # layer 2 at 100 + 25 + 25 = 150 from the lower face
    assert (100.0, 137.5, 6900.0, 162.5) in bands(msp)
    assert {"1段目D25-ctc125", "2段目D25-ctc250"} <= set(texts(msp))


def test_the_upper_face_of_the_footing_is_needed():
    changed = pier(**{"鉄筋/フーチング/faces/上/線路/diameter_mm": None})
    with pytest.raises(InputError, match=re.escape("鉄筋.フーチング.faces.上.線路.diameter_mm: 値が必要です")):
        drawing_dxf(changed)


# --- the files ---

def test_the_dxf_has_the_three_figures_titled_with_their_scales(sample):
    data = drawing_dxf(sample)
    doc = read(data)
    msp = doc.modelspace()
    assert len(msp.query("CIRCLE")) == 76 + 77 + 110
    assert {"梁（柱前面の断面）　1:25", "柱（水平断面）　1:40", "フーチング（線路方向の断面）　1:60"} <= set(texts(msp))
    assert {layer.dxf.name for layer in doc.layers} >= {"躯体", "鉄筋", "寸法", "引出線", "文字"}
    assert not doc.audit().has_errors
    assert data == drawing_dxf(sample)


def test_the_bytes_do_not_depend_on_the_string_hash_seed_or_a_home(sample, tmp_path):
    """ezdxf orders the CLASSES section by a set, and needs a home: the DXF and the figures are the same in processes
    with other seeds and in one without a home (the headless runner's minimal environment)."""
    source = tmp_path / "input.json"
    source.write_text(json.dumps(document(), ensure_ascii=False), encoding="utf-8")
    script = ("import hashlib, json, sys; from pathlib import Path; from webpier.inputs import parse_input; "
              "from webpier.export.drawing import drawing_dxf, drawing_figures; "
              "pier = parse_input(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))); "
              "print(hashlib.sha256(drawing_dxf(pier)).hexdigest()); "
              "print(*(hashlib.sha256(pdf + png).hexdigest() for pdf, png in drawing_figures(pier).values()))")
    hashes = " ".join(hashlib.sha256(pdf + png).hexdigest() for pdf, png in drawing_figures(sample).values())
    expected = "\n".join([hashlib.sha256(drawing_dxf(sample)).hexdigest(), hashes])
    homes = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME")
    homeless = {key: value for key, value in os.environ.items() if key not in homes}
    for environment in ({**os.environ, "PYTHONHASHSEED": "1"}, {**os.environ, "PYTHONHASHSEED": "2"}, homeless):
        done = subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(source)], cwd=ROOT, check=True,
                              capture_output=True, text=True, env=environment)
        assert done.stdout.strip() == expected


def test_each_figure_is_one_pdf_page_and_its_png_with_the_same_bytes(sample):
    """The PNG is the PDF page at 200 dpi: GridLayoutPdf's PdfFigure takes it as the preview of the grid Excel only when
    one scale gives both its sides to half a pixel (its aspect ratio is the page's)."""
    figures = drawing_figures(sample)
    assert tuple(figures) == FIGURES[:3]  # the pile's is a 場所打ち杭's (test_drawing_pile)
    for name, (pdf, png) in figures.items():
        document_ = pymupdf.open(stream=pdf, filetype="pdf")
        assert document_.page_count == 1, name
        page = document_[0]
        assert page.get_drawings(), name
        assert "/ID" not in document_.pdf_trailer(), name
        picture = pymupdf.Pixmap(png)
        width, height = page.rect.width, page.rect.height  # one scale holds both axes to half a pixel
        assert max((picture.width - .5) / width, (picture.height - .5) / height) <= min(
            (picture.width + .5) / width, (picture.height + .5) / height), name
        assert round(picture.width / width * 72) == 200, name
    assert figures == drawing_figures(sample)


def test_the_text_is_drawn_with_ms_gothic():
    """ezdxf draws a text style whose font it cannot find with another font (Japanese becomes boxes): the style is
    MS Gothic (msgothic.ttc), which ezdxf finds."""
    sheet = Sheet(50)
    assert sheet.doc.styles.get("MSゴシック").dxf.font == "msgothic.ttc"
    assert fonts.font_manager.has_font("msgothic.ttc")
    assert fonts.font_manager.get_font_face("msgothic.ttc").family == "MS Gothic"


# --- the drafting parts ---

def test_a_member_is_drawn_at_the_smallest_scale_that_fits():
    assert (scale_for(4500, 2700), scale_for(2700), scale_for(7000, 2700), scale_for(60001)) == (40, 25, 60, 500)


def test_the_printed_lengths():
    assert (mm(145.75), mm(Decimal("108.0")), mm(Decimal("3900")), mm(Decimal("2332.0"))) == (
        "145.75", "108", "3900", "2332")


def test_a_narrow_gap_moves_its_text_outwards():
    """At 1/50 the text of a 10 mm gap does not fit: the first goes before its start, one between others above the
    chain, the last after its end."""
    sheet = Sheet(50)
    sheet.chain([Decimal(0), Decimal(10), Decimal(1000), Decimal(1010), Decimal(2000), Decimal(2010)], 0.0, -500.0,
                vertical=False, origin=Vec2(0, 0))
    found = {mtext.plain_text(): mtext.dxf.insert for dim in sheet.msp.query("DIMENSION")
             for mtext in dim.get_geometry_block().query("MTEXT")}
    assert set(found) == {"10", "990"}
    first, middle, last = sorted((insert for dim in sheet.msp.query("DIMENSION")
                                  for mtext in dim.get_geometry_block().query("MTEXT") if mtext.plain_text() == "10"
                                  for insert in (mtext.dxf.insert,)), key=lambda insert: insert.x)
    assert first.x < 0 and last.x > 2010
    assert 1000 < middle.x < 1010 and middle.y > first.y


def test_the_texts_of_narrow_gaps_in_a_row_step_out():
    """Of narrow gaps between others in a row, each text is one line further out than the one before, over three
    lines, then from the first line again; a gap that fits starts again."""
    sheet = Sheet(50)
    # gaps 1000 | 10 20 30 40 | 900 | 10 | 990: at 1/50 a text of two digits does not fit 40 mm
    sheet.chain([Decimal(value) for value in (0, 1000, 1010, 1030, 1060, 1100, 2000, 2010, 3000)], 0.0, -500.0,
                vertical=False, origin=Vec2(0, 0))
    found = sorted((mtext.dxf.insert.x, mtext.plain_text(), mtext.dxf.insert.y) for dim in sheet.msp.query("DIMENSION")
                   for mtext in dim.get_geometry_block().query("MTEXT") if len(mtext.plain_text()) == 2)
    line = (sheet_module.TEXT + 2 * sheet_module.GAP) * 50
    first = found[0][2]
    assert [(text, round((y - first) / line, 6)) for _, text, y in found] == [
        ("10", 0), ("20", 1), ("30", 2), ("40", 0), ("10", 0)]


def test_a_process_without_a_home_gets_one_under_the_temporary_folder(monkeypatch, tmp_path):
    def homeless():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(sheet_module.Path, "home", staticmethod(homeless))
    monkeypatch.setattr(sheet_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("USERPROFILE", "unused")
    sheet_module.home()
    assert os.environ["USERPROFILE"] == str(tmp_path / "webpier-ezdxf")


def test_a_process_with_a_home_keeps_it(monkeypatch):
    monkeypatch.setenv("USERPROFILE", "C:/Users/someone")
    sheet_module.home()
    assert os.environ["USERPROFILE"] == "C:/Users/someone"
