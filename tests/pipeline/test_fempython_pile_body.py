"""What the pile body check of a steel pipe pile reads of the PIK of FEMPython (decision 89): the section forces of the pile members, point
by point, in the pickup of the 安全性（破壊）."""

import pytest

from webpier.calc.pile_body import PileResponseError, PointForces, SectionForce
from webpier.pipeline.fempython import member_forces

PIK = """PickUpNo,着目力,部材No,最大CaseNo,最小CaseNo,着目点,着目点距離,最大Md,最大Vd,最大Nd,最小Md,最小Vd,最小Nd
    1    M    7    3    4 ITAN     0.000    393.31    326.72 -10430.30   -450.63   -326.35  -7114.73
    1    M    7    5    6    1     3.750    182.06    -53.18  -6778.47   -217.18     44.71  -9855.98
    1    S    7    7    8 JTAN    26.500      0.00     12.50   -100.00      0.00     -9.50   -200.00
    1    N    9    9   10    2    11.250     47.55     19.12  -5669.39    -46.92    -20.27  -7122.56
    1    N    5    9   10    2    11.250     47.55     19.12  -5669.39    -46.92    -20.27  -7122.56
    2    M    7    1    2    1     3.750      1.00      2.00      3.00      4.00      5.00      6.00
"""


def test_the_section_forces_of_the_pile_members_are_the_lines_of_the_pickup_of_each_point():
    found = member_forces(PIK.encode("utf-8"), [7, 9], 1)
    assert sorted(found) == [7, 9]  # member 5 is no pile, pickup 2 is another pickup, the header is skipped
    assert found[7] == (
        PointForces("M", "ITAN", 0.0, SectionForce(393.31, 326.72, -10430.30, 3), SectionForce(-450.63, -326.35, -7114.73, 4)),
        PointForces("M", "1", 3.75, SectionForce(182.06, -53.18, -6778.47, 5), SectionForce(-217.18, 44.71, -9855.98, 6)),
        PointForces("S", "JTAN", 26.5, SectionForce(0.0, 12.5, -100.0, 7), SectionForce(0.0, -9.5, -200.0, 8)))
    assert [item.focus for item in found[9]] == ["N"]
    assert member_forces(PIK.encode("utf-8"), [8], 1) == {8: ()}


@pytest.mark.parametrize("content, message", [
    (PIK.replace("-6778.47", "       nan").encode("utf-8"), "有限でない断面力"),
    (PIK.replace("    1    S    7    7", "    1    S    x    7").encode("utf-8"), "PIK を読めません"),
    (b"\xff\xfe\x00", "PIK を読めません"),
])
def test_a_pik_whose_section_forces_cannot_be_read_is_named(content, message):
    with pytest.raises(PileResponseError, match=message):
        member_forces(content, [7, 9], 1)
