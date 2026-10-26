"""The 地盤変位 of a pile foundation (decision 97, CONTEXT.md 地盤変位).

A pile foundation on the ground classes G3〜G5 considers the 地盤変位 in its seismic design (Example橋脚4 IV-28: the deep
foundations on any ground but G0〜G2). SoilStructure's runner (``run-ground-displacement``) calculates the natural period Tg
of the surface ground and the design horizontal displacement f(z) of L1 and L2 (spectrum II, the larger one: 0.413 Tg
against 0.320 Tg) from the layers above the base; WebPier gives it the layers and reads its answer, and does not calculate
either itself.

- **The layers.** Every layer of the ground sheet but the last, which goes on below: the base of the seismic design is the
  top of the last layer. Each needs its thickness, its 湿潤 unit weight and its Vs; a blank one is an input error.
- **The rows.** Each layer is cut at the depths asked for (the nodes of the piles), so the runner's answer has a point at
  every one of them: the first row of a layer carries its unit weight and Vs, the rows after it leave them blank (the runner
  then takes the row above's). SoilStructure takes 58 rows.
- **The region.** Aggre-SE's 地域別補正係数 (A 1.0, B 0.85, C 0.7) is the runner's 地域別係数, and its 標準設計震度 is 1.0.
- **The answer.** Tg to 4 decimals (Example橋脚4 IV-4: 0.5335 s), the displacements in mm to 2 decimals (17.11, 220.34);
  a depth below the base does not move.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import LENGTH, Precision, Printed
from ..inputs import PierInput, choices
from ._exact import d, put

CONSIDERED = ("G3地盤", "G4地盤", "G5地盤")
REGION_COEFFICIENTS = {"A地域": Decimal("1.0"), "B地域": Decimal("0.85"), "C地域": Decimal("0.7")}
STANDARD_COEFFICIENT = Decimal(1)  # SoilStructure's 標準設計震度: railways have none
MAX_ROWS = 58  # SoilStructure's rows
PERIOD = Precision(4, "s")
DISPLACEMENT = Precision(2, "mm")
_LAYERS = "地盤データ.層"
_WHY = "地盤変位の算定に必要です（地盤区分 G3〜G5 の杭基礎）"
_MM = Decimal(1000)


class GroundDisplacementError(ValueError):
    """The runner's answer does not hold what was asked (not the input's fault)."""


def considered(pier: PierInput) -> bool:
    """Whether the seismic design of *pier* considers the 地盤変位: a pile foundation on G3〜G5."""
    return (pier.substructure.foundation in choices.PILE_FOUNDATIONS
            and pier.seismic_design.ground_class in CONSIDERED)


def region_coefficient(pier: PierInput) -> Decimal:
    region = pier.seismic_design.region
    if region is None:
        raise InputError(f"耐震設計条件.地域別: {_WHY}")
    return REGION_COEFFICIENTS[region]


@dataclass(frozen=True)
class SurfaceLayer:
    """A layer above the base: its place in the ground sheet, where it starts (m below the surface) and its values."""

    index: int
    name: str
    top: Printed
    thickness: Printed
    unit_weight: Printed  # 湿潤, kN/m3
    velocity: Printed  # Vs, m/s


def _need(value: Printed | None, path: str) -> Printed:
    if value is None:
        raise InputError(f"{path}: {_WHY}")
    return value


def surface_layers(pier: PierInput) -> tuple[SurfaceLayer, ...]:
    """The layers above the base of *pier*: every layer but the last."""
    layers, top = [], Decimal(0)
    for index, layer in enumerate(pier.soil.layers[:-1]):
        path = f"{_LAYERS}[{index}]"
        thickness = _need(layer.thickness, f"{path}.層厚")
        layers.append(SurfaceLayer(index, layer.name, put(LENGTH, top), thickness,
                                   _need(layer.unit_weight_wet, f"{path}.単位体積重量.湿潤"),
                                   _need(layer.shear_wave_velocity, f"{path}.せん断弾性波速度_Vs")))
        top += d(thickness)
    return tuple(layers)


@dataclass(frozen=True)
class RunnerRow:
    """A row of SoilStructure's input: the layer's number from 1, the thickness (m), and the values on its first row."""

    layer: str
    thickness: Decimal
    unit_weight: Decimal | None
    velocity: Decimal | None


def _millimetres(value: Decimal) -> int:
    return int(value * _MM)


def runner_rows(layers: Sequence[SurfaceLayer], depths: Iterable[Decimal]) -> tuple[RunnerRow, ...]:
    """The rows of *layers*, each layer cut at the *depths* (m below the surface, to the mm) inside it."""
    cuts = {_millimetres(depth) for depth in depths}
    rows: list[RunnerRow] = []
    for number, layer in enumerate(layers, 1):
        top = _millimetres(d(layer.top))
        bottom = top + _millimetres(d(layer.thickness))
        edges = [top, *sorted(cut for cut in cuts if top < cut < bottom), bottom]
        for first, (start, end) in enumerate(zip(edges, edges[1:])):
            rows.append(RunnerRow(str(number), Decimal(end - start) / _MM,
                                  None if first else d(layer.unit_weight), None if first else d(layer.velocity)))
    if len(rows) > MAX_ROWS:
        raise InputError(f"{_LAYERS}: 地盤変位の算定の行が{len(rows)}行あります（層の境界と杭の節点で分けます。"
                         f"SoilStructure は{MAX_ROWS}行まで）")
    return tuple(rows)


@dataclass(frozen=True)
class GroundPoint:
    """f(z) at a depth (m below the surface): L1 and L2 (spectrum II), mm."""

    depth: Printed
    l1: Printed
    l2: Printed


@dataclass(frozen=True)
class GroundDisplacement:
    layers: tuple[SurfaceLayer, ...]
    region_coefficient: Decimal
    period: Printed  # Tg
    profile: tuple[GroundPoint, ...]  # at the top of each layer, then at the base
    nodes: tuple[GroundPoint, ...]  # at the depths asked for, in the order asked

    def at(self, depth: Decimal) -> GroundPoint:
        """f(z) at one of the depths asked for."""
        wanted = _millimetres(depth)
        return next(point for point in self.nodes if _millimetres(d(point.depth)) == wanted)


def ground_displacement(layers: Sequence[SurfaceLayer], coefficient: Decimal, period: float,
                        points: Sequence[Mapping[str, float]], depths: Sequence[Decimal]) -> GroundDisplacement:
    """The 地盤変位 from the runner's answer: its Tg and its points (``depthM``, ``l1DisplacementMm``,
    ``l2SpectrumTwoDisplacementMm``), at the top of each layer, at the base and at each of *depths*."""
    if not period > 0:
        raise GroundDisplacementError(f"表層地盤の固有周期が正の値ではありません（{period!r}）")
    found = {round(Decimal(repr(float(point["depthM"]))) * _MM): point for point in points}
    base = _millimetres(d(layers[-1].top) + d(layers[-1].thickness))

    def point(depth: Decimal) -> GroundPoint:
        millimetres = _millimetres(depth)
        if millimetres >= base:
            return GroundPoint(put(LENGTH, depth), DISPLACEMENT(0), DISPLACEMENT(0))
        if millimetres not in found:
            raise GroundDisplacementError(f"深さ {depth} m の地盤変位がありません")
        value = found[millimetres]
        return GroundPoint(put(LENGTH, depth), put(DISPLACEMENT, Decimal(repr(float(value["l1DisplacementMm"])))),
                           put(DISPLACEMENT, Decimal(repr(float(value["l2SpectrumTwoDisplacementMm"])))))

    tops = [d(layer.top) for layer in layers]
    return GroundDisplacement(tuple(layers), coefficient, put(PERIOD, Decimal(repr(float(period)))),
                              tuple(point(depth) for depth in tops) + (
                                  GroundPoint(put(LENGTH, Decimal(base) / _MM), DISPLACEMENT(0), DISPLACEMENT(0)),),
                              tuple(point(depth) for depth in depths))


__all__ = ["CONSIDERED", "GroundDisplacement", "GroundDisplacementError", "GroundPoint", "RunnerRow", "SurfaceLayer",
           "considered", "ground_displacement", "region_coefficient", "runner_rows", "surface_layers"]
