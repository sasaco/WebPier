"""有効根入れ深さ Df and 平均有効単位重量 γ2 of the cover above the footing base (CONTEXT.md).

For one level surface layer on the supporting layer, the footing base is the top of the supporting layer and
Df is the 0500 表層厚 H6 + H5 + min(df1, df2). The normal water level hw2 is measured up from the footing base
(not down from the ground), so the cover is wet above it and submerged below it:

    γ2 = ((Df − hw2) × γwet + hw2 × γsub) / Df

with γwet and γsub of 表層 (Example2 08 p.8-28, the procedure behind the JRSNAP FootInfo Df / γ2). Other ground
(sloping cover, more layers, water at or outside the cover) is outside this procedure and an input error.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import InputError
from ..core.printed import LENGTH, UNIT_WEIGHT, Printed
from ..inputs import PierInput
from ._exact import d, put
from .foundation import FoundationResult

LAYERS = 2  # 表層 and 支持層


@dataclass(frozen=True)
class EmbedmentResult:
    depth: Printed  # Df, the 0500 表層厚
    water: Printed  # hw2 above the footing base
    wet_segment: Printed  # Df − hw2
    unit_weight_wet: Printed  # γwet of 表層
    unit_weight_submerged: Printed  # γsub of 表層
    unit_weight: Printed  # γ2


def _outside(pier: PierInput, foundation: FoundationResult) -> str | None:
    """Why the ground is outside the procedure, or None."""
    sub = pier.substructure
    if sub.df1 != sub.df2:
        return (f"下部構造.土かぶり: 起点側_df1（{sub.df1.value} m）と終点側_df2（{sub.df2.value} m）が異なり、"
                "Df・γ2 の対象（左右同じ平坦な土被り）ではありません")
    layers = pier.soil.layers
    if len(layers) != LAYERS:
        return f"地盤データ.層: 表層と支持層の2層だけに対応します（{len(layers)}層）"
    depth, water = foundation.surface_thickness, sub.hw2
    if not 0 < water.value < depth.value:
        return f"下部構造.水位.平水位_hw2: 0 < hw2 < Df（{depth.value} m）が必要です（入力 {water.value} m）"
    return None


def calculate_embedment(pier: PierInput, foundation: FoundationResult) -> EmbedmentResult:
    """Df and γ2; ground outside the procedure is an input error (the JRSNAP export needs them)."""
    reason = _outside(pier, foundation)
    if reason is not None:
        raise InputError(reason)
    return _embedment(pier, foundation)


def applicable_embedment(pier: PierInput, foundation: FoundationResult) -> EmbedmentResult | None:
    """Df and γ2 where the procedure applies, else None: the 0500 report prints γ2 only then."""
    return None if _outside(pier, foundation) is not None else _embedment(pier, foundation)


@dataclass(frozen=True)
class CoverWeight:
    """γ2 of the cover with the water at *water* above the footing base (the 基礎の照査, decision 54)."""

    water: Printed  # the water level as entered, above the footing base
    wet_segment: Printed  # Df − hw within 0 … Df
    submerged_segment: Printed  # hw within 0 … Df
    unit_weight: Printed  # γ2


def cover_weight(embedment: EmbedmentResult, water: Printed) -> CoverWeight:
    """γ2 = ((Df − hw) × γwet + hw × γsub) / Df, the cover all submerged when hw ≧ Df and all wet when hw ≦ 0."""
    depth = d(embedment.depth)
    submerged = put(LENGTH, min(max(d(water), d(0)), depth))
    wet = put(LENGTH, depth - d(submerged))
    return CoverWeight(water, wet, submerged, put(UNIT_WEIGHT, (d(wet) * d(embedment.unit_weight_wet) + d(submerged)
                                                                * d(embedment.unit_weight_submerged)) / depth))


def _embedment(pier: PierInput, foundation: FoundationResult) -> EmbedmentResult:
    depth, water = foundation.surface_thickness, pier.substructure.hw2
    surface = pier.soil.surface
    wet, submerged = surface.unit_weight_wet, surface.unit_weight_submerged
    assert wet is not None and submerged is not None  # required by parse_input
    segment = put(LENGTH, d(depth) - d(water))
    return EmbedmentResult(
        depth=depth, water=water, wet_segment=segment, unit_weight_wet=wet, unit_weight_submerged=submerged,
        unit_weight=put(UNIT_WEIGHT, (d(segment) * d(wet) + d(water) * d(submerged)) / d(depth)))
