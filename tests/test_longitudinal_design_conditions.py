"""0610-only concrete conditions and the independent RcDan table contract."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, is_dataclass
import importlib
import json
from pathlib import Path
import re

import pytest

from src.inputs import InputError
from src.frame_model import build_frame_model
from src.reaction_inputs import parse_reaction_input


BASELINE = Path(__file__).parent / "fixtures" / "baseline_input.json"


def design_module():
    # Called by tests, so an unimplemented module fails a test, not collection.
    return importlib.import_module("src.longitudinal_design_conditions")


@pytest.fixture
def material_data():
    return {
        "鉄筋": {
            "梁": {"concrete_strength_mpa": 24},
            "柱": {"concrete_strength_mpa": 27},
            "フーチング": {"concrete_strength_mpa": 40},
        }
    }


@pytest.mark.parametrize("fck_mpa,expected_ec", [
    (18, 22e6), (24, 25e6), (30, 28e6), (40, 31e6),
    (50, 33e6), (60, 35e6), (70, 37e6), (80, 38e6),
    (21, 23.5e6), (27, 26.5e6), (35, 29.5e6), (45, 32e6),
    (55, 34e6), (65, 36e6), (75, 37.5e6),
    (12, 19e6), (100, 38e6),
])
def test_concrete_ec_table_interpolation_extrapolation_cap_and_units(fck_mpa, expected_ec):
    assert design_module().concrete_ec(fck_mpa) == pytest.approx(expected_ec, rel=0, abs=1e-8)


@pytest.mark.parametrize("bad", [None, True, False, "27", 0, -1, float("nan"), float("inf")])
def test_concrete_ec_rejects_invalid_strength_with_path(bad):
    with pytest.raises(InputError, match="fck_mpa"):
        design_module().concrete_ec(bad)


def test_parser_preserves_part_strength_modulus_and_provenance_without_mutation(material_data):
    original = deepcopy(material_data)
    result = design_module().parse_longitudinal_design_conditions(material_data)
    assert material_data == original
    assert is_dataclass(result) and not isinstance(result, type)
    for name, source_name, fck, ec in (
        ("beam", "梁", 24, 25e6),
        ("column", "柱", 27, 26.5e6),
        ("footing", "フーチング", 40, 31e6),
    ):
        material = getattr(result, name)
        assert is_dataclass(material) and not isinstance(material, type)
        assert material.fck == fck
        assert material.Ec == ec
        assert material.input_path == f"鉄筋.{source_name}.concrete_strength_mpa"
        assert "RcDan" in str(material.ec_source)
        assert "InformationGetter.cs" in str(material.ec_source)
        assert "GetLinear" in str(material.ec_source)
        with pytest.raises(FrozenInstanceError):
            material.fck = 99
    with pytest.raises(FrozenInstanceError):
        result.beam = result.column


@pytest.mark.parametrize("part", ["梁", "柱", "フーチング"])
@pytest.mark.parametrize("bad", ["missing", None, True, False, "27", 0, -1, float("nan"), float("inf")])
def test_parser_rejects_invalid_part_strength_with_input_path(material_data, part, bad):
    path = f"鉄筋.{part}.concrete_strength_mpa"
    if bad == "missing":
        del material_data["鉄筋"][part]["concrete_strength_mpa"]
    else:
        material_data["鉄筋"][part]["concrete_strength_mpa"] = bad
    with pytest.raises(InputError, match=re.escape(path)):
        design_module().parse_longitudinal_design_conditions(material_data)


@pytest.mark.parametrize("missing_part", ["鉄筋", "梁", "柱", "フーチング"])
def test_parser_rejects_missing_material_container_with_path(material_data, missing_part):
    if missing_part == "鉄筋":
        del material_data["鉄筋"]
        path = "鉄筋"
    else:
        del material_data["鉄筋"][missing_part]
        path = f"鉄筋.{missing_part}"
    with pytest.raises(InputError, match=re.escape(path)):
        design_module().parse_longitudinal_design_conditions(material_data)


def test_existing_0600_input_parser_still_accepts_null_material_strengths():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    expected = parse_reaction_input(data)
    data["鉄筋"] = {
        "梁": {"concrete_strength_mpa": None},
        "柱": {"concrete_strength_mpa": None},
        "フーチング": {"concrete_strength_mpa": None},
    }
    original = deepcopy(data)
    assert parse_reaction_input(data) == expected
    assert data == original


def frame_with_parapet(direction):
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    geometry = asdict(parse_reaction_input(data).geometry)
    geometry.update(h1=0.5, h2=1, h3=0.5, h4=3, h5=0, h6=2,
                    b1=3, b2=0.5, b3=1, b4=0, b5=0,
                    w1=6, w2=1, w3=2, w4=0, w5=0)
    fck = 24 if direction == "b" else 25
    legacy = {
        "nodes": [
            {"id": 1, "x": 0, "y": 6.5, "source_row": 81},
            {"id": 2, "x": 0, "y": 2, "source_row": 82},
            {"id": 3, "x": 0, "y": 1, "source_row": 83},
            {"id": 4, "x": 0, "y": 0, "source_row": 84},
        ],
        "section": {"width": 6.5, "depth": 1.75, "area": 11.375, "inertia": 2.90299, "footing": "rigid"},
        "materials": {"body": {"fck": fck, "Ec": 25e6}, "footing": {"fck": fck, "Ec": 25e6}},
        "springs": {"long_term": {"Kv": 11, "Ks": 12, "Kr": 13},
                    "short_term": {"Kv": 21, "Ks": 22, "Kr": 23}},
        "shape_eccentricity": 0.125,
    }
    return build_frame_model(geometry, legacy, direction)


def without_materials(frame):
    frame = deepcopy(frame)
    frame.pop("materials")
    frame.pop("material_provenance", None)
    for member in frame["members"]:
        member.pop("material_ref")
    return frame


def test_apply_materials_maps_actual_regions_and_preserves_all_other_frame_data(material_data):
    module = design_module()
    conditions = module.parse_longitudinal_design_conditions(material_data)
    frame = frame_with_parapet("b")
    original = deepcopy(frame)
    applied = module.apply_longitudinal_materials(frame, conditions)
    assert frame == original
    assert set(applied["materials"]) == {"beam", "column", "footing"}
    for name, expected_fck, expected_ec in (("beam", 24, 25e6), ("column", 27, 26.5e6), ("footing", 40, 31e6)):
        assert applied["materials"][name]["fck"] == expected_fck
        assert applied["materials"][name]["Ec"] == expected_ec
    elastic = {member["region"]: member["material_ref"] for member in applied["members"]
               if member["behavior"] == "elastic"}
    assert elastic == {"h2": "beam", "h3": "beam", "h4": "column", "h1": "column"}
    rigid = [member for member in applied["members"] if member["behavior"] == "rigid"]
    assert {member["region"] for member in rigid} == {"footing_top_to_centroid", "footing_centroid_to_bottom", "parapet_arm"}
    assert all(member["material_ref"] is None for member in rigid)
    assert without_materials(applied) == without_materials(original)
    # The returned frame must own its material maps rather than exposing shared
    # mutable state to the caller or the frozen input conditions.
    applied["materials"]["column"]["fck"] = 99
    assert frame == original
    assert conditions.column.fck == 27


def test_h1_material_inheritance_is_explicit_compatibility_provenance(material_data):
    module = design_module()
    frame = module.apply_longitudinal_materials(
        frame_with_parapet("b"), module.parse_longitudinal_design_conditions(material_data),
    )
    h1 = frame["material_provenance"]["h1"]
    assert h1["policy"] == "compatibility_inheritance"
    assert h1["legacy_material_ref"] == "body"
    assert h1["material_ref"] == "column"
    assert h1["dedicated_input"] is False
    assert h1["input_path"] == "鉄筋.柱.concrete_strength_mpa"


def test_longitudinal_material_application_does_not_change_shared_0620_builder(material_data):
    before = frame_with_parapet("w")
    module = design_module()
    module.apply_longitudinal_materials(
        frame_with_parapet("b"), module.parse_longitudinal_design_conditions(material_data),
    )
    after = frame_with_parapet("w")
    assert after == before
    assert after["materials"] == {"body": {"fck": 25, "Ec": 25e6}, "footing": {"fck": 25, "Ec": 25e6}}
    assert all(member["material_ref"] == ("body" if member["behavior"] == "elastic" else None)
               for member in after["members"])
    assert "material_provenance" not in after
