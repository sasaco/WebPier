"""Independent checks of the documented V5.2 pier NDU subset.

This module deliberately imports neither the exporter nor its field constants.
Its reference values are reviewed case-specific JSON, never serializer output.
Reading a saved NDU is not a structural analysis or a GUI inspection.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any


class ReadbackError(ValueError):
    """An input or its app-normalized copy failed independent inspection."""


_ENGINEERING_KEY = re.compile(
    r"(?:JointXY\d+|ElementInfo\d+|MemberInfo\d+|MemberLeng\d+|MemberDvid\d+-\d+|"
    r"NonLinInfo\d+|SectInfo\d+|SectConc\d+|SectJikuNum\d+|SectJiku\d+|"
    r"SectRein\d+-\d+|SectSher\d+|SectSafe\d+|SuppotInfo\d+|FootInfo\d+|"
    r"MLoadInfo\d+|JLoadInfo\d+|LoadCase\d+|LoadAlph\d+|MLoadRow\d+|"
    r"JLoadRow\d+|SNAPConb\d+|ConbAlpf\d+)"
)


def parse_ndu(data: bytes) -> dict[str, tuple[str, ...]]:
    """Parse records without applying production mappings or filling defaults."""
    if not data or not data.endswith(b"\r\n"):
        raise ReadbackError("NDU must end with CRLF")
    if b"\n" in data.replace(b"\r\n", b"") or b"\r" in data.replace(b"\r\n", b""):
        raise ReadbackError("NDU contains non-CRLF line endings")
    try:
        lines = data.decode("cp932", errors="strict").splitlines()
    except UnicodeError as exc:
        raise ReadbackError("NDU is not valid CP932") from exc
    records: dict[str, tuple[str, ...]] = {}
    for line_number, line in enumerate(lines, 1):
        if line == "SHABUZAI_INFO":
            continue
        if "=" not in line:
            raise ReadbackError(f"Unsupported NDU line {line_number}")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key) or key in records:
            raise ReadbackError(f"Invalid or duplicate NDU key: {key}")
        records[key] = tuple(part.strip() for part in value.split(","))
    if not re.fullmatch(r"5\.2\.3\.S\.[1-5]", records.get("Virsion", ("",))[0]):
        raise ReadbackError("Expected a JRSNAP 5.2.3 S.1-S.5 header")
    return records


def _zero_blank_allowed(key: str, position: int) -> bool:
    # Only force components have a reviewed blank=zero meaning. In particular,
    # blank range-start and blank support-case fields must never become zero.
    return ((key.startswith("JLoadInfo") and position in (4, 5, 6))
            or (key.startswith("MLoadInfo") and position in (7, 8)))


def _integer_field(key: str, position: int) -> bool:
    """Identifiers/codes are exact; dimensional values may round as Single."""
    if key == "DataInfo":
        return position < 16 or position > 19
    if re.fullmatch(r"(?:JointXY|ElementInfo|SectInfo|SectRein\d+-|NonLinInfo|SuppotInfo|FootInfo|JLoadInfo|MLoadInfo|SNAPConb)\d+", key):
        if key.startswith("JointXY"):
            return position == 2
        if key.startswith("ElementInfo"):
            return position < 8 or position > 10
        if key.startswith("SectInfo"):
            return position < 4 or position > 11
        if key.startswith("SectRein"):
            return position == 2
        if key.startswith("NonLinInfo"):
            return position < 7
        if key.startswith("SuppotInfo"):
            return position in (1, 2)
        if key.startswith("FootInfo"):
            return position in (1, 2, 11)
        if key.startswith("JLoadInfo"):
            return position < 4
        if key.startswith("MLoadInfo"):
            return position < 5
        if key.startswith("SNAPConb"):
            return position in (2, 3, 19, 20)
    return (key == "JointOrg" or "Num" in key or "Row" in key
            or key.startswith(("MemberInfo", "LoadCase", "ExOpt"))
            or (key.startswith("MemberDvid") and position == 1)
            or (key.startswith("TanbuShiji") and position == 0))


def _compare_field(key: str, position: int, actual: str, expected: Any,
                   relative: float, absolute: float) -> None:
    if _zero_blank_allowed(key, position) and {str(expected), actual} <= {"", "0", "0.0"}:
        return
    if isinstance(expected, str):
        if actual != expected:
            raise ReadbackError(f"{key}[{position + 1}]: {actual!r} != {expected!r}")
        return
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        raise ReadbackError(f"Oracle contains unsupported value: {key}[{position + 1}]")
    try:
        number = float(actual)
    except ValueError as exc:
        raise ReadbackError(f"{key}[{position + 1}] is not numeric: {actual!r}") from exc
    if not math.isfinite(number):
        raise ReadbackError(f"{key}[{position + 1}] is not finite")
    equal = number == expected if _integer_field(key, position) else math.isclose(
        number, expected, rel_tol=relative, abs_tol=absolute)
    if not equal:
        raise ReadbackError(f"{key}[{position + 1}]: {number} != {expected}")


def verify_readback(data: bytes, oracle: Mapping[str, Any]) -> dict[str, Any]:
    """Check all engineering records against a case-specific independent oracle."""
    records = parse_ndu(data)
    expected = oracle.get("expected_records")
    prefixes = oracle.get("prefix_fields", {})
    if not isinstance(expected, Mapping) or not expected:
        raise ReadbackError("The independent oracle has no expected records")
    relative, absolute = 5e-7, 1e-6
    suffix_records = set(oracle.get("text_suffix_records", []))
    checked = 0
    for key, values in {**expected, **prefixes}.items():
        actual = records.get(key)
        if actual is None:
            raise ReadbackError(f"Missing required NDU record: {key}")
        suffix = 1 if key in suffix_records else 0
        if len(actual) != len(values) + suffix:
            raise ReadbackError(f"{key}: expected {len(values) + suffix} fields, got {len(actual)}")
        for position, value in enumerate(values):
            _compare_field(key, position, actual[position], value, relative, absolute)
            checked += 1
    known = set(expected) | set(prefixes)
    extra = sorted(key for key in records if _ENGINEERING_KEY.fullmatch(key) and key not in known)
    if extra:
        raise ReadbackError(f"Unexpected engineering records: {extra}")
    if records.get("SRenkeiNum", ("0",)) != ("0",):
        raise ReadbackError("Soil-JR links must be disabled")
    if any(key.startswith(("CHOKU_KISO", "SoilRenkei", "NDTPath")) for key in records):
        raise ReadbackError("Unexpected foundation-check, soil-link or old output-path data")
    resultants = _resultants(records)
    expected_resultants = oracle.get("resultants_about_footing_bottom", {})
    case_order = oracle.get("case_order", ("D1", "D2", "Wp", "Sw2", "L", "EQ1", "EQL", "EQ2"))
    if (len(case_order) != len(resultants) or len(set(case_order)) != len(case_order)
            or set(expected_resultants) != set(case_order)):
        raise ReadbackError("Independent resultants for every basic case are required")
    for case, symbol in enumerate(case_order, 1):
        if symbol not in expected_resultants:
            raise ReadbackError(f"Missing independent resultant: {symbol}")
        values = expected_resultants[symbol]
        for axis, (actual, value) in enumerate(zip(resultants[case], values, strict=True)):
            if not math.isclose(actual, value, rel_tol=5e-7, abs_tol=1e-5):
                raise ReadbackError(f"{symbol} resultant[{axis}]: {actual} != {value}")
    combinations = {}
    for key, values in oracle.get("combination_resultants_about_footing_bottom", {}).items():
        coefficients = tuple(float(value) for value in records[f"ConbAlpf{key}"])
        if len(coefficients) != len(resultants):
            raise ReadbackError("Combination does not cover every basic case")
        combined = [sum(coefficients[case - 1] * force[axis] for case, force in resultants.items())
                    for axis in range(3)]
        if len(values) != 3 or any(not math.isclose(actual, value, rel_tol=5e-7, abs_tol=1e-5)
                                   for actual, value in zip(combined, values, strict=True)):
            raise ReadbackError(f"Combination {key} resultant differs from independent oracle")
        combinations[key] = combined
    return {"verified": True, "checked_records": len(known), "checked_fields": checked,
            "resultants_about_footing_bottom": resultants,
            "combination_resultants_about_footing_bottom": combinations,
            "method": "independent_normalized_record_parser_and_literal_oracle",
            "gui_inspected": False, "analysis_executed": False}


def _numeric(fields: tuple[str, ...], position: int) -> float:
    value = fields[position]
    if value == "":
        return 0.0
    number = float(value)
    if not math.isfinite(number):
        raise ReadbackError("Non-finite engineering value")
    return number


def _resultants(records: Mapping[str, tuple[str, ...]]) -> dict[int, list[float]]:
    """Integrate native loads independently about the foundation bottom.

    The supported oracle has vertical members ordered from top to bottom.
    Native direction 4 is global downward load; direction 1 acts leftward on
    these members. For a linear distribution the first moment is integrated,
    so relocating a load while preserving its resultant still fails.
    """
    nodes = {int(key[7:]): tuple(map(float, fields[:2])) for key, fields in records.items()
             if re.fullmatch(r"JointXY\d+", key)}
    bottom = int(records["FootInfo1"][1])
    ox, oy = nodes[bottom]
    case_count = int(records["LoadNum"][0])
    if not 1 <= case_count <= 100:
        raise ReadbackError("Invalid basic-case count")
    result = {case: [0.0, 0.0, 0.0] for case in range(1, case_count + 1)}
    for key, fields in records.items():
        if re.fullmatch(r"JLoadInfo\d+", key):
            case, node = int(fields[0]), int(fields[2])
            x, y = nodes[node]
            fx, fy, moment = (_numeric(fields, index) for index in (4, 5, 6))
            action = result[case]
            action[0] += fx
            action[1] += fy
            action[2] += moment + (x - ox) * fy - (y - oy) * fx
        elif re.fullmatch(r"MLoadInfo\d+", key):
            _add_distributed(result, records, nodes, fields, ox, oy)
    return result


def _add_distributed(result: dict[int, list[float]], records: Mapping[str, tuple[str, ...]],
                     nodes: Mapping[int, tuple[float, ...]], fields: tuple[str, ...],
                     ox: float, oy: float) -> None:
    case, end, direction = int(fields[0]), int(fields[2]), int(fields[4])
    start = int(fields[1]) if fields[1] else end
    for element in range(start, end + 1):
        definition = records[f"ElementInfo{element}"]
        xi, yi = nodes[int(definition[4])]
        xj, yj = nodes[int(definition[5])]
        if abs(xi - xj) > 1e-6 or yj <= yi or direction not in (1, 4):
            raise ReadbackError("Independent oracle supports top-to-bottom vertical member loads only")
        if any(fields[index] not in ("", "0", "0.0") for index in (5, 6, 9, 10)):
            raise ReadbackError("Independent oracle requires full-member distributed loads")
        length, qa = yj - yi, _numeric(fields, 7)
        qb = qa if direction == 4 else _numeric(fields, 8)
        force = length * (qa + qb) / 2
        if direction == 4:
            result[case][1] += force
            result[case][2] += (xi - ox) * force
        else:
            result[case][0] -= force
            result[case][2] += length / 6 * (
                qa * (2 * (yi - oy) + yj - oy) + qb * (yi - oy + 2 * (yj - oy)))
