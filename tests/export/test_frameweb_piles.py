"""The FrameWeb input of a pile foundation (decision 88): springs at the pile tips (``fix_node``), the springs along each pile row's
member as intervals from its head (``fix_member``), and the set of each load case in both. Example橋脚4 with the .sdc the real
SOIL-JR 5.2 returned for it."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.integrity import dump_json, load_json
from webpier.export.frameweb import build_frameweb, build_frameweb_transverse, validate_frameweb
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture(scope="module")
def results():
    pier = parse_input(load_json((FIXTURES / "inputs" / "example4.json").read_bytes()))
    foundation = PileFoundation(calculate_pile_ground(pier),
                                parse_sdc((FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes()))
    reaction = calculate_reaction(pier)
    return calculate_longitudinal(pier, foundation, reaction), calculate_transverse(pier, foundation, reaction)


@pytest.fixture(scope="module")
def document(results):
    return build_frameweb(results[0])


def test_the_tips_of_the_piles_hold_the_springs_of_each_term(document, results):
    frame = results[0].frame
    tips = [str(nodes.tip) for nodes in frame.pile_nodes]
    for number, vertical in (("1", 532245), ("2", 1064491)):
        rows = document["fix_node"][number]
        assert [row["n"] for row in rows] == tips and [row["row"] for row in rows] == [1, 2]
        assert {(row["tx"], row["ty"], row["rz"]) for row in rows} == {(None, vertical, None)}  # SOIL-JR leaves out the others


def test_each_pile_row_has_the_springs_of_its_layers_from_the_head(document, results):
    members = [str(nodes.member) for nodes in results[0].frame.pile_nodes]
    for number, horizontal, shear in (("1", [14208, 19186, 37482, 125727, 125727], [13534, 18275, 35702, 119755, 119755]),
                                      ("2", [28417, 38373, 74964, 251453, 251453], [27067, 36550, 71404, 239510, 239510])):
        rows = document["fix_member"][number]
        assert [row["row"] for row in rows] == list(range(1, 11))
        for index, member in enumerate(members):
            mine = rows[index * 5:(index + 1) * 5]
            assert {row["m"] for row in mine} == {member}
            assert [row["length"] for row in mine] == [3.75, 7.5, 1.95, 12.3, 1.0]
            assert [row["ty"] for row in mine] == horizontal  # the horizontal spring is the member's local y
            assert [row["tx"] for row in mine] == shear  # the vertical shear spring is along it (the last layer takes the pull side)
            assert all(row["tz"] is None and row["tr"] is None for row in mine)


def test_each_load_case_takes_the_set_of_its_term_in_both(document):
    cases = document["load"].values()
    assert {(case["fix_node"], case["fix_member"]) for case in cases} == {(1, 1), (2, 2)}


def test_the_piles_are_elastic_members_of_their_own_section(document, results):
    frame = results[0].frame
    sections = document["element"]["1"]
    pile_section = sections[str(document["member"][str(frame.pile_nodes[0].member)]["e"])]
    assert pile_section == {"E": 200000000, "G": None, "Xp": 1e-05, "A": 0.12513, "J": None, "Iy": None, "Iz": 0.00954,
                            "n": "杭"}
    base = [m for m in frame.members if m.region.value == "footing_base"]
    assert {sections[str(document["member"][str(m.number)]["e"])]["n"] for m in base} == {"剛域"}


def test_the_transverse_frame_has_a_row_under_the_footing_centre(results):
    document = build_frameweb_transverse(results[1])
    frame = results[1].frame
    assert sorted(document["fix_node"]) == ["1", "2"] and len(document["fix_node"]["1"]) == 3
    assert {row["n"] for row in document["fix_node"]["1"]} == {str(n.tip) for n in frame.pile_nodes}
    assert len(document["fix_member"]["1"]) == 15  # three rows of five layers


def test_the_bytes_are_the_same_every_time(results):
    assert dump_json(build_frameweb(results[0])) == dump_json(build_frameweb(results[0]))
    assert json.loads(dump_json(build_frameweb(results[0])))["dimension"] == 2




def broken(document, change):
    found = deepcopy(document)
    change(found)
    return found


@pytest.mark.parametrize("change, message", [
    (lambda d: d["fix_member"]["1"][0].update(length=30.0), "区間の長さの合計.*が部材長.*を超えます"),
    (lambda d: d["fix_member"]["1"][0].update(tx=0, ty=0), "ばね値は 0 以上で、成分のない行は書きません"),
    (lambda d: d["fix_member"]["1"][0].update(ty=-1), "ばね値は 0 以上"),
    (lambda d: d["fix_member"]["1"][0].update(length=0), "正の有限の数値が必要です"),
    (lambda d: d["fix_member"]["1"][0].update(tz=5), "2次元のモデルでは null です"),
    (lambda d: d["fix_member"]["1"][0].update(m="99"), "存在する番号（文字列）が必要です"),
    (lambda d: d["fix_member"]["1"][1].update(row=7), "行番号 2 が必要です"),
    (lambda d: d["fix_member"].pop("2"), "fix_node と同じ番号のばねの組が必要です"),
    (lambda d: d["load"]["1"].pop("fix_member"), "荷重ケースごとに分布ばねの組を指します"),
    (lambda d: d["load"]["1"].update(fix_member=9), "存在する番号（整数）が必要です"),
    (lambda d: d.pop("fix_member"), r"fix_node\.1\[1\]\.tx: 正の有限の数値が必要です"),  # a direct frame has no null spring
    (lambda d: d["fix_node"]["1"][0].update(ty=None), "有限の数値が必要です"),
    (lambda d: d["fix_node"]["1"][0].update(tx=1), "ばね値 1 は FrameWeb では固定支点を意味します"),
])
def test_a_document_that_breaks_a_rule_of_the_pile_springs_is_refused(document, change, message):
    with pytest.raises(InputError, match=message):
        validate_frameweb(broken(document, change))
