"""0500 杭基礎: SOIL-JR calculates the ground of a pile foundation (decision 85, ADR-0013).

WebPier derives the rows of SOIL-JR's input from the input (``calc.pile_ground``), writes the .sdt (``export.soiljr``) and
has SOIL-JR calculate it with the JRSNAP runner (``jrsnap.calculate_ground``). The report of the stage is SOIL-JR's as the
runner printed it, byte for byte; the 基礎照査連携用データ (.sdr), the 解析連携データ (.sdc) and, when a layer along the pile
liquefies, the same two for the liquefaction are published under post/ as returned. The stage's result holds what WebPier
derived, the .sdt SOIL-JR calculated by its SHA256, the design limits of the .sdr (and of the one for the
liquefaction) as tables, and the ground springs of the .sdc, so that the stages that use them take them from the result
(0610 and 0620 the springs, decision 88; 0612 and 0622, Aggre-SE's check the limits).
SOIL-JR returns no judgement: the check is recorded as run, not as passed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..calc.pile_ground import PileGroundResult, calculate_pile_ground
from ..core.integrity import sha256
from ..calc.pile_springs import GroundSprings
from ..export.soiljr import SdcError, SdrError, SdrFile, build_sdt, parse_sdc, parse_sdr
from ..inputs import PierInput
from .jrsnap import SOIL_REPORT

STEM = "杭基礎"  # the name of the files: SOIL-JR's own names follow it
SDT = f"{STEM}.sdt"
TITLE = "WebPier 杭基礎"  # SOIL-JR's タイトル of the input, on every page of its report
FILES = (("sdr", f"{STEM}.sdr"), ("sdc", f"{STEM}.sdc"))
LIQUEFACTION = (("liquefiedsdr", f"{STEM}(液状化時用).sdr"), ("liquefiedsdc", f"{STEM}(液状化時用).sdc"))
# What the sidecar of the .sdt records of the file's target: SOIL-JR 5.2.3 reads it; it was written to its format
SDT_FACTS = {"target": "SOIL-JR", "target_version": "5.2-L03", "app_read_verified": False}


@dataclass(frozen=True)
class PileGroundModel:
    """The result of 0500 for a pile foundation: the derived values, the .sdt SOIL-JR calculated and its limits."""

    ground: PileGroundResult
    sdt_sha256: str
    sdr: SdrFile
    springs: GroundSprings  # the 解析用地盤ばね値 of the .sdc: the frame of 0610 and 0620 stands on them (decision 88)
    liquefied_sdr: SdrFile | None  # the .sdr for the liquefaction, when some layer along the pile liquefies
    sdc_sha256: str = ""
    # the .sdc as SOIL-JR returned it: the model of 0710 and 0720 reads its seismic tables (decision 93), the layouts it does
    # not support only when it is built
    sdc: bytes = field(default=b"", repr=False, metadata={"json": False})


def sdt(results: Mapping[str, Any], pier: PierInput) -> bytes:
    """The .sdt of 0500's result: the title names the stage, the description the 基礎形式."""
    return build_sdt(results["0500"], title=TITLE, description=pier.substructure.foundation)


def liquefied(pier: PierInput) -> bool:
    """Whether the input considers liquefaction, so that SOIL-JR returns the files for it."""
    return calculate_pile_ground(pier).liquefaction


def _check(ground: PileGroundResult, found: SdrFile, name: str) -> None:
    """The header of the .sdr is the pile WebPier gave SOIL-JR (length, type, columns, piles)."""
    pile, rows = found.pile, ground.rows
    wanted = {"杭種": ground.section.kind, "杭長": ground.length.value, "橋軸杭本数": len(rows.along),
              "直角杭本数": len(rows.across), "換算抵抗幅算定用杭本数": rows.piles}
    for key, value in wanted.items():
        if pile.get(key) != value:
            raise SdrError(f"{name} の{key}（{pile.get(key)!r}）が渡した入力の値（{value}）と違います")


def complete(result: PileGroundResult, files: Mapping[str, bytes], pier: PierInput,
             results: Mapping[str, Any]) -> PileGroundModel:
    """The result of 0500 with the files SOIL-JR returned: its .sdr (and the one for the liquefaction) read as tables."""
    found = parse_sdr(files["sdr"])
    _check(result, found, FILES[0][1])
    other = None
    if "liquefiedsdr" in files:
        other = parse_sdr(files["liquefiedsdr"])
        _check(result, other, LIQUEFACTION[0][1])
    try:
        springs = parse_sdc(files["sdc"])
    except SdcError as exc:
        raise SdrError(f"{FILES[1][1]} を読めません: {exc}") from exc
    return PileGroundModel(result, sha256(files["sdt"]), found, springs, other, sha256(files["sdc"]), files["sdc"])


def render(results: Mapping[str, Any], pier: PierInput, path: Path, pages: Mapping[str, bytes]) -> None:
    """SOIL-JR's report is the stage's report as the runner printed it (ADR-0013): nothing is added to it."""
    Path(path).write_bytes(pages[SOIL_REPORT])
