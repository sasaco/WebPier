"""The Aggre-SE project XML of both directions (decision 49).

The expected files (tests/fixtures/example2/aggrese, notes.md there) are the Example2 projects P1_線路.xml and
P1_直角.xml, with the Case arrays cut to 50 and the DB1 paths of WebPier's JRSNAP folders, with the check items of each
Case and the DB1 names copied from the owner's project (decision 76), saved again by Aggre-SE itself: the conditions are Example2's and the format is that of the Aggre-SE the writer follows. Other values are
read back from the XML with ElementTree, independent of the writer.
"""

from dataclasses import replace
import xml.etree.ElementTree as ET

import pytest

from jrsnap_support import FIXTURES, document, model
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.export.aggrese import BATCH_VERSION, ProjectError, build_project, databases, write_project
from webpier.export.aggrese.writer import CASES, document as project_document
from webpier.inputs import parse_input

EXPECTED = FIXTURES / "example2" / "aggrese"
FOLDERS = {"longitudinal": "線路方向", "transverse": "線路直角方向"}


def names(stem, cases, suffix="DB1"):
    return [f"{stem}(Case{case}_ρm10_αf1_正向).{suffix}" for case in cases]


# JRSNAP's names of the Cases (decision 76): the 照査パターン (ρm, αf) of each track, the down track 逆向.
PATTERNS = ("ρm10_αf1", "ρm12_αf1", "ρm10_αf2", "ρm12_αf2")
ANALYZED = {"longitudinal": [f"{pattern}_正向" for pattern in PATTERNS],
            "transverse": [f"{pattern}_{way}" for way in ("正向", "逆向") for pattern in PATTERNS]}


def analyzed(direction):
    stem = FOLDERS[direction]
    return [f"{stem}(Case{case}_{name}).DB1" for case, name in enumerate(ANALYZED[direction], 1)]


def write(direction, data=None, **changes):
    built = model(direction, data, **changes)
    pier = parse_input(data if data is not None else document(**changes))
    project = build_project(built, pier)
    stem = FOLDERS[direction]
    found = databases(f"{stem}_JRSNAP", analyzed(direction), len(project.cases))
    return project, write_project(project, found)


def tree(data):
    return ET.fromstring(data.decode("cp932").replace('encoding="utf-16"', ""))


def items(root, path):
    return [item.text for item in root.find(path)]


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
def test_the_example2_projects_as_aggre_se_saves_them(direction):
    _, data = write(direction)
    assert data == (EXPECTED / f"{FOLDERS[direction]}.xml").read_bytes()


def test_the_values_that_follow_from_the_ndu():
    """La of the column-base M-θ member (mm) and the FootInfo joint: Example2 7600 / 7 and 10350 / 8."""
    for direction, la, joint, cases in (("longitudinal", 7600, 7, 4), ("transverse", 10350, 8, 8)):
        project, data = write(direction)
        assert (project.shear_span.value, project.footing_joint, len(project.cases)) == (la, joint, cases)
        root = tree(data)
        assert items(root, "Element/_dgLimitLevel_La") == [str(la)]
        assert root.find("Foundation/基礎照査/clsFoundation/dgDispAtPoint/pointNo").text == str(joint)
        paths = items(root, "SNAP/SnapDBPath")
        stem = FOLDERS[direction]
        assert paths[:cases] == [f"{stem}_JRSNAP/{name}" for name in analyzed(direction)]
        assert len(paths) == CASES and set(paths[cases:]) == {None}
        assert root.find("Version").text == BATCH_VERSION


# Decision 76: ①..⑨ of each 照査パターン (1.0, 1)(1.2, 1)(1.0, 2)(1.2, 2), whichever way it is pushed:
# ①② all, ③ but (1.0, 2), ④ ρm 1.2, ⑤ none, ⑥ (1.0, 1), ⑦⑧⑨ αf 1.
CHECKED = ["1111", "1111", "1101", "0101", "0000", "1000", "1100", "1100", "1100"]


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
def test_the_check_items_of_each_case_are_those_of_its_pattern(direction):
    project, data = write(direction)
    root = tree(data)
    tracks = len(project.cases) // 4
    for item, checked in enumerate(CHECKED, 1):
        expected = ["-1" if flag == "1" else "0" for flag in checked * tracks]
        assert items(root, f"CaseName/dgCaseList_{item}") == expected + ["0"] * (CASES - len(expected))


def test_a_pattern_without_check_items_is_an_error():
    built = model("longitudinal")
    other = replace(built.combinations[1], rho_m=Printed(1.1, 1, ""))
    with pytest.raises(ValueError, match="組合せ 2 の照査パターン ρm=1.1・αf=1.0 の照査項目がありません"):
        build_project(replace(built, combinations=(built.combinations[0], other)), parse_input(document()))


@pytest.mark.parametrize("region,ground,chiiki,jiban", [
    ("A地域", "G0地盤", 0, 0), ("B地域", "G5地盤", 1, 5), ("C地域", "G3地盤", 2, 3)])
def test_the_seismic_design_conditions_are_the_radio_buttons(region, ground, chiiki, jiban):
    _, data = write("longitudinal", **{"耐震設計条件/地域別": region, "耐震設計条件/地盤区分": ground})
    root = tree(data)
    assert items(root, "Requirement/_rbChiiki") == ["true" if i == chiiki else "false" for i in range(3)]
    assert items(root, "Requirement/_rbJIban") == ["true" if i == jiban else "false" for i in range(10)]


@pytest.mark.parametrize("key", ["地域別", "地盤区分"])
def test_a_blank_seismic_design_condition_is_an_input_error(key):
    data = document(**{f"耐震設計条件/{key}": None})
    with pytest.raises(InputError, match=f"耐震設計条件.{key}: 値が必要です"):
        build_project(model("longitudinal", data), parse_input(data))


def test_the_project_has_one_nonlinear_member():
    built = model("longitudinal")
    rigid = tuple(replace(element, nonlinear=False) for element in built.elements)
    with pytest.raises(InputError, match="JRSNAP の非線形部材が0個です"):
        build_project(replace(built, elements=rigid), parse_input(document()))


def test_a_shear_span_with_a_decimal_is_written_as_xmlserializer_writes_it():
    built = model("longitudinal")
    built = replace(built, section=replace(built.section, shear_span=Printed(7600.5, 1, "mm")))
    project = build_project(built, parse_input(document()))
    found = [f"x/{name}" for name in analyzed("longitudinal")]
    assert items(tree(write_project(project, found)), "Element/_dgLimitLevel_La") == ["7600.5"]


def test_the_databases_are_found_by_their_case_number():
    found = ["m(Case10_ρm10_αf1_正向).db1", *names("m", (2, 1)), *names("m", (1, 2), "OUT"),
             *(f"m(Case{case}_ρm10_αf1_正向).DB1" for case in range(3, 10))]
    assert databases("f", found, 10) == tuple(f"f/m(Case{case}_ρm10_αf1_正向).{'db1' if case == 10 else 'DB1'}"
                                              for case in range(1, 11))


@pytest.mark.parametrize("found,cases,message", [
    (names("m", (1,)), 2, "Case1〜2 の DB1 がそろっていません"),
    (names("m", (1, 2)), 1, "Case1〜1 の DB1 がそろっていません"),
    ([*names("m", (1,)), "n(Case1_ρm10_αf1_正向).DB1"], 1, "Case1 の DB1 が2つあります"),
    (["m.DB1", "m(Case1).DB1"], 1, "Case1〜1 の DB1 がそろっていません"),
])
def test_the_databases_must_be_one_per_case(found, cases, message):
    with pytest.raises(ProjectError, match=message):
        databases("f", found, cases)


def test_the_document_needs_one_database_per_case():
    project = build_project(model("transverse"), parse_input(document()))
    with pytest.raises(ValueError, match="DB1 が1件です（Case は8件）"):
        project_document(project, ["f/a.DB1"])
