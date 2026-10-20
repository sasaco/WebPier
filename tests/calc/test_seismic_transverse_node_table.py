"""0720 node table: a control node apart from the girder levels is named (decision 65)."""

from reaction_support import pier
from seismic_transverse_support import seismic
from webpier.reporting.stages.frame_report import node_table


def names(p) -> list[str]:
    return [row[3] for row in node_table(seismic(p).frame, springs=False).rows[1:4]]


def test_girders_at_different_heights_name_the_control_node():
    assert names(pier(**{"上部構造/終点側/高さ/h1": 0.5})) == ["終点側の桁", "制御節点", "起点側の桁"]


def test_girders_at_the_same_height_print_as_before():
    assert names(pier())[0] == "起点側の桁・終点側の桁"  # Example2 node 1
