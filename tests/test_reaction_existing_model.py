"""Transverse inertia uses the existing dead, snow and centroid inputs."""

import pytest

from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import SpanInput, parse_reaction_input
from test_reaction_load_rules import example2_horizontal_input


def test_span_model_has_no_separate_transverse_inertia_input():
    assert "transverse_earthquake" not in SpanInput.__dataclass_fields__


def test_transverse_inertia_uses_existing_inputs_even_with_obsolete_extra_data():
    data = example2_horizontal_input()
    for side, hs in (("起点側", 2.35), ("終点側", 3.45)):
        span = data["上部構造"][side]
        span["重心高_hs"] = hs
        span["直角地震時慣性力"] = {
            "シェルター固定死荷重_D1": 100,
            "シェルター水平反力": 200,
            "シェルター転倒モーメント": 900,
        }
    result = calculate_reactions(parse_reaction_input(data))
    for side, force, hs in (("B", 6720, 2.35), ("C", 2370, 3.45)):
        detail = result["transverse"][6][side]
        assert detail["force"] == force
        assert detail["height"] == hs
        assert detail["moment"] == pytest.approx(force * hs)
        assert result["macro_handoff_single"]["直角荷重強度"][6][f"R{side}"] == force
        assert result["macro_handoff_single"]["直角荷重位置"][6][f"R{side}"] == pytest.approx(hs)
