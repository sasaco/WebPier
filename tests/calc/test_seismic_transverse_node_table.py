"""0720 node table: the girder levels are named, the control node is not (decision 81)."""

from reaction_support import pier
from seismic_transverse_support import seismic
from webpier.reporting.stages.frame_report import node_table


def names(p) -> list[str]:
    return [row[3] for row in node_table(seismic(p).frame, springs=False).rows[1:4]]


def test_girders_at_different_heights_name_each_girder_only():
    # The end girder at 0.500 + 2.650 = 3.150 is node 1, the origin's 2.750 node 2 and the control node (the origin
    # girder, the larger inertia force) is not named.
    assert names(pier(**{"上部構造/終点側/高さ/h1": 0.5})) == ["終点側の桁", "起点側の桁", "はり天端"]


def test_girders_at_the_same_height_print_as_before():
    assert names(pier())[0] == "起点側の桁・終点側の桁"  # Example2 node 1
