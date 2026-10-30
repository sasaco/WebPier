"""The actions on the cantilever beam at the column face (0900 13.1 (4) 荷重設計の集計, decision 59; Example2
13-24 to 13-29).

Each action is a table of what loads the cantilever: a vertical load N on a bearing at X from the column face and e
along the track (Md = N·X, Mt = N·e), the self weight (N and Md), or a horizontal force H on a device at the arm Y
(Mt = H·Y). The totals are the sums of the printed rows (ADR-0003). The actions are, in report order: D1 (with the
self weight), D2, S2, S10, S30; the train L of each loading and the seismic train; the impact I of each loading for
安全性 and for 使用性; the vehicle lateral load LF of each loading; the wind W with and without the train; the seismic
inertia EQ across the track (girder and train); then the bearing forces along the track of each case that has them
(bearings, decision 125: one table per case, as the cap of a movable bearing depends on the case's vertical forces),
in case order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...core.printed import FORCE, MOMENT, Printed
from .._exact import d, put, total
from ..moving_load import Girder
from ..reaction.longitudinal import Snow
from .bearings import BearingCase
from .geometry import GIRDER_SIDES, CantileverBearing, Geometry
from .loads import Loading, LoadingResult, SeismicTrainLoad, Torque, Wind

SELF_WEIGHT = "片持梁自重"
REACTION = "上部工反力"
GIRDER_INERTIA = "上部工慣性力"
TRAIN_INERTIA = "列車慣性力"
TRANSVERSE, LONGITUDINAL = "線路直角方向", "線路方向"


class Group(Enum):
    """The impact (and load factor) group of a train term."""

    ULTIMATE = "安全性(破壊)"
    SERVICE = "使用性"


@dataclass(frozen=True)
class ActionKey:
    kind: str  # D1, D2, S, L, I, LF, W, EQ, LRB
    variant: str = ""  # S: S2/S10/S30; L/LF: the loading or 地震時; I: group:loading; W: the wind; EQ: 直角/線路;
    # LRB: the case number

    @staticmethod
    def snow(snow: Snow) -> ActionKey:
        return ActionKey("S", snow.name)

    @staticmethod
    def train(loading: Loading | None) -> ActionKey:
        return ActionKey("L", "地震時" if loading is None else loading.name)

    @staticmethod
    def impact(group: Group, loading: Loading) -> ActionKey:
        return ActionKey("I", f"{group.name}:{loading.name}")

    @staticmethod
    def lateral(loading: Loading) -> ActionKey:
        return ActionKey("LF", loading.name)

    @staticmethod
    def wind(wind: Wind) -> ActionKey:
        return ActionKey("W", wind.name)

    @staticmethod
    def bearing(number: int) -> ActionKey:
        return ActionKey("LRB", str(number))


EQ_TRANSVERSE = ActionKey("EQ", TRANSVERSE)
D1, D2 = ActionKey("D1"), ActionKey("D2")


@dataclass(frozen=True)
class Row:
    """One line of an action table: a vertical load (n, x, e) or a horizontal force (h, y)."""

    label: str
    sublabel: str  # the bearing (起点側 Ｇ1桁 of a vertical load, Ｇ1桁 of a horizontal force), or ""
    n: Printed | None
    x: Printed | None
    md: Printed
    h: Printed | None
    arm: Printed | None  # e of a vertical load, Y of a horizontal force
    mt: Printed


@dataclass(frozen=True)
class Action:
    key: ActionKey
    title: str  # as the report heads it: 固定死荷重D1, 列車荷重L (a) B支点最大の場合 …
    rows: tuple[Row, ...]
    n: Printed  # Σ N (the design shear force at the column face)
    md: Printed
    mt: Printed
    h: Printed  # Σ H (0 for vertical actions)


def _vertical_row(label: str, bearing: CantileverBearing, n: Printed) -> Row:
    md = put(MOMENT, d(n) * d(bearing.x))
    return Row(label, f"{GIRDER_SIDES[bearing.girder]} {bearing.bearing.label}", n, bearing.x, md, None, bearing.e,
               put(MOMENT, d(n) * d(bearing.e)))


def _action(key: ActionKey, title: str, rows: list[Row]) -> Action:
    return Action(key, title, tuple(rows), put(FORCE, total(row.n for row in rows if row.n is not None)),
                  put(MOMENT, total(row.md for row in rows)), put(MOMENT, total(row.mt for row in rows)),
                  put(FORCE, total(row.h for row in rows if row.h is not None)))


def _vertical(key: ActionKey, title: str, geometry: Geometry, label: str, load, *, self_weight: bool = False
              ) -> Action:
    """A vertical action: *load*(bearing) gives N of each bearing on the cantilever."""
    rows = []
    if self_weight:
        weight = geometry.self_weight
        rows.append(Row(SELF_WEIGHT, "", weight.force, None, weight.moment, None, None, MOMENT(0)))
    rows += [_vertical_row(label, bearing, load(bearing)) for bearing in geometry.bearings]
    return _action(key, title, rows)


def _dead(geometry: Geometry, snow: bool) -> list[Action]:
    """D1, D2 and, with snow on the pier, the three snow loads (decision 69: without, no snow action)."""

    def of(field: str):
        return lambda bearing: getattr(bearing.bearing.loads.bearing, field)

    return [_vertical(D1, "固定死荷重D1", geometry, REACTION, of("d1"), self_weight=True),
            _vertical(D2, "付加死荷重D2", geometry, REACTION, of("d2")),
            *(_vertical(ActionKey.snow(kind), f"雪荷重S ({label})", geometry, REACTION, of(kind.value))
              for kind, label in ((Snow.S2, "2年確率"), (Snow.S10, "10年確率"), (Snow.S30, "30年確率")) if snow)]


def _train(geometry: Geometry, loadings: tuple[LoadingResult, ...],
           seismic: dict[Girder, tuple[SeismicTrainLoad, ...]]) -> list[Action]:
    found = []
    for item in loadings:
        found.append(_vertical(ActionKey.train(item.loading), f"列車荷重L {item.loading.value}の場合", geometry, REACTION,
                               lambda bearing, item=item: item.girders[bearing.girder].bearing(bearing.bearing.number)
                               .adopted.load))
    found.append(_vertical(ActionKey.train(None), "列車荷重L 地震時列車荷重", geometry, REACTION,
                           lambda bearing: next(load.load for load in seismic[bearing.girder]
                                                if load.bearing.number == bearing.bearing.number)))
    return found


def _impact(geometry: Geometry, loadings: tuple[LoadingResult, ...]) -> list[Action]:
    found = []
    for group in Group:
        for item in loadings:
            def load(bearing: CantileverBearing, item=item, group=group) -> Printed:
                adopted = item.girders[bearing.girder].bearing(bearing.bearing.number).adopted
                return adopted.impact_ultimate if group is Group.ULTIMATE else adopted.impact_service
            found.append(_vertical(ActionKey.impact(group, item.loading), f"衝撃荷重I {group.value} {item.loading.value}の場合",
                                   geometry, REACTION, load))
    return found


def _torque_action(key: ActionKey, title: str, geometry: Geometry, label: str,
                   torques: dict[Girder, Torque]) -> Action:
    return _vertical(key, title, geometry, label,
                     lambda bearing: torques[bearing.girder].vertical(bearing.bearing.number))


def _seismic_transverse(geometry: Geometry, girder: dict[Girder, Torque], train: dict[Girder, Torque]) -> Action:
    rows = [_vertical_row(GIRDER_INERTIA, bearing, girder[bearing.girder].vertical(bearing.bearing.number))
            for bearing in geometry.bearings]
    rows += [_vertical_row(TRAIN_INERTIA, bearing, train[bearing.girder].vertical(bearing.bearing.number))
             for bearing in geometry.bearings]
    return _action(EQ_TRANSVERSE, "地震時直角方向EQ", rows)


def bearing_actions(cases: tuple[BearingCase, ...]) -> tuple[Action, ...]:
    """The bearing forces along the track of each case on one cantilever (one row per bearing on it)."""
    found = []
    for case in cases:
        title = "地震時線路方向" if case.combination is None else (
            f"{case.label}の支承に働く水平荷重" if case.loading is None else
            f"{case.label} {case.loading.value}の支承に働く水平荷重")
        rows = [Row(GIRDER_SIDES[item.bearing.girder], item.bearing.bearing.label, None, None, MOMENT(0), item.force,
                    item.arm, item.moment) for item in case.bearings]
        found.append(_action(ActionKey.bearing(case.number), title, rows))
    return tuple(found)


def vertical_actions(geometry: Geometry, loadings: tuple[LoadingResult, ...],
                     seismic_train: dict[Girder, tuple[SeismicTrainLoad, ...]],
                     lateral: dict[Loading, dict[Girder, Torque]], wind: dict[Wind, dict[Girder, Torque]],
                     seismic_girder: dict[Girder, Torque], seismic_train_torque: dict[Girder, Torque], *,
                     snow: bool = True) -> tuple[Action, ...]:
    """Every action table of the cantilever but the bearing forces, in report order; the snow loads only with snow on
    the pier."""
    return (*_dead(geometry, snow), *_train(geometry, loadings, seismic_train), *_impact(geometry, loadings),
            *(_torque_action(ActionKey.lateral(loading), f"車両横荷重LF {loading.value}の場合", geometry, REACTION,
                             lateral[loading]) for loading in Loading),
            *(_torque_action(ActionKey.wind(kind), f"風荷重W {kind.value}", geometry, REACTION, wind[kind])
              for kind in Wind),
            _seismic_transverse(geometry, seismic_girder, seismic_train_torque))
