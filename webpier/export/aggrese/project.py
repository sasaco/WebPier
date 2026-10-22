"""The Aggre-SE project of a 0711 / 0721 analysis (decision 49, CONTEXT.md 耐震照査の入力).

Aggre-SE (structural-mcp ``Batch``, Docu-SE) reads the JRSNAP results of each Case (the DB1 and the files of the same
name beside it) with the conditions of a project XML. Only the 耐震設計条件 are inputs; the other conditions are
WebPier's, those of the Example2 projects (.claude/docs/Example橋脚2/10_線路(耐震)/P1_線路.xml and 11_直角(耐震)/
P1_直角.xml), and the values that follow from the NDU are taken from its model:

- the direct foundation checked at the FootInfo joint (Aggre-SE's 直接基礎の照査位置 is a joint number);
- the shear span La of the one nonlinear (M-θ) member, in mm, as the NDU's section has it;
- the focus joint 0: Aggre-SE then uses the control joint stored in each DB1;
- the check items of each Case, by the 照査パターン (ρm, αf) of its combination (decision 76).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
import re

from ...core.errors import InputError
from ...core.printed import Printed
from ...inputs import PierInput
from ...inputs.choices import GROUND_CLASSES, REGIONS
from ..jrsnap.model import NduModel

SECTION = "耐震設計条件"
_CASE = re.compile(r".*\(Case(\d+)_[^()]*\)\.db1", re.IGNORECASE)  # JRSNAP's <data>(Case<n>_ρm…_αf…_…).DB1

# Decision 76: the check items ①..⑨ of a Case by its 照査パターン (ρm, αf), whichever way it is pushed:
# ① 復旧性L2, ② 安全性L2, ③ 損傷レベル, ④ 破壊形態の検討, ⑤ せん断耐力, ⑥ L1, ⑦ 基礎の安定, ⑧ 杭の段落し,
# ⑨ 断面力ピックアップ. ③ all but (1.0, 2.0), ④ ρm 1.2, ⑤ none, ⑥ (1.0, 1.0), ⑦⑧⑨ αf 1.0.
CHECKS = {
    (Decimal("1.0"), Decimal("1.0")): (True, True, True, False, False, True, True, True, True),
    (Decimal("1.2"), Decimal("1.0")): (True, True, True, True, False, False, True, True, True),
    (Decimal("1.0"), Decimal("2.0")): (True, True, False, False, False, False, False, False, False),
    (Decimal("1.2"), Decimal("2.0")): (True, True, True, True, False, False, False, False, False),
}
Checks = tuple[bool, ...]


class ProjectError(ValueError):
    """The JRSNAP results cannot be named in the project (not the input's fault)."""


@dataclass(frozen=True)
class Project:
    """What the project XML takes from the input and the NDU; everything else is a fixed condition."""

    region: int  # index of REGIONS (A, B, C)
    ground_class: int  # index of GROUND_CLASSES (G0 .. G5)
    shear_span: Printed  # La of the nonlinear member, mm
    footing_joint: int  # FootInfo joint: the direct foundation that is checked
    cases: tuple[Checks, ...]  # the check items ①..⑨ of each combination of the NDU, one DB1 each


def _choice(value: str | None, options: tuple[str, ...], key: str) -> int:
    if value is None:
        raise InputError(f"{SECTION}.{key}: 値が必要です（静的非線形解析の耐震照査の入力に使います）")
    return options.index(value)


def _checks(model: NduModel) -> tuple[Checks, ...]:
    found = []
    for number, combination in enumerate(model.combinations, 1):
        pattern = (Decimal(repr(combination.rho_m.value)), Decimal(repr(combination.alpha_f.value)))
        if pattern not in CHECKS:
            raise ValueError(f"組合せ {number} の照査パターン ρm={pattern[0]}・αf={pattern[1]} の照査項目がありません")
        found.append(CHECKS[pattern])
    return tuple(found)


def build_project(model: NduModel, pier: PierInput) -> Project:
    """The project of the NDU *model*; a blank 耐震設計条件 is an input error."""
    design = pier.seismic_design
    nonlinear = [element for element in model.elements if element.nonlinear]
    if len(nonlinear) != 1:  # the NDU has one M-θ member, the column base; Aggre-SE's member type 2 is it
        raise InputError(f"JRSNAP の非線形部材が{len(nonlinear)}個です（耐震照査の入力は1個だけに対応します）")
    return Project(region=_choice(design.region, REGIONS, "地域別"),
                   ground_class=_choice(design.ground_class, GROUND_CLASSES, "地盤区分"),
                   shear_span=model.section.shear_span, footing_joint=model.footing.node, cases=_checks(model))


def databases(folder: str, names: Iterable[str], cases: int) -> tuple[str, ...]:
    """The DB1 of each Case 1..*cases* among the result files *names*, as a path from the XML (``folder/name``)."""
    found: dict[int, str] = {}
    for name in names:
        if match := _CASE.fullmatch(name):
            case = int(match[1])
            if case in found:
                raise ProjectError(f"Case{case} の DB1 が2つあります: {found[case]}, {name}")
            found[case] = name
    if sorted(found) != list(range(1, cases + 1)):
        raise ProjectError(f"JRSNAP の結果に Case1〜{cases} の DB1 がそろっていません（{sorted(found.values())!r}）")
    return tuple(f"{folder}/{found[case]}" for case in range(1, cases + 1))
