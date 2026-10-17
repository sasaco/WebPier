"""The native rules of a FrameWeb input (2D frame) that WebPier writes, checked on the saved JSON.

Sources: the Example2 FrameWeb files (format, types and the rigid-region convention) and the FrameWeb behaviour
recorded in README (spring value 1 is a fixed support, empty member rows are rejected, member load intensities
are projected to 0.01, an empty Combine is dropped, the Combine grid shows 50 Define columns). Partial and
varying member loads follow FrameWebforCS (calculation/CalculationRequest.cs): for a distributed load (mark 2)
L1 is the distance of the load start from the member start and L2 the margin from the member end, both projected
to 0.001 m; P1 acts at L1 and P2 at the end of the load; a symbol "LL" makes the case a moving load.
"""

import json
from copy import deepcopy

import pytest

from frameweb_support import CURVE, EXAMPLE2, EXAMPLE2_09, T_PEDESTAL, WIDTHS, ground, longitudinal, transverse
from webpier.core.errors import InputError
from webpier.core.integrity import dump_json, load_json
from webpier.export.frameweb import build_frameweb, build_frameweb_transverse, validate_frameweb


@pytest.fixture(scope="module")
def current():
    return build_frameweb(longitudinal())


def test_the_built_document_is_valid_after_a_json_round_trip(current):
    validate_frameweb(load_json(dump_json(current)))


def test_the_example2_model_tables_follow_the_same_format():
    # Example2 without its empty member rows (FrameWeb rejects them) and with the dimension it saves.
    example = {key: deepcopy(EXAMPLE2[key]) for key in ("node", "fix_node", "member", "element", "load", "define",
                                                        "combine", "pickup")}
    for case in example["load"].values():
        for key in ("fix_member", "joint"):
            del case[key]
        rows = [row for row in case.pop("load_member", []) if row.get("P1") is not None]
        if rows:
            case["load_member"] = [{**row, "m2": row["m1"], "direction": "gy", "L1": 0, "P1": -row["P1"],
                                    "P2": -row["P2"]} for row in rows]
        for index, row in enumerate(case.get("load_node", []), 1):
            row["row"] = index
    example["dimension"] = 2
    validate_frameweb(example)


def mutate(document, path, value):
    target = document
    for key in path[:-1]:
        target = target[key]
    if value is DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value


DELETE = object()

INVALID = {
    "not_a_table": ((), []),
    "extra_top_level": (("three",), {}),
    "missing_top_level": (("pickup",), DELETE),
    "dimension_3": (("dimension",), 3),
    "dimension_bool": (("dimension",), True),
    "node_list": (("node",), []),
    "node_empty": (("node",), {}),
    "node_key": (("node", "01"), {"x": 0, "y": 0, "z": None}),
    "node_key_zero": (("node", "0"), {"x": 0, "y": 0, "z": None}),
    "node_key_text": (("node", "a"), {"x": 0, "y": 0, "z": None}),
    "node_fields": (("node", "1", "w"), 0),
    "node_z": (("node", "1", "z"), 0),
    "node_x_text": (("node", "1", "x"), "0"),
    "node_x_bool": (("node", "1", "x"), False),
    "node_x_nan": (("node", "1", "x"), float("nan")),
    "member_end": (("member", "1", "nj"), 99),
    "member_end_text": (("member", "1", "nj"), "2"),
    "member_same_ends": (("member", "1", "nj"), 1),
    "member_zero_length": (("node", "2", "y"), 10.3),
    "member_section": (("member", "1", "e"), 9),
    "member_cg": (("member", "1", "cg"), 0),
    "member_fields": (("member", "1", "ni"), DELETE),
    "disconnected": (("node", "7"), {"x": 5, "y": 5, "z": None}),
    "element_types": (("element", "2"), {}),
    "element_fields": (("element", "1", "1", "Y"), 1),
    "element_e_zero": (("element", "1", "1", "E"), 0),
    "element_iz_negative": (("element", "1", "2", "Iz"), -1),
    "element_g": (("element", "1", "1", "G"), 1),
    "element_name": (("element", "1", "1", "n"), 1),
    "element_empty": (("element", "1"), {}),
    "fix_list": (("fix_node", "1"), {}),
    "fix_empty": (("fix_node", "1"), []),
    "fix_node_ref": (("fix_node", "1", 0, "n"), "9"),
    "fix_node_int": (("fix_node", "1", 0, "n"), 6),
    "fix_one": (("fix_node", "1", 0, "tx"), 1),
    "fix_zero": (("fix_node", "2", 0, "rz"), 0),
    "fix_null": (("fix_node", "2", 0, "ty"), None),
    "fix_3d": (("fix_node", "1", 0, "tz"), 5),
    "fix_row": (("fix_node", "1", 0, "row"), 2),
    "fix_fields": (("fix_node", "1", 0, "extra"), 2),
    "load_gap": (("load", "22"), DELETE),
    "load_spring": (("load", "1", "fix_node"), 3),
    "load_spring_bool": (("load", "1", "fix_node"), True),
    "load_type": (("load", "1", "element"), 2),
    "load_symbol": (("load", "1", "symbol"), None),
    "load_symbol_moving": (("load", "1", "symbol"), "LL"),
    "load_pitch": (("load", "1", "LL_pitch"), 0),
    "load_rate": (("load", "1", "rate"), -1),
    "load_fields": (("load", "1", "fix_member"), 1),
    "load_missing_field": (("load", "1", "name"), DELETE),
    "node_rows_empty": (("load", "2", "load_node"), []),
    "node_row_ref": (("load", "2", "load_node", 0, "n"), "99"),
    "node_row_zero": (("load", "2", "load_node", 0, "ty"), 0),
    "node_row_all_null": (("load", "13", "load_node", 0, "tx"), None),
    "node_row_3d": (("load", "2", "load_node", 0, "rx"), 1.0),
    "node_row_index": (("load", "2", "load_node", 1, "row"), 1),
    "node_row_fields": (("load", "2", "load_node", 0, "extra"), 1),
    "member_rows_dict": (("load", "1", "load_member"), {}),
    "member_row_ref": (("load", "1", "load_member", 0, "m1"), "9"),
    "member_row_ref2": (("load", "1", "load_member", 0, "m2"), "9"),
    "member_row_mark": (("load", "1", "load_member", 0, "mark"), 1),
    "member_row_direction": (("load", "1", "load_member", 0, "direction"), "z"),
    "member_row_start_negative": (("load", "1", "load_member", 0, "L1"), -0.5),
    "member_row_start_projection": (("load", "1", "load_member", 0, "L1"), 0.0005),
    "member_row_margin_text": (("load", "1", "load_member", 0, "L2"), "0"),
    "member_row_margin_negative": (("load", "1", "load_member", 0, "L2"), -1),
    "member_row_margin_projection": (("load", "1", "load_member", 0, "L2"), 1.2344),
    "member_row_no_length": (("load", "1", "load_member", 0, "L1"), 2),  # member 1 is 2.000 long
    "member_row_beyond_length": (("load", "1", "load_member", 0, "L2"), 2.5),
    "member_row_projection": (("load", "1", "load_member", 0, "P1"), -297.681),
    "member_row_end_projection": (("load", "1", "load_member", 0, "P2"), -297.685),
    "member_row_null": (("load", "1", "load_member", 0, "P1"), None),
    "define_reference": (("define", "1", "C1"), 99),
    "define_reference_zero": (("define", "1", "C1"), 0),
    "define_reference_float": (("define", "1", "C1"), 1.0),
    "define_duplicate": (("define", "13", "C2"), 13),
    "define_column_gap": (("define", "1", "C3"), 2),
    "define_row": (("define", "1", "row"), 2),
    "define_empty": (("define", "1", "C1"), DELETE),
    "define_extra_field": (("define", "1", "name"), "x"),
    "define_mixed_empty": (("define", "5", "C2"), 1),
    "combine_not_table": (("combine", "1"), []),
    "define_without_row": (("define", "1", "row"), DELETE),
    "combine_reference": (("combine", "1", "C99"), 1),
    "combine_column": (("combine", "1", "X1"), 1),
    "combine_column_number": (("combine", "1", "Ca"), 1),
    "combine_zero": (("combine", "1", "C1"), 0),
    "combine_name": (("combine", "1", "name"), None),
    "combine_row": (("combine", "1", "row"), "1"),
    "combine_empty": (("combine", "6"), {"row": 6, "name": "", "C5": 1}),
    "pickup_reference": (("pickup", "1", "C1"), 17),
    "pickup_duplicate": (("pickup", "1", "C2"), 1),
    "pickup_empty": (("pickup", "2", "C1"), DELETE),
    "pickup_name": (("pickup", "1", "name"), 3),
}


@pytest.mark.parametrize("path,value", INVALID.values(), ids=INVALID.keys())
def test_rejects(current, path, value):
    document = json.loads(json.dumps(current))
    if path:
        mutate(document, path, value)
    else:
        document = value
    with pytest.raises(InputError, match="FrameWeb入力"):
        validate_frameweb(document)


def test_rejects_more_defines_than_the_combine_grid_shows(current):
    document = json.loads(json.dumps(current))
    for number in range(23, 52):
        document["load"][str(number)] = {**document["load"]["1"]}
        document["define"][str(number)] = {"row": number, "C1": number}
    validate_frameweb({**document, "define": {k: v for k, v in document["define"].items() if int(k) <= 50}})
    with pytest.raises(InputError, match="50"):
        validate_frameweb(document)


def test_a_member_load_range_may_span_members(current):
    document = json.loads(json.dumps(current))
    document["load"]["1"]["load_member"] = [{**document["load"]["1"]["load_member"][0], "m2": "3"}]
    validate_frameweb(document)


def member_row(document, **changes):
    document = json.loads(json.dumps(document))
    row = document["load"]["1"]["load_member"][0]
    row.update(changes)
    return document


@pytest.mark.parametrize("changes", [
    {"L1": 0.5}, {"L2": 1.08}, {"L1": 0.25, "L2": 1.749}, {"P2": -297.0}, {"P1": 0}, {"P2": 0},
    {"L1": 0.3, "P1": -9.6, "P2": -8.7}], ids=["start", "margin", "inside", "trapezoid", "from_zero", "to_zero",
                                               "partial_trapezoid"])
def test_partial_and_varying_loads_on_one_member_are_valid(current, changes):
    # Member 1 is 2.000 long: the load runs from L1 to 2.000 − L2, P1 at its start and P2 at its end.
    validate_frameweb(member_row(current, **changes))


@pytest.mark.parametrize("changes", [{"P1": 0, "P2": 0}, {"L1": 1, "L2": 1}, {"L1": 1.5, "L2": 0.5}],
                         ids=["no_intensity", "no_length", "margin_reaches_start"])
def test_rejects_an_empty_member_load(current, changes):
    with pytest.raises(InputError, match="load.1.load_member"):
        validate_frameweb(member_row(current, **changes))


@pytest.mark.parametrize("changes", [{"m2": "3", "L1": 0.5}, {"m2": "3", "L2": 0.5}, {"m2": "3", "P2": -297.0}],
                         ids=["start", "margin", "varying"])
def test_a_member_load_range_is_uniform_over_whole_members(current, changes):
    # FrameWeb repeats L1 / L2 on every member of a range and carries P1 on, so a partial or varying load is one
    # row per member.
    with pytest.raises(InputError, match="load.1.load_member"):
        validate_frameweb(member_row(current, **changes))


@pytest.mark.parametrize("changes", [{}, T_PEDESTAL, CURVE, WIDTHS | ground(5.2)],
                         ids=["current", "pedestal", "curve", "haunch_cut"])
def test_the_transverse_document_is_valid_after_a_json_round_trip(changes):
    validate_frameweb(load_json(dump_json(build_frameweb_transverse(transverse(**changes)))))


def test_the_example2_09_model_tables_follow_the_same_format():
    # Example2 09 without its member loads (range rows in local axes, see test_frameweb_transverse_loads) and
    # without the GUI-only keys of its load cases.
    example = {key: deepcopy(EXAMPLE2_09[key]) for key in ("node", "fix_node", "member", "element", "load", "define",
                                                           "combine", "pickup", "dimension")}
    for case in example["load"].values():
        for key in ("fix_member", "joint", "load_member"):
            case.pop(key, None)
    validate_frameweb(example)
