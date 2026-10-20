"""有効根入れ深さ Df and 平均有効単位重量 γ2 of the cover above the footing base (CONTEXT.md, decision 64).

Df is the 0500 表層厚 H6 + H5 + min(df1, df2). The layers from 表層 down to 支持層 fill it from the ground:
each layer above 支持層 has its entered 層厚 and 支持層 takes the rest, Df − Σ (the footing base sits in it).
A blank 層厚 of 表層 is the rest instead and 支持層 starts at the footing base (Example2: 表層 alone, Df).
Water levels are measured up from the footing base (not down from the ground), so each layer is wet above the
water and submerged below it:

    γ2 = Σ (wet part × γwet + submerged part × γsub) / Df

which for one layer is ((Df − hw2) × γwet + hw2 × γsub) / Df (Example2 08 p.8-28, the procedure behind the
JRSNAP FootInfo Df / γ2). A sloping cover (df1 ≠ df2) or the normal water level outside the cover is outside this
procedure and an input error.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import LENGTH, UNIT_WEIGHT, Printed
from ..inputs import PierInput
from ..inputs.choices import LAYER_SUPPORT
from ._exact import d, put, total
from .foundation import FoundationResult, surface_thickness

_LAYERS = "地盤データ.層"


@dataclass(frozen=True)
class CoverLayer:
    """A layer of 地盤データ.層 within Df."""

    index: int  # in 地盤データ.層
    name: str
    bottom: Printed  # above the footing base, m
    thickness: Printed  # within Df, m
    unit_weight_wet: Printed
    unit_weight_submerged: Printed


@dataclass(frozen=True)
class Segment:
    """A part of one layer, wet above the water or submerged below it, as the γ2 formula prints it."""

    thickness: Printed
    unit_weight: Printed
    submerged: bool


@dataclass(frozen=True)
class CoverWeight:
    """γ2 of the cover with the water at *water* above the footing base (the 基礎の照査, decision 54)."""

    water: Printed  # the water level as entered, above the footing base
    segments: tuple[Segment, ...]  # from the ground down; one layer always prints its wet and its submerged part
    unit_weight: Printed  # γ2

    @property
    def wet_segment(self) -> Printed:  # Df − hw within 0 … Df
        return LENGTH.total(segment.thickness for segment in self.segments if not segment.submerged)

    @property
    def submerged_segment(self) -> Printed:  # hw within 0 … Df
        return LENGTH.total(segment.thickness for segment in self.segments if segment.submerged)


@dataclass(frozen=True)
class EmbedmentResult:
    depth: Printed  # Df, the 0500 表層厚
    water: Printed  # hw2 above the footing base
    layers: tuple[CoverLayer, ...]  # the layers within Df, from the ground down
    normal: CoverWeight  # γ2 at hw2

    @property
    def unit_weight(self) -> Printed:  # γ2
        return self.normal.unit_weight

    @property
    def single(self) -> CoverLayer | None:
        """The one layer of the cover, or None for several (the report prints the one-layer formula)."""
        return self.layers[0] if len(self.layers) == 1 else None


def surface_layer_thickness(pier: PierInput, depth: Printed) -> Printed:
    """The thickness of 表層: entered, or the rest of Df below the layers between it and 支持層."""
    layers = pier.soil.layers
    surface = layers[0]
    if surface.thickness is not None:
        return surface.thickness
    middle = layers[1:_support_index(pier)]  # each has its thickness (parse_input)
    return put(LENGTH, d(depth) - total(layer.thickness for layer in middle if layer.thickness is not None))


def _support_index(pier: PierInput) -> int:
    """The row of 支持層 (exactly one after parse_input; a hand-made Soil without one ends at its last row)."""
    layers = pier.soil.layers
    return next((index for index, layer in enumerate(layers) if layer.name == LAYER_SUPPORT), len(layers))


def cover_layers(pier: PierInput, depth: Printed) -> tuple[CoverLayer, ...]:
    """The layers within Df from the ground down (decision 64); layers that get no thickness are left out."""
    layers = pier.soil.layers
    above = layers[:_support_index(pier)]
    given = [layer.thickness for layer in above if layer.thickness is not None]  # all but a blank 表層
    entered = put(LENGTH, total(given))
    if d(entered) > d(depth):
        what = "表層から支持層の上まで" if layers[0].thickness is not None else "表層と支持層の間"
        raise InputError(f"{_LAYERS}: {what}の層厚の合計 {entered.value:.3f} m が "
                         f"Df（H6＋H5＋min(df1,df2) = {depth.value:.3f} m）を超えます")
    surface = surface_layer_thickness(pier, depth)
    thicknesses = [surface, *(layer.thickness for layer in above[1:])]
    thicknesses.append(put(LENGTH, d(depth) - total(thicknesses)))  # 支持層 within Df
    result, top = [], d(depth)
    for index, thickness in enumerate(thicknesses):
        if thickness.value <= 0:
            continue
        layer = layers[index]
        path = f"{_LAYERS}[{index}].単位体積重量"
        wet, submerged = layer.unit_weight_wet, layer.unit_weight_submerged
        if wet is None or submerged is None:
            key = "湿潤" if wet is None else "水中"
            raise InputError(f"{path}.{key}: 値が必要です（Df の範囲の層）")
        top -= d(thickness)
        result.append(CoverLayer(index=index, name=layer.name, bottom=put(LENGTH, top), thickness=thickness,
                                 unit_weight_wet=wet, unit_weight_submerged=submerged))
    return tuple(result)


def _outside(pier: PierInput, foundation: FoundationResult) -> str | None:
    """Why the ground is outside the procedure, or None."""
    sub = pier.substructure
    if sub.df1 != sub.df2:
        return (f"下部構造.土かぶり: 起点側_df1（{sub.df1.value} m）と終点側_df2（{sub.df2.value} m）が異なり、"
                "Df・γ2 の対象（左右同じ平坦な土被り）ではありません")
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


def _cover_weight(depth: Printed, layers: tuple[CoverLayer, ...], water: Printed) -> CoverWeight:
    segments = []
    for layer in layers:
        submerged = put(LENGTH, min(max(d(water) - d(layer.bottom), d(0)), d(layer.thickness)))
        wet = put(LENGTH, d(layer.thickness) - d(submerged))
        for part, unit_weight, below in ((wet, layer.unit_weight_wet, False),
                                         (submerged, layer.unit_weight_submerged, True)):
            if part.value > 0 or len(layers) == 1:
                segments.append(Segment(part, unit_weight, below))
    weight = put(UNIT_WEIGHT, sum((d(s.thickness) * d(s.unit_weight) for s in segments), Decimal(0)) / d(depth))
    return CoverWeight(water, tuple(segments), weight)


def cover_weight(embedment: EmbedmentResult, water: Printed) -> CoverWeight:
    """γ2 = Σ (wet part × γwet + submerged part × γsub) / Df, the cover all submerged when hw ≧ Df and all wet
    when hw ≦ 0."""
    return _cover_weight(embedment.depth, embedment.layers, water)


def _embedment(pier: PierInput, foundation: FoundationResult) -> EmbedmentResult:
    depth, water = foundation.surface_thickness, pier.substructure.hw2
    layers = cover_layers(pier, depth)
    return EmbedmentResult(depth=depth, water=water, layers=layers, normal=_cover_weight(depth, layers, water))


@dataclass(frozen=True)
class Displaced:
    """γ' of the soil the footing displaces (0710 / 0720): the wet unit weight of the layers within the footing
    height H5 + H6 above the base, averaged by their thickness (decision 64)."""

    height: Printed  # H5 + H6
    parts: tuple[tuple[CoverLayer, Printed], ...]  # (layer, its thickness within the footing height)
    unit_weight: Printed


def displaced_soil(pier: PierInput, height: Printed) -> Displaced:
    layers = cover_layers(pier, surface_thickness(pier))
    parts = []
    for layer in layers:
        low, high = d(layer.bottom), d(layer.bottom) + d(layer.thickness)
        part = put(LENGTH, max(min(high, d(height)) - low, d(0)))
        if part.value > 0:
            parts.append((layer, part))
    weight = put(UNIT_WEIGHT, sum((d(part) * d(layer.unit_weight_wet) for layer, part in parts), Decimal(0))
                 / d(height))
    return Displaced(height=height, parts=tuple(parts), unit_weight=weight)
