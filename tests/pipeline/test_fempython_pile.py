"""What the 基礎の照査 of a pile foundation reads of FEMPython's files (decision 89): the axial force at the head of the pile
members in the PIK and the displacement of the footing top in the displacement pickup CSV."""

import pytest

from webpier.calc.pile_check import Extreme, HeadForce, PileResponseError
from webpier.pipeline.fempython import footing_displacements, head_forces

PIK = """PickUpNo,着目力,部材No,最大CaseNo,最小CaseNo,着目点,着目点距離,最大Md,最大Vd,最大Nd,最小Md,最小Vd,最小Nd
    1    M    7    3    3 ITAN     0.000    393.31    326.72 -10430.30   -450.63   -326.35  -7114.73
    1    N    7    4    3 ITAN     0.000   -274.89   -164.85  -6679.88    393.31    326.72 -10430.30
    1    N    7    4    4    1     3.750   -274.89   -164.85  -6679.88    393.31    326.72 -10430.30
    1    N    9    2    3 ITAN     0.000    385.72    318.30   -6419.99   -452.36   -326.72 -10057.92
    1    N    5    2    3 ITAN     0.000    385.72    318.30   -6419.99   -452.36   -326.72 -10057.92
    2    N    7    5    5 ITAN     0.000   -283.94   -164.83   150.50   234.50    165.17  -8644.57
"""


def test_the_head_force_is_the_n_line_of_the_itan_point_of_each_member_in_each_pickup():
    found = head_forces(PIK.encode("utf-8"), [7, 9])
    assert found == {(1, 7): HeadForce(-6679.88, 4, -10430.30, 3), (1, 9): HeadForce(-6419.99, 2, -10057.92, 3),
                     (2, 7): HeadForce(150.5, 5, -8644.57, 5)}  # member 5 is no pile; M lines and other points are skipped


@pytest.mark.parametrize("content, message", [
    (PIK + PIK.splitlines()[2] + "\n", "ピックアップ 1 の部材 7 の杭頭が重複"),
    (PIK.replace("-10430.30   -450.63", "      nan   -450.63", 1).replace("-6679.88    393.31    326.72 -10430.30",
                                                                        "-6679.88    393.31    326.72       nan"),
     "有限でありません"),
    (PIK.replace("    2    N    7    5    5", "    x    N    7    5    5"), "PIK を読めません"),
])
def test_a_pik_that_cannot_be_read_is_named(content, message):
    with pytest.raises(PileResponseError, match=message):
        head_forces(content.encode("utf-8"), [7, 9])


def test_a_pik_that_is_not_text_is_named():
    with pytest.raises(PileResponseError, match="PIK を読めません"):
        head_forces(b"\xff\xfe\x00", [7])


HEADER = ("pickup_id,focus_component,node_id,max_combine_id,min_combine_id,max_dx (unspecified),max_dy (unspecified),"
          "max_dz (unspecified),max_rx (rad),max_ry (rad),max_rz (rad),min_dx (unspecified),min_dy (unspecified),"
          "min_dz (unspecified),min_rx (rad),min_ry (rad),min_rz (rad)")
ROWS = [
    "1,dx,4,3,5,0.002,0.001,0,0,0,0.0001,-0.0035,0.001,0,0,0,-0.0002",
    "1,dy,4,3,5,0.009,0.009,0,0,0,0.0009,-0.009,0.009,0,0,0,-0.0009",
    "1,rz,4,6,7,0.0001,0.0001,0,0,0,0.0004,-0.0001,0.0001,0,0,0,-0.0003",
    "1,dx,7,3,5,0.5,0.001,0,0,0,0.0001,-0.5,0.001,0,0,0,-0.0002",
    "1,dx,generated:7:S1,3,5,0.5,0.001,0,0,0,0.0001,-0.5,0.001,0,0,0,-0.0002",
    "2,dx,4,8,9,0.004,0.001,0,0,0,0.0001,-0.001,0.001,0,0,0,-0.0002",
    "2,rz,4,10,11,0.0001,0.0001,0,0,0,0.0001,-0.0001,0.0001,0,0,0,-0.0005",
]


def csv(*rows, header=HEADER):
    return "\n".join([header, *rows]).encode("utf-8")


def test_the_extremes_of_the_footing_top_are_the_largest_absolute_values_of_dx_and_rz_in_each_pickup():
    found = footing_displacements(csv(*ROWS), 4)
    assert found == {(1, "dx"): Extreme(0.0035, 5), (1, "rz"): Extreme(0.0004, 6),  # the smaller side is dropped
                     (2, "dx"): Extreme(0.004, 8), (2, "rz"): Extreme(0.0005, 11)}


@pytest.mark.parametrize("content, message", [
    (csv(*ROWS, ROWS[0]), "ピックアップ 1（dx）の節点 4 が重複"),
    (csv(ROWS[0].replace("0.002,", "nan,", 1)), "有限でない変位"),
    (csv(ROWS[0].replace("0.002,", "x,", 1)), "変位の CSV を読めません"),
    (csv(ROWS[0], header=HEADER.replace("max_rz (rad)", "max_ry2 (rad)", 1).replace("max_ry (rad)", "max_ry3 (rad)")), "変位の CSV を読めません"),
    (b"", "変位の CSV を読めません"),
    (b"\xff\xfe\x00", "変位の CSV を読めません"),
])
def test_a_displacement_csv_that_cannot_be_read_is_named(content, message):
    with pytest.raises(PileResponseError, match=message):
        footing_displacements(content, 4)
