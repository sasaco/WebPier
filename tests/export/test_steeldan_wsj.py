"""The WSJ of the pile body check of a steel pipe pile (decision 89): what SteelDan reads of it (Capacita/SteelDan WsjReader and
PipePileVerifier; the real runner reads the document in the real-runner test of the pile body)."""

import json

from webpier.calc.pile_body import Case, PileRowForces, PileSteel, SectionForce
from webpier.core.printed import Printed
from webpier.export.steeldan import build_wsj, write_wsj

STEEL = PileSteel("SKK490", Printed(315.0, 0, "N/mm2"), Printed(180.0, 0, "N/mm2"), Printed(798.0, 1, "mm"), Printed(17.0, 1, "mm"))
ROWS = [PileRowForces(1, 7, 3, {Case.MOMENT: SectionForce(139.1, 31.2, -1572.6, 16), Case.SHEAR: SectionForce(97.3, 154.3, -3784.8, 18),
                                Case.AXIAL: SectionForce(-75.4, 133.0, -4609.4, 4)}, {case: 3.75 for case in Case}),
        PileRowForces(2, 9, 2, {Case.MOMENT: SectionForce(1.0, 2.0, -3.0, 1), Case.SHEAR: SectionForce(4.0, 5.0, -6.0, 2),
                                Case.AXIAL: SectionForce(7.0, 8.0, -9.0, 3)}, {case: 1.0 for case in Case})]


def test_each_pile_row_is_a_member_and_a_point_with_a_pipe_section_and_its_piles():
    document = build_wsj(STEEL, ROWS)
    assert (document["format"], document["schema_version"], document["pickup_data"]) == ("wsj", "1.0.0", None)
    assert [(member["m_no"], member["shape"], member["n"], member["g_id"]) for member in document["members"]] == [
        (1, "Pipe", 3, "1"), (2, "Pipe", 2, "1")]
    assert [(point["index"], point["m_no"]) for point in document["points"]] == [(1, 1), (2, 2)]
    assert [(section["index"], section["shape"], section["h"], section["t"]) for section in document["sections"]] == [
        (1, "Pipe", 798.0, 17.0), (2, "Pipe", 798.0, 17.0)]
    assert document["crack"] == [] and document["fatigues"]["fatigue_list"] == []


def test_the_factors_of_the_slot_one_and_the_strength_of_the_pipe_are_what_the_check_reads():
    safety = build_wsj(STEEL, ROWS)["safety"]
    slot = safety["safety_factor"]["1"][1]
    assert (slot["ri"], slot["rb_T"], slot["rb_C"], slot["rb_S"], slot["rs"]) == (1.2, 1.05, 1.05, 1.05, 1.05)
    assert len(safety["safety_factor"]["1"]) == 3  # the slots 0 and 2 are placeholders
    bands = safety["material_steel"]["1"]
    assert [(band["separate"], band["fsyk"], band["fsvyk"]) for band in bands] == [(16, 315.0, 180.0), (40, 315.0, 180.0), (75, 315.0, 180.0)]


def test_the_forces_are_the_cases_6_7_8_of_the_manual_mode_with_the_compression_positive():
    document = build_wsj(STEEL, ROWS)
    assert document["force"][0] == {
        "index": 1, "6_Md": 139.1, "6_Vd": 31.2, "6_Nd": 1572.6, "6_Mt": 0.0, "7_Md": 97.3, "7_Vd": 154.3, "7_Nd": 3784.8,
        "7_Mt": 0.0, "8_Md": -75.4, "8_Vd": 133.0, "8_Nd": 4609.4, "8_Mt": 0.0}
    calc = document["calc"]
    assert calc["calculate_pipe_pile"] is True and calc["print_safety_ratio_checked"] is True
    assert not any(calc[key] for key in ("calculate_shear_force", "calculate_torsional_moment", "print_calculate_checked",
                                         "print_section_force_checked", "print_summary_table_checked"))


def test_the_file_is_utf8_json_with_a_final_newline_and_the_same_every_time():
    content = write_wsj(STEEL, ROWS)
    assert content.endswith(b"\n") and json.loads(content.decode("utf-8")) == build_wsj(STEEL, ROWS)
    assert write_wsj(STEEL, ROWS) == content
