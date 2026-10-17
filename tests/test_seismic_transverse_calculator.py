"""Independent 0720 arithmetic, source identity, and physical-action contracts."""

from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any

import pytest

from src.calculator import calculate as calculate_foundation
from src.inputs import InputError, parse_input
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import ReactionInput, parse_reaction_input
from src.seismic_transverse_calculator import calculate_seismic_transverse
from src.transverse_calculator import calculate_transverse


FIXTURES = Path(__file__).parent / "fixtures"
REFERENCE = json.loads((FIXTURES / "seismic_transverse_example2.json").read_text(encoding="utf-8"))
CURRENT = json.loads((FIXTURES / "seismic_transverse_current_input.json").read_text(encoding="utf-8"))


def rounded(value: float, digits: int = 2) -> float:
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def single(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


@pytest.fixture(scope="module")
def source() -> dict[str, Any]:
    raw = (FIXTURES / "seismic_transverse_input.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CURRENT["input_sha256"]
    data = json.loads(raw)
    inputs = parse_reaction_input(data)
    result = {"inputs": inputs, "foundation": calculate_foundation(parse_input(data)),
              "conditions": parse_longitudinal_design_conditions(data)}
    result["reactions"], result["transverse"] = upstream(result, inputs)
    return result


def upstream(source: dict[str, Any], inputs: ReactionInput) -> tuple[dict, dict]:
    reactions = calculate_reactions(inputs)
    transverse = calculate_transverse(inputs, source["foundation"], reactions, design_conditions=source["conditions"])
    return reactions, transverse


def calculate(source: dict[str, Any], inputs: ReactionInput | None = None) -> dict[str, Any]:
    inputs = inputs or source["inputs"]
    reactions, transverse = upstream(source, inputs)
    return calculate_seismic_transverse(inputs, reactions, transverse)


@pytest.fixture
def canonical(source: dict[str, Any]) -> tuple[ReactionInput, dict, dict]:
    return source["inputs"], deepcopy(source["reactions"]), deepcopy(source["transverse"])


def assert_references(result: dict[str, Any]) -> None:
    frame = result["frame"]
    nodes = {node["id"]: node for node in frame["nodes"]}
    members = {member["id"]: member for member in frame["members"]}
    assert list(nodes) == list(range(1, len(nodes)+1))
    assert list(members) == list(range(1, len(members)+1))
    assert [(node["y"], node["x"]) for node in nodes.values()] == sorted(
        ((node["y"], node["x"]) for node in nodes.values()), key=lambda xy: (-xy[0], xy[1]))
    midpoints = [(sum(nodes[member[end]]["y"] for end in ("node_i", "node_j"))/2,
                  sum(nodes[member[end]]["x"] for end in ("node_i", "node_j"))/2) for member in members.values()]
    assert midpoints == sorted(midpoints, key=lambda xy: (-xy[0], xy[1]))
    for role, identifier in frame["node_ids"].items():
        assert role in nodes[identifier]["roles"]
    for action in result["actions"].values():
        for point in action["points"]:
            assert point["node_id"] == frame["node_ids"][point["anchor"]]
        for line in action["line_loads"]:
            assert line["from_node_id"] in nodes and line["to_node_id"] in nodes
            assert set(line["member_ids"]) <= members.keys()
    micro = frame["column_base_micro_member"]
    member = members[micro["member_id"]]
    assert member["node_i"] == micro["node_id"] == frame["node_ids"]["column_base_micro_top"]
    assert member["node_j"] == frame["node_ids"]["footing_top"]
    assert nodes[member["node_i"]]["y"]-nodes[member["node_j"]]["y"] == pytest.approx(.01)


def test_pdf_transcription_and_independent_current_input_arithmetic(canonical: tuple) -> None:
    result = calculate_seismic_transverse(*canonical)
    assert REFERENCE["girder"]["H"] == 9080
    assert CURRENT["girder"]["H"] == 9090
    assert sum(row[-1] for row in REFERENCE["girder"]["moment_rows"]) == 27105
    for track in ("up", "down"):
        actual = result["actions"][f"train_{track}"]
        rows = [row for row in actual["rows"] if row["active"]]
        assert len(rows) == len(REFERENCE["train"][track])
        for row, values in zip(rows, REFERENCE["train"][track], strict=True):
            expected = dict(zip(REFERENCE["train"]["columns"], values, strict=True))
            for key, value in expected.items():
                assert row[key] == value
            assert row["N"] == rounded(row["upstream_N"] * row["factor"])
            assert row["M"] == rounded(row["upstream_N"] * row["factor"] * row["arm"])
        for key, value in REFERENCE["train"]["totals"][track].items():
            assert actual["table_totals"][key] == value
    for side, row in zip(("B", "C"), result["horizontal"]["girder"]["rows"], strict=True):
        expected = CURRENT["girder"][side]
        assert row["H"] == sum(expected[key] for key in ("D1", "D2", "S2"))
        assert row["height"] == expected["height"]
        assert row["M"] == expected["M"]
    assert result["horizontal"]["girder"]["table_totals"]["H"] == 9090
    assert result["horizontal"]["girder"]["table_totals"]["M"] == 27105
    assert result["horizontal"]["train"]["table_totals"]["H"] == 144
    assert result["horizontal"]["train"]["display_totals"]["M"] == 770.4
    for name, value in CURRENT["inertia"].items():
        if name != "pedestal":
            assert result["inertia"][name] == value
    for name in ("beam_top", "beam_bottom", "column"):
        formula = result["formulas"][name]
        f = formula["factors"]
        assert rounded(f["b"]*f["w"]*f["unit_weight"]*f["Kh"]) == formula["value"]


def test_case_semantics_match_p13_and_preserve_full_fixed_actions(canonical: tuple) -> None:
    result = calculate_seismic_transverse(*canonical)
    assert [[row[key] for key in ("id", "symbol", "direction", "load_type")] for row in result["basic_cases"]] == REFERENCE["basic_cases"]
    combination = result["combinations"][0]
    assert all(combination[key] == value for key, value in REFERENCE["combination"].items() if key != "selected_cases")
    assert [row["id"] for row, coefficient in zip(result["basic_cases"], combination["coefficients"], strict=True)
            if coefficient] == [1,2,3,4,5,7,8,9]
    assert result["basic_cases"][4]["key"] == "train_down"
    assert result["basic_cases"][5]["key"] == "train_up"
    for key in ("dead_fixed", "dead_additional", "buoyancy_normal", "snow_2_year"):
        old, new = canonical[2]["actions"][key], result["actions"][key]
        assert new["table_totals"] == old["table_totals"]
        assert new["rows"] == old["rows"]
        assert new["details"] == old["details"]
        assert [point[field] for point in new["points"] for field in ("N","H","M")] == [point[field] for point in old["points"] for field in ("N","H","M")]
    fixed = result["actions"]["dead_fixed"]
    assert fixed["points"][0]["N"] == 8299.52
    assert fixed["points"][1]["N"] == 4167.4501953125
    assert result["actions"]["dead_additional"]["points"][1]["N"] == 1830.5999755859375
    assert result["actions"]["buoyancy_normal"]["points"][0]["N"] == -1701


def test_geometry_and_full_reference_remap_preserve_line_load_resultants(canonical: tuple) -> None:
    result = calculate_seismic_transverse(*canonical)
    frame = result["frame"]
    assert len(frame["nodes"]) == 8 and len(frame["members"]) == 7
    assert max(node["y"] for node in frame["nodes"]) == pytest.approx(13.05)
    assert frame["node_ids"]["cap_top"] == 2
    assert frame["column_base_micro_member"]["member_id"] == 5
    assert_references(result)
    line = result["actions"]["dead_fixed"]["line_loads"][0]
    assert line["member_ids"] == [2,3,4,5]
    nodes = {node["id"]: node for node in frame["nodes"]}
    members = {member["id"]: member for member in frame["members"]}
    length = sum(abs(nodes[members[i]["node_i"]]["y"]-nodes[members[i]["node_j"]]["y"]) for i in line["member_ids"])
    assert length == pytest.approx(2+.7+4.9)
    assert line["qN"] * length == pytest.approx(297.68*(2+.7+4.9))
    eq2 = result["actions"]["self_inertia"]["line_loads"]
    assert [row["member_ids"] for row in eq2] == [[2],[3],[4],[5]]
    assert sum(row["resultant_H"] for row in eq2) == pytest.approx(595.35*2+(595.35+297.68)/2*.7+297.68*4.9)
    taper = next(row for row in eq2 if row["anchor"] == "h3")
    assert taper["distribution"] == "linear" and taper["qH_top"] == 595.35 and taper["qH_bottom"] == 297.68
    for key in ("girder_inertia", "train_inertia"):
        assert result["actions"][key]["points"][0]["node_id"] == 2
        assert result["actions"][key]["points"][0]["M"] == result["actions"][key]["table_totals"]["M"]


def test_result_is_detached_and_has_no_legacy_or_support_dependency(canonical: tuple) -> None:
    inputs, reactions, transverse = canonical
    transverse.pop("legacy_audit")
    reactions.pop("longitudinal")
    reactions["macro_handoff_single"]["直角荷重強度"] = "must not read"
    reactions["macro_handoff_single"]["直角荷重位置"] = "must not read"
    reactions["macro_handoff_single"]["地震列車"] = "must not read"
    transverse["frame"]["solver_settings"] = {"forbidden": True}
    before = deepcopy((reactions, transverse))
    result = calculate_seismic_transverse(inputs, reactions, transverse)
    assert (reactions, transverse) == before
    for forbidden in ("springs", "support_node_id", "spring_provenance", "solver_settings", "legacy_nodes"):
        assert forbidden not in result["frame"]
    result["input"]["geometry"]["h4"] = 111
    result["actions"]["dead_fixed"]["points"][0]["N"] = -999
    result["frame"]["nodes"][0]["y"] = 222
    assert (reactions, transverse) == before


@pytest.mark.parametrize("rates", [(0.,0.,0.,0.), (1.,-1.,0.,0.), (-.2,.6,.1,.7)])
def test_signed_zero_and_nonunit_sum_rates_use_own_side_arms_once(source: dict, rates: tuple) -> None:
    inputs = source["inputs"]
    b = tuple(replace(row, factors=(rates[i],-rates[i],*row.factors[2:]), position=(-4.321+i*2) if i < 4 else None)
              if i < 4 else row for i,row in enumerate(inputs.dead.b))
    c = tuple(replace(row, position=-6.123 if i == 0 else 4.567) if i < 2 else row for i,row in enumerate(inputs.dead.c))
    inputs = replace(inputs, dead=replace(inputs.dead,b=b,c=c))
    result = calculate(source, inputs)
    for track, slot in (("down",0),("up",1)):
        action = result["actions"][f"train_{track}"]
        expected_n = expected_m = 0.
        for side, reaction in (("B",320.),("C",160.)):
            for bearing in getattr(inputs.dead, side.lower()):
                force = reaction*bearing.factors[slot]
                expected_n += force
                expected_m += rounded(force*(bearing.position or 0))
        assert action["table_totals"]["N"] == rounded(expected_n)
        assert action["table_totals"]["M"] == rounded(expected_m)
        b_rows = [row for row in action["rows"] if row["side"] == "B"]
        assert [row["raw_N"] for row in b_rows[:4]] == pytest.approx([320*r*(1 if slot==0 else -1) for r in rates])


@pytest.mark.parametrize("load", [0.,12.3456,48.])
def test_earthquake_train_load_and_whole_spans_control_both_actions(source: dict, load: float) -> None:
    original = source["inputs"]
    inputs = replace(original, train=replace(original.train,earthquake_load=load),
        spans=replace(original.spans,b=replace(original.spans.b,l1=.3,span=19.456,l2=.7),c=replace(original.spans.c,span=12.345)))
    result = calculate(source, inputs)
    expected = [load*(span.l1+span.span+span.l2)/2 for span in (inputs.spans.b,inputs.spans.c)]
    assert [row["formula"]["factors"]["earthquake_reaction"] for row in result["horizontal"]["train"]["rows"]] == expected
    assert result["horizontal"]["train"]["table_totals"]["H"] == sum(rounded(value*.3) for value in expected)
    assert result["actions"]["train_down"]["table_totals"]["N"] == rounded(sum(expected))
    if load == 0:
        assert all(row["raw_N"] == row["raw_M"] == 0 for row in result["actions"]["train_up"]["rows"])


def test_hs_upper_geometry_and_train_height_are_independent(source: dict) -> None:
    inputs = source["inputs"]
    baseline = calculate(source)
    hs_inputs = replace(inputs,spans=replace(inputs.spans,b=replace(inputs.spans.b,hs=3.123456789)))
    hs = calculate(source,hs_inputs)
    assert hs["frame"] == baseline["frame"]
    assert hs["horizontal"]["train"] == baseline["horizontal"]["train"]
    assert hs["horizontal"]["girder"]["rows"][0]["M"] == 6720*3.123456789
    upper_inputs = replace(inputs,spans=replace(inputs.spans,b=replace(inputs.spans.b,h1=.876543,h2=2.123456)))
    upper = calculate(source,upper_inputs)
    assert upper["frame"]["upper_levels"]["B"]["height"] == pytest.approx(2.999999)
    assert upper["horizontal"]["girder"]["table_totals"] == baseline["horizontal"]["girder"]["table_totals"]
    train_row = upper["horizontal"]["train"]["rows"][0]
    assert train_row["height"] == .876543+2.123456+1.1+1.5
    assert train_row["M"] == train_row["H"]*train_row["height"]
    assert train_row["height"] != single(train_row["height"])
    assert_references(upper)


def test_s2_changes_eq1_but_nonseismic_snow_does_not(source: dict) -> None:
    inputs = source["inputs"]
    baseline = calculate(source)
    changed = replace(inputs,snow=replace(inputs.snow,b=tuple((s2,s10+17,s30+31) if i < 4 else (s2,s10,s30)
                                                            for i,(s2,s10,s30) in enumerate(inputs.snow.b))))
    assert calculate(source,changed)["horizontal"] == baseline["horizontal"]
    changed = replace(inputs,snow=replace(inputs.snow,c=tuple((s2+1.23456,s10,s30) if i < 2 else (s2,s10,s30)
                                                            for i,(s2,s10,s30) in enumerate(inputs.snow.c))))
    result = calculate(source,changed)
    assert result["horizontal"]["girder"]["rows"][1]["H"] == rounded(2370+2*1.23456)


@pytest.mark.parametrize("b,c", [(0.,0.),(1.,1.),(1.,3.),(3.,1.),(0.,2.)])
def test_distinct_equal_zero_upper_levels_and_reordering(source: dict, b: float, c: float) -> None:
    inputs=source["inputs"]
    inputs=replace(inputs,spans=replace(inputs.spans,b=replace(inputs.spans.b,h1=0,h2=b),c=replace(inputs.spans.c,h1=0,h2=c)))
    reactions, transverse=upstream(source,inputs)
    first=calculate_seismic_transverse(inputs,reactions,transverse)
    transverse["frame"]["nodes"].reverse()
    transverse["frame"]["members"].reverse()
    assert calculate_seismic_transverse(inputs,reactions,transverse) == first
    levels=first["frame"]["upper_levels"]
    assert (levels["B"]["node_id"] == levels["C"]["node_id"]) == (b == c)
    for side,height in (("B",b),("C",c)):
        assert levels[side]["height"] == height
        assert (levels[side]["node_id"] == first["frame"]["node_ids"]["cap_top"]) == (height == 0)
    assert_references(first)


@pytest.mark.parametrize("centered", [False,True])
@pytest.mark.parametrize("upper", [.25,.5,1.])
def test_h1_branch_remains_connected_without_overlapping_upper_geometry(source: dict, centered: bool, upper: float) -> None:
    inputs=source["inputs"]
    # Transverse center = (w3-w1)/2 + w2; w1=9, w3=2.
    g=replace(inputs.geometry,h1=.5,b2=.5,b3=1,w2=3.5 if centered else 1,w3=2)
    inputs=replace(inputs,geometry=g,spans=replace(inputs.spans,b=replace(inputs.spans.b,h1=0,h2=upper),c=replace(inputs.spans.c,h1=0,h2=upper)))
    result=calculate(source,inputs)
    assert_references(result)
    assert result["inertia"]["pedestal"]["H"] == rounded(1*2*.5*24.5)
    assert result["inertia"]["pedestal"]["M"] == rounded(result["inertia"]["pedestal"]["H"]*.25)
    assert not any(row["anchor"] == "h1" for row in result["actions"]["self_inertia"]["line_loads"])
    nodes={node["id"]:node for node in result["frame"]["nodes"]}
    intervals=[]
    cap_y=nodes[result["frame"]["node_ids"]["cap_top"]]["y"]
    for member in result["frame"]["members"]:
        a,b=nodes[member["node_i"]],nodes[member["node_j"]]
        if a["x"] == b["x"] == 0 and min(a["y"],b["y"]) >= cap_y:
            intervals.append(sorted((a["y"],b["y"])))
    intervals.sort()
    assert all(first[1] <= second[0] for first,second in zip(intervals,intervals[1:]))


def test_nonrectangular_footing_and_distinct_intensities_use_actual_weight(source: dict) -> None:
    inputs=source["inputs"]
    g=replace(inputs.geometry,h1=.41,b2=.3,b3=1.1,w2=1.2,w3=2.1,h5=.8,h6=2.1,
              b4=.17,b5=.28,w4=1.7,w5=2.1,b6=2.61,w6=4.23,unit_weight_body=24.137,
              unit_weight_footing=25.123,unit_weight_displaced_soil=17.765)
    result=calculate(source,replace(inputs,geometry=g))
    bf,wf=g.b7+g.b8+g.b9,g.w7+g.w8+g.w9
    volume=g.h5/6*(bf*g.w8+g.b8*wf+2*(g.b8*g.w8+bf*wf))+bf*wf*g.h6
    weight=single(rounded(volume*g.unit_weight_footing))
    expected=rounded(weight/g.unit_weight_footing*(g.unit_weight_footing-g.unit_weight_displaced_soil))
    assert result["inertia"]["footing"] == expected
    assert expected != rounded(bf*wf*(g.h5+g.h6)*(g.unit_weight_footing-g.unit_weight_displaced_soil))
    assert result["inertia"]["beam_bottom"] == rounded((g.b1-g.b4-g.b5)*(g.w1-g.w4-g.w5)*g.unit_weight_body)
    assert result["inertia"]["column"] == rounded(g.b6*g.w6*g.unit_weight_body)
    assert result["inertia"]["beam_bottom"] != result["inertia"]["column"]
    assert result["formulas"]["footing"]["factors"]["weight"] == weight
    assert_references(result)


@pytest.mark.parametrize("source_index,key,value", [(1,"stage","0610"),(2,"stage","0610"),(1,"schema_version",True),
    (1,"schema_version",2),(2,"schema_version",1),(2,"case_model_version","legacy")])
def test_rejects_malformed_schema_and_case_model(canonical: tuple, source_index: int, key: str, value: Any) -> None:
    canonical[source_index][key]=value
    with pytest.raises(InputError,match="0720"):
        calculate_seismic_transverse(*canonical)


@pytest.mark.parametrize("which,problem", [("reaction","missing"),("reaction","duplicate"),("reaction","meaning"),
                                         ("fixed","missing"),("fixed","duplicate"),("fixed","meaning")])
def test_selected_cases_must_be_unique_and_have_expected_semantics(canonical: tuple, which: str, problem: str) -> None:
    rows=canonical[1]["transverse"] if which=="reaction" else canonical[2]["basic_cases"]
    row=rows[6] if which=="reaction" else rows[0]
    if problem=="missing": rows.remove(row)
    elif problem=="duplicate": rows.append(deepcopy(row))
    else: row["label"]="wrong semantics"
    with pytest.raises(InputError,match="識別|一意性|意味"):
        calculate_seismic_transverse(*canonical)


@pytest.mark.parametrize("value", [None,True,"1",float("nan"),float("inf"),-float("inf")])
@pytest.mark.parametrize("path", [(1,"train","earthquake","RB"),(1,"transverse",6,"B","moment"),
                                  (1,"macro_handoff_single","フーチング","N"),(2,"actions","dead_fixed","points",0,"N")])
def test_required_quantities_reject_missing_wrong_type_and_nonfinite(canonical: tuple, path: tuple, value: Any) -> None:
    node=canonical
    for key in path[:-1]: node=node[key]
    node[path[-1]]=value
    with pytest.raises(InputError,match="0720"):
        calculate_seismic_transverse(*canonical)


def test_snapshot_and_sha_identity_reject_mixed_runs_and_accept_json_decoding(canonical: tuple) -> None:
    inputs,reactions,transverse=canonical
    encoded=(json.loads(json.dumps(reactions)),json.loads(json.dumps(transverse)))
    assert calculate_seismic_transverse(inputs,*encoded)["input"] == asdict(inputs)
    for value in (reactions,transverse): value["provenance"]["input_sha256"]="a"*64
    assert calculate_seismic_transverse(inputs,reactions,transverse)["provenance"]["input_sha256"] == "a"*64
    transverse["provenance"]["input_sha256"]="b"*64
    with pytest.raises(InputError,match="SHA"):
        calculate_seismic_transverse(inputs,reactions,transverse)
    transverse["provenance"]["input_sha256"]="invalid"
    with pytest.raises(InputError,match="sha256"):
        calculate_seismic_transverse(inputs,reactions,transverse)
    transverse["provenance"].pop("input_sha256")
    transverse["input"]["spans"]["b"]["hs"]+=.1
    with pytest.raises(InputError,match="スナップショット"):
        calculate_seismic_transverse(inputs,reactions,transverse)


@pytest.mark.parametrize("height", [0.,.005,.01,math.nextafter(.01,math.inf)])
def test_h4_split_rejects_insufficient_or_unrepresentable_height(source: dict, height: float) -> None:
    inputs=replace(source["inputs"],geometry=replace(source["inputs"].geometry,h4=height))
    reactions,transverse=upstream(source,inputs)
    with pytest.raises(InputError,match="H4|座標精度"):
        calculate_seismic_transverse(inputs,reactions,transverse)


@pytest.mark.parametrize("problem", ["inclined","large_coordinate","bad_member","bad_node","bad_anchor","lost_upper"])
def test_frame_geometry_and_all_references_fail_explicitly(canonical: tuple, problem: str) -> None:
    inputs,reactions,transverse=canonical
    frame=transverse["frame"]
    column=next(member for member in frame["members"] if member["region"]=="h4")
    by_id={node["id"]:node for node in frame["nodes"]}
    if problem=="inclined": by_id[column["node_i"]]["x"]+=.1
    elif problem=="large_coordinate":
        by_id[column["node_i"]]["y"]=2.**45+4
        by_id[column["node_j"]]["y"]=2.**45
    elif problem=="bad_member": transverse["actions"]["dead_fixed"]["line_loads"][0]["member_ids"]=[999]
    elif problem=="bad_node": transverse["actions"]["dead_fixed"]["points"][0]["node_id"]=999
    elif problem=="bad_anchor": frame["node_ids"]["cap_top"]=frame["node_ids"]["footing_top"]
    else:
        inputs=replace(inputs,spans=replace(inputs.spans,b=replace(inputs.spans.b,h1=0,h2=1e-20)))
        reactions["input"]=transverse["input"]=asdict(inputs)
    with pytest.raises(InputError,match="0720"):
        calculate_seismic_transverse(inputs,reactions,transverse)


def test_loaded_missing_bearing_position_rejected_even_if_upstream_snapshot_claims_it(canonical: tuple) -> None:
    inputs,reactions,transverse=canonical
    b=(replace(inputs.dead.b[0],position=None),*inputs.dead.b[1:])
    inputs=replace(inputs,dead=replace(inputs.dead,b=b))
    reactions["input"]=transverse["input"]=asdict(inputs)
    with pytest.raises(InputError,match="荷重がある支承"):
        calculate_seismic_transverse(inputs,reactions,transverse)


def test_direct_eq_values_reject_inconsistent_upstream_moment(canonical: tuple) -> None:
    canonical[1]["transverse"][7]["B"]["moment"] *= .3
    with pytest.raises(InputError,match="現在入力の式"):
        calculate_seismic_transverse(*canonical)


@pytest.mark.parametrize("problem", ["h2_length", "line_omits_h3", "anchor_omits_h3", "row_boolean"])
def test_malformed_physical_intervals_and_numeric_rows_are_rejected(canonical: tuple, problem: str) -> None:
    frame = canonical[2]["frame"]
    if problem == "h2_length":
        h2 = next(member for member in frame["members"] if member["region"] == "h2")
        next(node for node in frame["nodes"] if node["id"] == h2["node_j"])["y"] += .125
    elif problem == "line_omits_h3":
        line = canonical[2]["actions"]["dead_fixed"]["line_loads"][0]
        h3 = next(member["id"] for member in frame["members"] if member["region"] == "h3")
        line["member_ids"].remove(h3)
    elif problem == "anchor_omits_h3":
        h3 = next(member["id"] for member in frame["members"] if member["region"] == "h3")
        frame["load_anchors"]["column_line_load"]["member_ids"].remove(h3)
    else:
        canonical[2]["actions"]["snow_2_year"]["rows"][0]["raw_N"] = True
    with pytest.raises(InputError, match="0720"):
        calculate_seismic_transverse(*canonical)


@pytest.mark.parametrize("region", ["h2", "h3", "h4"])
def test_reversed_loaded_member_endpoints_reject_negative_eq2_lengths(canonical: tuple, region: str) -> None:
    member = next(member for member in canonical[2]["frame"]["members"] if member["region"] == region)
    member["node_i"], member["node_j"] = member["node_j"], member["node_i"]
    with pytest.raises(InputError, match="0720.*(上端から下端|H4部材)"):
        calculate_seismic_transverse(*canonical)


@pytest.mark.parametrize("component", ["フーチング", "桁受け"])
def test_finite_0600_weight_conflict_with_unchanged_0620_d1_is_rejected(canonical: tuple, component: str) -> None:
    before = deepcopy(canonical[2])
    canonical[1]["macro_handoff_single"][component]["N"] += 123.5
    with pytest.raises(InputError, match="0600.*0620固定死荷重.*一致しません"):
        calculate_seismic_transverse(*canonical)
    assert canonical[2] == before


@pytest.mark.parametrize("source_name", ["0600_footing", "0600_pedestal", "0620_footing", "0620_pedestal"])
@pytest.mark.parametrize("bad", [None, True, float("nan"), "missing"])
def test_weight_crosscheck_fields_are_required_finite_numbers(canonical: tuple, source_name: str, bad: Any) -> None:
    if source_name == "0600_footing":
        row, field = canonical[1]["macro_handoff_single"]["フーチング"], "N"
    elif source_name == "0600_pedestal":
        row, field = canonical[1]["macro_handoff_single"]["桁受け"], "N"
    elif source_name == "0620_footing":
        row, field = canonical[2]["actions"]["dead_fixed"]["points"][1], "N"
    else:
        row, field = canonical[2]["actions"]["dead_fixed"]["details"], "pedestal_N"
    if bad == "missing":
        row.pop(field)
    else:
        row[field] = bad
    with pytest.raises(InputError, match="0720"):
        calculate_seismic_transverse(*canonical)


@pytest.mark.parametrize("c_height,coincident", [(.3, True), (math.nextafter(.3, math.inf), False)])
def test_decimal_upper_height_addition_merges_only_equal_levels(source: dict, c_height: float, coincident: bool) -> None:
    inputs = source["inputs"]
    inputs = replace(inputs, geometry=replace(inputs.geometry,h2=0.,h3=0.,h4=.011,h5=.004,h6=.005),
                     spans=replace(inputs.spans,b=replace(inputs.spans.b,h1=.1,h2=.2),
                                   c=replace(inputs.spans.c,h1=c_height,h2=0.)))
    result = calculate(source, inputs)
    frame = result["frame"]
    levels = frame["upper_levels"]
    assert levels["B"]["height"] == .3
    assert levels["C"]["height"] == c_height
    assert (levels["B"]["node_id"] == levels["C"]["node_id"]) is coincident
    upper_members = [member for member in frame["members"] if member["region"] == "upper_geometry"]
    assert len(upper_members) == (1 if coincident else 2)
    nodes = {node["id"]: node for node in frame["nodes"]}
    lengths = [nodes[member["node_i"]]["y"]-nodes[member["node_j"]]["y"] for member in upper_members]
    assert all(length > 0 for length in lengths)
    if not coincident:
        assert min(lengths) < 1e-15
    assert_references(result)
