"""The NDU of the 応答変位法 of a pile foundation (decision 97): the 地盤変位 at the pile nodes, as JRSNAP_Input saves it.

The records follow JRSNAP_Input's ``mdlDataFile`` (``ELoadNum``, ``ELoadRow`` and one ``ELoadInfo<i>=from,to,EDSPX,ALF`` a
row, a single node with ``from`` blank) and the sample R-7 C1 応答変位法 of Batch's manual data: the analysis is the load
increment (``DataInfo`` second field 2) up to the step of the 最大応答震度, at which the 地盤変位 is all on (LiMiT5 = LiMiT6),
and the combination puts the 地盤変位 on (``SNAPConb`` ELoad 1). The bytes JRSNAP then writes (the ED block) were checked
against its JOT link on the real S_ANALYSIS (decision 97 最初の実験).
"""

from dataclasses import replace
from decimal import Decimal

import pytest
from pile_ndu_support import printed, sample_model

from webpier.core.errors import InputError
from webpier.export.jrsnap.model import Combination
from webpier.export.jrsnap.pile_model import EDSPX, GroundLoad
from webpier.export.jrsnap.pile_records import records
from webpier.export.jrsnap.writer import line, write_pile_ndu


def written(model):
    return dict((key, line((key, values)).partition("=")[2]) for key, values in records(model))


def with_ground(model=None, steps=430, inertia=Decimal("0.30"), reverse=False):
    model = model or sample_model()
    combination = Combination(rho_m=printed(1, 1), alpha_f=printed(1, 1), coefficients=(inertia,), reverse=reverse)
    return replace(model, combinations=(combination,),
                   ground=GroundLoad(steps, ((22, EDSPX(0.34073)), (23, EDSPX(-0.00512)))))


def test_the_analysis_is_the_load_increment_up_to_the_step_of_the_maximum_response():
    ours = written(with_ground())
    fields = ours["DataInfo"].split(",")
    assert fields[:9] == ["1", "2", " ", " ", "1000", "200", " ", "430", "430"]
    assert fields[18] == " "  # no target displacement
    assert written(sample_model())["DataInfo"].split(",")[:3] == ["1", "1", "200"]  # the inertia one is unchanged


def test_the_ground_displacement_is_one_row_a_node_with_the_alf_of_one():
    ours = written(with_ground())
    assert (ours["ELoadNum"], ours["ELoadRow"]) == ("2", "2")
    assert (ours["ELoadInfo1"], ours["ELoadInfo2"]) == (" ,22,0.34073,1", " ,23,-0.00512,1")
    assert "ELoadInfo1" not in written(sample_model())


def test_the_combination_puts_the_ground_displacement_on_with_its_coefficients():
    ours = written(with_ground(reverse=True))
    assert ours["SNAPConb1"].split(",")[2:5] == ["1", "0", "0.3"]  # 逆向, no JOT link, ν of the inertia
    assert ours["SNAPConb1"].split(",")[-2:] == ["1", "0"]
    assert ours["ConbAlpf1"] == "0.3"
    assert written(sample_model())["SNAPConb1"].split(",")[-2:] == ["0", "0"]


def test_the_displacement_must_be_at_joints_in_order_and_the_steps_within_the_divisions():
    model = with_ground()
    write_pile_ndu(model)
    for ground, message in ((GroundLoad(430, ((23, EDSPX(0)), (22, EDSPX(0)))), "地盤変位の節点"),
                            (GroundLoad(430, ((999, EDSPX(0)),)), "地盤変位の節点"),
                            (GroundLoad(0, ((22, EDSPX(0)),)), "地盤変位の最終載荷ステップ"),
                            (GroundLoad(1001, ((22, EDSPX(0)),)), "地盤変位の最終載荷ステップ")):
        with pytest.raises(InputError, match=message):
            write_pile_ndu(replace(model, ground=ground))
