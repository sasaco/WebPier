"""13.1 (1) 鉛直荷重: the dead loads of the girders, the three train loadings, the train and its impact on every
bearing, and the verticals the torques put on the bearings (Example2 13-1 to 13-14)."""

from __future__ import annotations

from ....calc.cantilever import CantileverResult
from ....calc.cantilever.geometry import GIRDER_SIDES
from ....calc.cantilever.loads import Loading, LoadingResult, Torque
from ....calc.moving_load import Girder
from ....calc.reaction import ReactionResult
from ....calc.reaction.transverse import LATERAL_RATIO, SEISMIC_KH_TRAIN
from ....core.printed import Printed
from ....inputs import PierInput
from ...numbers import printed
from ..reaction.manuscript import DETAIL, INDENTED, ITEM, SUBSECTION, CellSpec, Manuscript, TableSpec, cells, sub, sup
from ..reaction.tables import GIRDER_ROW, header
from ..reaction.train import loading_lines

LOADS = (("d1", "固定死荷重（D1）"), ("d2", "付加死荷重（D2）"), ("snow2", "雪荷重 S 2年確率"), ("snow10", "雪荷重 S 10年確率"),
         ("snow30", "雪荷重 S 30年確率"))
SUPPORTS = {Girder.ORIGIN: "B", Girder.END: "C"}
GIRDER_LABELS = {Girder.ORIGIN: "起点側桁", Girder.END: "終点側桁"}
CIRCLED = ("①", "②", "③")
LETTERS = ("a)", "b)", "c)")
TWO = "2"


def _dead_table(result: CantileverResult, reaction: ReactionResult) -> TableSpec:
    """表 13.1: the dead and snow loads of every bearing of both girders and their sums (0600's pier totals)."""
    girders = result.basis.girders
    columns = max(len(item.bearings) for item in girders.values())
    rows = [header("荷重", "", *(f"G{number}" for number in range(1, columns + 1)), "ΣR")]
    rows[0] = (CellSpec("荷重", colspan=2, align="center"), *rows[0][2:])
    for girder in (Girder.ORIGIN, Girder.END):
        item = girders[girder]
        for index, (field, label) in enumerate(LOADS):
            values: list = [getattr(bearing.loads.bearing, field) for bearing in item.bearings]
            values += [""] * (columns - len(values))
            pier_loads = reaction.dead.origin.pier if girder is Girder.ORIGIN else reaction.dead.end.pier
            first = (CellSpec(GIRDER_LABELS[girder], rowspan=len(LOADS), align="center"),) if index == 0 else ()
            rows.append((*first, CellSpec(label, align="left"), *cells(*values), *cells(getattr(pier_loads, field))))
    widths = (62.04, 120.0, *([54.0] * columns), 60.0)
    return TableSpec(widths, tuple(rows), header_rows=1, row_height=GIRDER_ROW,
                     numeric_columns=tuple(range(2, columns + 3)))


def _girder_lines(m: Manuscript, key: str, loading: LoadingResult, track: str, field: str) -> None:
    """Ｇ１桁 R × share = load for every bearing of both girders, one track count."""
    for girder in (Girder.ORIGIN, Girder.END):
        train = loading.girders[girder]
        for bearing in train.bearings:
            load = getattr(bearing, track)
            m.formula(f"{key}.{girder.name.lower()}.{bearing.bearing.number}", bearing.bearing.label, None,
                      (train.reaction, "×", load.share), getattr(load, field), wide=True)


def _impact_lines(m: Manuscript, key: str, loading: LoadingResult, track: str, service: bool) -> None:
    for girder in (Girder.ORIGIN, Girder.END):
        train = loading.girders[girder]
        impact = (train.impact_service if service else train.impact_ultimate)
        coefficient = impact.single if track == "single" else impact.double
        for bearing in train.bearings:
            load = getattr(bearing, track)
            m.formula(f"{key}.{girder.name.lower()}.{bearing.bearing.number}", bearing.bearing.label, None,
                      (load.load, "×", coefficient), load.impact_service if service else load.impact_ultimate,
                      wide=True)


def _tracks(m: Manuscript, key: str, loading: LoadingResult, lines, **options) -> None:  # noqa: ANN001
    for track, label in (("single", "・単線"), ("double", "・複線")):
        m.paragraph(f"{key}.{track}.label", label, gap=True)
        lines(m, f"{key}.{track}", loading, track, **options)


def _torque_lines(m: Manuscript, key: str, torque: Torque, support: str, *, force=None) -> None:  # noqa: ANN001
    """H, y, M of a torque and the vertical on each bearing: M × |xi| / Σxi²."""
    label = sub("H", support)
    if force is not None:
        m.formula(f"{key}.force", "水平力", label, force, torque.force, wide=True)
    else:
        m.value(f"{key}.force", "水平力", torque.force, symbolic=label, wide=True)
    m.value(f"{key}.height", "作用位置", torque.height, symbolic=sub("y", support), wide=True)
    m.formula(f"{key}.moment", "モーメント", sub("M", support), (torque.force, "×", torque.height), torque.moment,
              wide=True)
    m.paragraph(f"{key}.verticals.label", "トルクによる鉛直力", gap=True)
    squares = [part for bearing in torque.verticals
               for part in (sup(printed(_abs(bearing.bearing.position)), TWO), "+")][:-1]
    m.formula(f"{key}.squares", "ΣXi²", None, squares, torque.sum_squares, wide=True)
    for vertical in torque.verticals:
        m.formula(f"{key}.vertical.{vertical.bearing.number}", vertical.bearing.label, None,
                  (torque.moment, "×", _abs(vertical.bearing.position), "/", torque.sum_squares), vertical.force,
                  wide=True)


def _abs(value: Printed) -> Printed:
    return Printed(abs(value.value), value.digits, value.unit)


def _lateral(m: Manuscript, key: str, result: CantileverResult, loading: LoadingResult, reaction: ReactionResult) -> None:
    torques = result.basis.lateral[loading.loading]
    for girder in (Girder.ORIGIN, Girder.END):
        torque = torques[girder]
        if not torque.force.value:
            continue
        side_key = f"{key}.{girder.name.lower()}"
        m.paragraph(f"{side_key}.label", f"・{GIRDER_SIDES[girder]}", gap=True)
        if loading.loading is Loading.BOTH_MAX:
            m.paragraph(f"{side_key}.note", "（0600 の車両横荷重の載荷による）")
            _torque_lines(m, side_key, torque, SUPPORTS[girder])
        else:
            _torque_lines(m, side_key, torque, SUPPORTS[girder],
                          force=(LATERAL_RATIO, "×", loading.girders[girder].reaction))


def _wind(m: Manuscript, key: str, result: CantileverResult) -> None:
    for index, (kind, torques) in enumerate(result.basis.wind.items()):
        m.heading(f"{key}.{kind.name.lower()}.heading", f"({'ab'[index]}) {kind.value}", DETAIL)
        for girder in (Girder.ORIGIN, Girder.END):
            side_key = f"{key}.{kind.name.lower()}.{girder.name.lower()}"
            torque = torques[girder]
            m.paragraph(f"{side_key}.label", f"・{GIRDER_SIDES[girder]}", gap=True)
            m.value(f"{side_key}.moment", "モーメント", torque.moment, symbolic=sub("M", SUPPORTS[girder]), wide=True)
            m.paragraph(f"{side_key}.verticals.label", "トルクによる鉛直力", gap=True)
            for vertical in torque.verticals:
                m.formula(f"{side_key}.vertical.{vertical.bearing.number}", vertical.bearing.label, None,
                          (torque.moment, "×", _abs(vertical.bearing.position), "/", torque.sum_squares),
                          vertical.force, wide=True)


def _seismic(m: Manuscript, key: str, result: CantileverResult, reaction: ReactionResult) -> None:
    response = result.transverse
    m.value(f"{key}.kh", "最大応答震度", response.kh, symbolic="Kh", wide=True)
    m.paragraph(f"{key}.kh.source", f"（線路直角方向 Case{response.adopted.case} {response.adopted.block}）")
    for girder in (Girder.ORIGIN, Girder.END):
        side = reaction.transverse.origin if girder is Girder.ORIGIN else reaction.transverse.end
        side_key = f"{key}.{girder.name.lower()}"
        m.heading(f"{side_key}.heading", f"({'bc'[girder is Girder.END]}) {GIRDER_SIDES[girder]}", DETAIL)
        _torque_lines(m, side_key, result.seismic_girder[girder], SUPPORTS[girder],
                      force=(response.kh, "×", side.seismic_girder.force))


def _seismic_train(m: Manuscript, key: str, result: CantileverResult) -> None:
    m.value(f"{key}.kh", "設計震度", Printed(float(SEISMIC_KH_TRAIN), 3, ""), symbolic="Kh", wide=True)
    for girder in (Girder.ORIGIN, Girder.END):
        side_key = f"{key}.{girder.name.lower()}"
        m.heading(f"{side_key}.heading", f"({'bc'[girder is Girder.END]}) {GIRDER_SIDES[girder]}", DETAIL)
        _torque_lines(m, side_key, result.basis.seismic_train_torque[girder], SUPPORTS[girder])


def section(m: Manuscript, result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> None:
    basis = result.basis
    m.heading("vertical.heading", "(1) 鉛直荷重", SUBSECTION)
    m.heading("dead.heading", "1) 死荷重", ITEM)
    m.paragraph("dead.table.title", "表 13.1 上部工死荷重反力", SUBSECTION)
    m.table("dead.table", _dead_table(result, reaction), SUBSECTION)
    m.heading("train.heading", "2) 列車荷重", ITEM)
    m.heading("train.loading.heading", "(a) 移動荷重による支点反力", DETAIL)
    for letter, loading in zip(LETTERS, basis.loadings):
        key = f"train.loading.{loading.loading.name.lower()}"
        m.heading(f"{key}.heading", f"{letter} {loading.loading.value}", INDENTED)
        loading_lines(m, key, loading.result, pier)
    m.heading("shoe.heading", "3) 各シューの列車荷重 及び 衝撃荷重", ITEM)
    m.heading("shoe.train.heading", "(a) 列車荷重　L", DETAIL)
    for letter, loading in zip(LETTERS, basis.loadings):
        key = f"shoe.train.{loading.loading.name.lower()}"
        m.heading(f"{key}.heading", f"{letter} {loading.loading.value}", INDENTED)
        _tracks(m, key, loading, _girder_lines, field="load")
    m.heading("shoe.impact.heading", "(b) 衝撃荷重　I", DETAIL)
    for group, service, title in (("ultimate", False, "a) 安全性(破壊)"), ("service", True, "b) 使用性")):
        m.heading(f"shoe.impact.{group}.heading", title, INDENTED)
        for mark, loading in zip(CIRCLED, basis.loadings):
            key = f"shoe.impact.{group}.{loading.loading.name.lower()}"
            m.heading(f"{key}.heading", f"{mark} {loading.loading.value}", INDENTED)
            _tracks(m, key, loading, _impact_lines, service=service)
    m.heading("shoe.seismic.heading", "(c) 耐震の検討に用いる列車荷重", DETAIL)
    for girder, loads in basis.seismic_train.items():
        for load in loads:
            m.formula(f"shoe.seismic.{girder.name.lower()}.{load.bearing.number}", load.bearing.label, None,
                      (load.reaction, "×", load.share), load.load, wide=True)
    m.heading("lateral.heading", "4) 車両横荷重のトルクによる鉛直荷重", ITEM)
    for letter, loading in zip(LETTERS, basis.loadings):
        key = f"lateral.{loading.loading.name.lower()}"
        m.heading(f"{key}.heading", f"({letter[0]}) {loading.loading.value}の場合", DETAIL)
        _lateral(m, key, result, loading, reaction)
    m.heading("wind.heading", "5) 風荷重のトルクによる鉛直反力", ITEM)
    _wind(m, "wind", result)
    m.heading("seismic.heading", "6) 地震時上部工慣性力のトルクによる鉛直反力", ITEM)
    _seismic(m, "seismic", result, reaction)
    m.heading("seismic_train.heading", "7) 地震時列車荷重慣性力のトルクによる鉛直反力", ITEM)
    _seismic_train(m, "seismic_train", result)

