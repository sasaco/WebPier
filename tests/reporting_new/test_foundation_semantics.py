"""0500 semantics: every printed number is the FoundationResult value at its digits.

The expected records are written here from the result and the input, apart
from the fixed wording, which is the reviewed old report (semantic/0500.json).
That fixture was mapped from the old PDF; its values are also Example2 04
pp.4-1..4-3 (kv 202988, Ks 4,262,769, Kr 52,218,663, ...), and 0500 did not
change, so it stays valid as the wording/order reference. Deliberate
differences from it are listed in DIFFERENCES and checked explicitly.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from foundation_report_cases import CASES, case, text
from webpier.core.printed import Printed

REFERENCE = Path(__file__).parents[1] / "fixtures" / "reporting" / "semantic" / "0500.json"

# Old record → why the new text differs. New records are listed with None.
DIFFERENCES = {
    "0500/bearing.normal": "Nγ/Nq は calc の印字桁（小数2桁）で書く。旧帳票と Example2 は 150・85",
    "0500/bearing.seismic": "同上",
    "0500/soil.surface": None,   # 表層厚 = H6 + H5 + min(df1, df2) を検算できるように印刷する（派生値）
    "0500/kv.soil_type": None,   # 決定18: 土質区分と係数・指数を印刷する
}


def squeeze(value: str) -> str:
    return re.sub(r"\s+", "", value)


def reference_records() -> dict[str, str]:
    records = {}
    for record in json.loads(REFERENCE.read_text(encoding="utf-8"))["records"]:
        value = record["source_text"]
        for atom in sorted(record.get("vector_atoms", []), key=lambda item: item["offset"], reverse=True):
            value = value[:atom["offset"]] + atom["text"] + value[atom["offset"]:]
        records[record["id"]] = squeeze(value)
    return records


LABELS = {"砂質土": "（砂質土）", "砂質土と粘性土の互層": "（砂質土，粘性土の互層）", "粘性土": "（粘性土）"}


def expected_records(result, pier) -> dict[str, str]:
    """Wording from the reviewed fixture, numbers from the result (never recomputed)."""
    reference = reference_records()
    out: dict[str, str] = {}

    def fixed(key: str) -> None:
        out["0500/" + key] = reference["0500/" + key]

    for key in ("title", "soil.heading", "soil.introduction", "soil.caption", "soil.header"):
        fixed(key)
    for index, layer in enumerate(pier.soil.layers):
        thickness = result.surface_thickness if index == 0 else layer.thickness
        out[f"0500/soil.row.{index}"] = "".join((
            layer.name, text(thickness), layer.soil_type, text(layer.n_value), text(layer.unit_weight_wet),
            text(layer.unit_weight_submerged), text(layer.friction_angle), text(layer.compressive_strength),
            text(layer.deformation_modulus, thousands=True)))
    sub = pier.substructure
    out["0500/soil.surface"] = (f"表層の層厚=H6+H5+min(df1,df2)={text(sub.h[6])}+{text(sub.h[5])}"
                                f"+min({text(sub.df1)},{text(sub.df2)})={text(result.surface_thickness)}m")
    fixed("bearing.heading")
    for key, label in (("normal", "地震時を除く"), ("seismic", "地震時")):
        out["0500/bearing." + key] = f"Nγ={text(result.n_gamma)},Nq={text(result.n_q)}{label}"
    for key in ("spring.heading", "vertical.heading", "kv.heading", "kv.sand", "kv.alternating", "kv.clay",
                "kv.definition.kv", "kv.definition.rho"):
        fixed(key)
    ed, width, area = text(result.deformation_modulus), text(result.width), text(result.area)
    out["0500/kv.definition.Ed"] = f"Ed：地盤の変形係数(={ed}kN/m2)"
    fixed("kv.definition.Bv")
    out["0500/kv.width"] = f"Bv=√Av(=√{area}={width}m)"
    out["0500/kv.area"] = f"Av：フーチング底面積(={text(result.b)}×{text(result.l)}={area}m2)"
    coefficient = repr(result.coefficient)
    out["0500/kv.soil_type"] = (f"支持層の土質区分：{result.soil_type}（kv={coefficient}ρgkEdBv"
                                f"{result.exponent_text}を用いる）")
    terms = (("long_term", "長期", result.long_term), ("short_term", "短期", result.short_term))
    for term, label, springs in terms:
        out[f"0500/kv.{term}.label"] = f"・{label}(ρgk={repr(springs.rho)})"
        out[f"0500/kv.{term}"] = (f"kv={coefficient}×{repr(springs.rho)}×{ed}×{width}{result.exponent_text}"
                                  f"={text(springs.kv)}kN/m3")
    for key in ("Kv.heading", "Kv.formula", "Kv.definition.Kv", "Kv.definition.kv", "Kv.definition.Av"):
        fixed(key)
    for term, label, springs in terms:
        out[f"0500/Kv.{term}.label"] = f"・{label}"
        out[f"0500/Kv.{term}"] = f"Kv={text(springs.kv)}×{area}={text(springs.Kv, thousands=True)}kN/m"
    for key in ("shear.heading", "ks.heading", "ks.formula", "ks.definition.ks", "ks.definition.lambda"):
        fixed(key)
    for term, label, springs in terms:
        out[f"0500/ks.{term}.label"] = f"・{label}"
        out[f"0500/ks.{term}"] = f"ks=1/3×{text(springs.kv)}={text(springs.ks)}kN/m3"
    for key in ("Ks.heading", "Ks.formula", "Ks.definition.Ks", "Ks.definition.ks", "Ks.definition.Av"):
        fixed(key)
    for term, label, springs in terms:
        out[f"0500/Ks.{term}.label"] = f"・{label}"
        out[f"0500/Ks.{term}"] = f"Ks={text(springs.ks)}×{area}={text(springs.Ks, thousands=True)}kN/m"
    for key in ("rotation.heading", "Kr.formula", "Kr.definition.Kr", "Kr.definition.kv", "Kr.definition.Iv"):
        fixed(key)
    for direction, first, cubed in (("longitudinal", result.l, result.b), ("transverse", result.b, result.l)):
        inertia = getattr(result, "inertia_" + direction)
        fixed(f"Kr.{direction}.heading")
        out[f"0500/Kr.{direction}.inertia"] = f"Iv={text(first)}×{text(cubed)}3/12={text(inertia)}m4"
        for term, label, springs in terms:
            out[f"0500/Kr.{direction}.{term}.label"] = f"・{label}"
            out[f"0500/Kr.{direction}.{term}"] = (f"Kr={text(springs.kv)}×{text(inertia)}="
                                                  f"{text(getattr(springs, 'Kr_' + direction), thousands=True)}kN・m/rad")
    return out


def actual_records(result, pier) -> dict[str, str]:
    from webpier.reporting.stages.foundation import semantic_records

    records = semantic_records(result, pier)
    ids = [record["id"] for record in records]
    assert len(ids) == len(set(ids))
    return {record["id"]: squeeze(record["text"]) for record in records}


def test_expectation_reproduces_the_reviewed_old_report_except_declared_differences():
    reference = reference_records()
    expected = expected_records(*case("current"))
    new = [key for key in expected if key not in reference]
    assert sorted(new) == sorted(key for key, why in DIFFERENCES.items() if why is None)
    assert [key for key in expected if key in reference] == list(reference)
    changed = {key for key in reference if expected[key] != reference[key]}
    assert changed == {key for key, why in DIFFERENCES.items() if why is not None}
    for key in changed:
        assert reference[key].replace("150", "150.00").replace("85", "85.00") == expected[key]


@pytest.mark.parametrize("name", list(CASES))
def test_every_record_prints_the_result_values_at_their_digits(name: str):
    result, pier = case(name)
    expected = expected_records(result, pier)
    actual = actual_records(result, pier)
    assert list(actual) == list(expected)
    for key in expected:
        assert actual[key] == expected[key], key


NUMERIC = ("soil.row.1", "soil.surface", "bearing.normal", "kv.definition.Ed", "kv.width", "kv.area", "kv.soil_type",
           "kv.long_term", "kv.short_term", "Kv.long_term", "Kv.short_term", "ks.long_term", "ks.short_term",
           "Ks.long_term", "Ks.short_term", "Kr.longitudinal.inertia", "Kr.longitudinal.long_term",
           "Kr.longitudinal.short_term", "Kr.transverse.inertia", "Kr.transverse.long_term", "Kr.transverse.short_term")


def test_variants_really_change_the_printed_values():
    current = expected_records(*case("current"))
    for name in ("clay", "alternating"):
        other = expected_records(*case(name))
        same = [key for key in NUMERIC if key != "soil.row.1" and current["0500/" + key] == other["0500/" + key]]
        assert same == [], name
    assert expected_records(*case("clay"))["0500/kv.soil_type"].startswith("支持層の土質区分：粘性土（kv=3.8")
    assert expected_records(*case("alternating"))["0500/soil.row.1"].startswith("第2層3.250粘性土12")


def test_the_report_reads_the_result_not_the_input():
    """A result whose values differ from what the input would give is printed as is."""
    result, pier = case("current")
    sentinel = replace(result, width=Printed(1.234, 3, "m"), n_gamma=Printed(12.34, 2, ""),
                       surface_thickness=Printed(9.876, 3, "m"), soil_type="粘性土", coefficient=3.8,
                       exponent_text="-1",
                       long_term=replace(result.long_term, kv=Printed(111.0, 0, "kN/m3"),
                                         Kr_transverse=Printed(7654321.0, 0, "kN m/rad")))
    actual = actual_records(sentinel, pier)
    assert actual["0500/kv.width"].endswith("=1.234m)")
    assert actual["0500/bearing.normal"].startswith("Nγ=12.34,")
    assert actual["0500/soil.row.0"].startswith("表層9.876")
    assert actual["0500/kv.long_term"] == "kv=3.8×0.5×165760×1.234-1=111kN/m3"
    assert actual["0500/Kr.transverse.long_term"] == "Kr=111×425.250000=7,654,321kN・m/rad"
    assert actual == expected_records(sentinel, pier)


def test_manuscript_uses_structured_fraction_root_and_script():
    from gridlayoutpdf import Fraction, Root, Script
    from webpier.reporting.stages.foundation import content

    def classes(value: Any) -> set[type]:
        found = {type(value)}
        if is_dataclass(value):
            for field in fields(value):
                found |= classes(getattr(value, field.name))
        elif isinstance(value, (tuple, list)):
            for item in value:
                found |= classes(item)
        return found

    assert {Fraction, Root, Script} <= classes(content(*case("current")))


def test_unit_text_follows_the_result_units():
    from webpier.reporting.stages.foundation import semantic_records

    result, pier = case("current")
    odd = replace(result, long_term=replace(result.long_term, Kv=Printed(1.0, 0, "furlong")))
    with pytest.raises(ValueError, match="単位"):
        semantic_records(odd, pier)


def test_semantic_text_rejects_an_unknown_node():
    from webpier.reporting.stages.foundation import plain, ratio

    with pytest.raises(TypeError, match="Unsupported"):
        plain(object())
    assert plain(ratio("2")) == "2" and plain(ratio("1/3")) == "1/3"
