"""The Aggre-SE project XML of piles (decision 94).

``tests/fixtures/aggrese/pile_s.xml`` is the project the JRSNAP sample 01_サンプル(V53)：RC橋脚L ships with (a wall pier on 8
場所打ち杭), Aggre-SE's own file: the owner's conditions for that sample. The project WebPier writes for the model of the same
sample (``pile_ndu_support.sample_model``) is compared with it item by item. What the two share is what the piles need of the
XML: the nonlinear members (the column, then a member of the 杭 type for each section of the piles, with their shear span,
formula and end support), the reaction at the head of each pile row, the displacement at the footing top, the 30 rows of the
displacement table and the blank limit values of the direct foundation. They differ only where the owner's sample has its own
choice of conditions, which WebPier takes from the Example2 projects (decision 49) or its own rules:

- the namespace order of the root and ``Version`` (Aggre-SE 5.3.0.0 saved the sample; the writer follows 5.3.0.1);
- the check items of each Case (decision 76: WebPier's by 照査パターン, the sample's are the owner's, and ⑧ is never checked);
- the type of the column (the sample's wall pier is 梁, WebPier's is 柱) and the names and limits of the types;
- the spectrum, 地盤区分, 製品 and the 着目点 of the 要求性能;
- ``sdtFilePath`` and the limit values of the piles, which the runner reads from the .sdr it is given (``--sdr``);
- the 段落し情報 of the sample (WebPier makes no check of it, ⑧ off).
"""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from jrsnap_support import document
from pile_ndu_support import sample_model
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.export.aggrese import ProjectError, build_pile_project, ndu_databases, write_project
from webpier.export.aggrese.project import CHECKS, LIQUEFACTION_CHECKS, PILE_ANCHOR_BAR
from webpier.export.jrsnap.model import Combination
from webpier.export.jrsnap.pile_model import COLUMN
from webpier.inputs import parse_input
from webpier.inputs.choices import GROUND_CLASSES, REGIONS

SAMPLE = Path(__file__).parents[1] / "fixtures" / "aggrese" / "pile_s.xml"
STEM = "線路方向"


def pier():
    return parse_input(document())


def combinations(*patterns):
    return tuple(Combination(rho_m=Printed(rho, 1, ""), alpha_f=Printed(alpha, 1, ""), coefficients=(1,)) for rho, alpha in patterns)


def built(*patterns):
    model = replace(sample_model(), combinations=combinations(*(patterns or ((1.0, 1.0), (1.2, 1.0)))))
    return model, build_pile_project([model], pier())


def tree(data):
    return ET.fromstring(data.decode("cp932").replace('encoding="utf-16"', ""))


def items(root, path):
    return [item.text for item in root.find(path)]


def written(patterns=((1.0, 1.0), (1.2, 1.0))):
    model, project = built(*patterns)
    names = [f"{STEM}(Case{case}_a).DB1" for case in range(1, len(project.cases) + 1)]
    return project, tree(write_project(project, ndu_databases("線路方向_JRSNAP", names, [(STEM, len(project.cases))])))


def sample():
    return tree(SAMPLE.read_bytes())


def foundation(root):
    return root.find("Foundation/基礎照査/clsFoundation")


def test_the_piles_are_what_the_sample_has():
    project, ours = written()
    theirs = sample()
    for path in ("dgReactAtPoint", "dgDispAtPoint", "dgDispAtPoints", "dgLimitValue1", "FoundationType"):
        assert ET.tostring(foundation(ours).find(path)) == ET.tostring(foundation(theirs).find(path)), path
    # reactions at the head of each row (the joint and the piles of the row in the depth), the displacement at the column's base
    assert [(row.head, row.piles) for row in project.pile_rows] == [(7, 3), (28, 2), (49, 3)]
    assert project.footing_joint == 3 and project.pile_sections == 2
    for path in ("_dgLimitLevel_SIJI", "_dgLimitLevel_VydType", "_dgLimitLevel_La"):
        assert items(ours, f"Element/{path}") == items(theirs, f"Element/{path}"), path
    assert ours.find("Element/dgLimitLevel_typeCount").text == theirs.find("Element/dgLimitLevel_typeCount").text == "3"
    assert items(ours, "Element/_dgLimitLevel_type")[1:] == items(theirs, "Element/_dgLimitLevel_type")[1:] == ["4", "4"]
    assert items(ours, "Element/_dgLimitLevel_type")[0] == "2"  # 柱 (the sample's wall pier is 梁)
    assert len(items(ours, "SNAP/SnapDBPath")) == len(items(theirs, "SNAP/SnapDBPath")) == 50


def test_the_limits_of_the_piles_are_left_to_the_runner_and_the_anchor_to_no_check():
    _, ours = written()
    assert [item.text for item in foundation(ours).find("dgLimitValue0")] == [None] * 31
    assert foundation(ours).find("sdtFilePath").text is None
    assert [item.text for item in ours.find("PileAnchorBar/段落し情報/clsPileAnchorBar/dgMemberFirst")] == []
    # ⑧ 杭の段落し is checked in no Case: dgCaseList_8 is all 0
    assert set(items(ours, "CaseName/dgCaseList_8")) == {"0"}
    assert [items(ours, f"CaseName/dgCaseList_{number}")[0] for number in range(1, 10)] == [
        "-1", "-1", "-1", "0", "0", "-1", "-1", "0", "-1"]  # ρm 1.0, αf 1.0 (decision 76) without ⑧


def test_the_other_check_items_are_those_of_the_direct_foundation():
    model, project = built((1.0, 1.0), (1.2, 1.0), (1.0, 2.0), (1.2, 2.0))
    assert project.cases == tuple(tuple(item and index != PILE_ANCHOR_BAR for index, item in enumerate(checks))
                                  for checks in CHECKS.values())
    assert len(project.cases) == 4


def test_the_project_takes_the_conditions_of_the_input():
    model, project = built()
    design = pier().seismic_design
    assert project.shear_span == Printed(8000, 0, "mm")
    assert (project.region, project.ground_class) == (REGIONS.index(design.region),
                                                      GROUND_CLASSES.index(design.ground_class))
    assert project.piled and not replace(project, pile_rows=()).piled


def test_the_cases_of_two_ndus_follow_each_other():
    forward = replace(sample_model(), combinations=combinations((1.0, 1.0), (1.2, 1.0)))
    reverse = replace(sample_model(), combinations=combinations((1.0, 1.0)))
    project = build_pile_project([forward, reverse], pier())
    assert len(project.cases) == 3
    assert project.cases[2] == project.cases[0]
    names = [f"{STEM}(Case1_a).DB1", f"{STEM}(Case2_a).DB1", f"{STEM}_逆向(Case1_b).DB1"]
    assert ndu_databases("F", names, [(STEM, 2), (f"{STEM}_逆向", 1)]) == (
        f"F/{STEM}(Case1_a).DB1", f"F/{STEM}(Case2_a).DB1", f"F/{STEM}_逆向(Case1_b).DB1")


def test_two_ndus_with_other_piles_or_sections_are_refused():
    forward = sample_model()
    other = replace(forward, sections=forward.sections[:2])
    with pytest.raises(ValueError, match="杭の列と断面が同じではありません"):
        build_pile_project([forward, other], pier())
    moved = replace(forward, piles=forward.piles[:2])
    with pytest.raises(ValueError, match="杭の列と断面が同じではありません"):
        build_pile_project([forward, moved], pier())


def test_the_column_must_be_one_member():
    model = sample_model()
    two = replace(model, elements=tuple(replace(element, kind=COLUMN) if element.number in (1, 2) else element
                                        for element in model.elements))
    with pytest.raises(InputError, match="非線形部材（柱）が2個"):
        build_pile_project([two], pier())


def test_a_blank_seismic_design_is_an_input_error():
    data = document()
    data["耐震設計条件"]["地域別"] = None
    with pytest.raises(InputError, match="地域別"):
        build_pile_project([sample_model()], parse_input(data))


def test_the_databases_of_each_ndu_are_found_by_its_own_name():
    names = [f"線路直角方向(Case{n}_x).DB1" for n in (1, 2)] + [f"線路直角方向_逆向(Case{n}_y).db1" for n in (1, 2)] + [
        "線路直角方向(Case1_x).LOG"]
    found = ndu_databases("D", names, [("線路直角方向", 2), ("線路直角方向_逆向", 2)])
    assert found == ("D/線路直角方向(Case1_x).DB1", "D/線路直角方向(Case2_x).DB1", "D/線路直角方向_逆向(Case1_y).db1",
                     "D/線路直角方向_逆向(Case2_y).db1")


def test_a_missing_or_doubled_database_is_a_project_error():
    names = ["a(Case1_x).DB1", "a(Case1_y).DB1"]
    with pytest.raises(ProjectError, match="Case1 の DB1 が2つあります"):
        ndu_databases("D", names, [("a", 1)])
    with pytest.raises(ProjectError, match="Case1〜2 の DB1 がそろっていません"):
        ndu_databases("D", ["a(Case1_x).DB1"], [("a", 2)])
    with pytest.raises(ProjectError, match="b の Case1〜1"):
        ndu_databases("D", ["a(Case1_x).DB1"], [("a", 1), ("b", 1)])


def with_index(value):
    data = document()
    data["耐震設計条件"]["液状化指数"] = value
    return parse_input(data)


def test_the_cases_for_the_liquefaction_follow_the_ordinary_ones_and_are_flagged():
    """Decision 95: one Case for each NDU for the liquefaction, after the Cases of the other NDUs, checked ②③⑤⑦⑨ and flagged
    for the L2 earthquake of both spectra; the 液状化指数 is the input's."""
    forward = replace(sample_model(), combinations=combinations((1.0, 1.0), (1.2, 1.0)))
    reverse = replace(sample_model(), combinations=combinations((1.0, 1.0)))
    wet = replace(sample_model(), combinations=combinations((1.0, 1.0)))
    project = build_pile_project([forward, reverse], with_index("20<PL"), liquefied=[wet, wet])
    assert len(project.cases) == 5 and project.liquefaction_cases == (3, 4) and project.liquefaction_index == 1
    assert project.cases[3] == project.cases[4] == LIQUEFACTION_CHECKS
    assert tuple(index for index, item in enumerate(LIQUEFACTION_CHECKS) if item) == (1, 2, 4, 6, 8)
    assert build_pile_project([forward], with_index("5<PL<20"), liquefied=[wet]).liquefaction_index == 0
    plain = build_pile_project([forward], with_index(None))
    assert (plain.liquefaction_cases, plain.liquefaction_index) == ((), 0)


def test_the_xml_flags_the_cases_for_the_liquefaction_and_the_index():
    model = replace(sample_model(), combinations=combinations((1.0, 1.0)))
    project = build_pile_project([model], with_index("20<PL"), liquefied=[model])
    root = tree(write_project(project, ["a.DB1", "b.DB1"]))
    for tag in ("dgEkijoCase21", "dgEkijoCase2"):
        assert [index for index, flag in enumerate(items(root, f"Requirement/{tag}")) if flag == "-1"] == [1]
    assert set(items(root, "Requirement/dgEkijoCase1")) == {"0"}
    assert items(root, "Requirement/_rbEkijo") == ["false", "true"]
    assert [items(root, f"CaseName/dgCaseList_{number}")[1] for number in range(1, 10)] == [
        "0", "-1", "-1", "0", "-1", "0", "-1", "0", "-1"]
    plain = tree(write_project(build_pile_project([model], with_index("20<PL")), ["a.DB1"]))
    assert items(plain, "Requirement/_rbEkijo") == ["true", "false"] and set(items(plain, "Requirement/dgEkijoCase2")) == {"0"}


def test_a_case_for_the_liquefaction_needs_the_index():
    model = replace(sample_model(), combinations=combinations((1.0, 1.0)))
    with pytest.raises(InputError, match="液状化指数"):
        build_pile_project([model], with_index(None), liquefied=[model])
