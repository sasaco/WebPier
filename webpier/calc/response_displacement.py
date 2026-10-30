"""The 応答変位法の解析 of a pile foundation (decision 97, CONTEXT.md 応答変位法の解析).

The inertia force and the 地盤変位 are put on one Case, in the two ways of 橋りょう編 解7.10.4・7.10.5 and both bounds of
the correction factor ν (解7.10.6・7.10.7, Example橋脚4 IV-55〜58):

- ① 1.0 Ra + νU f(z), ② 1.0 Ra + νL f(z), ③ νU Ra + 1.0 f(z), ④ νL Ra + 1.0 f(z), for L1 and for L2; a Case alike to an
  earlier one of its level is dropped (νU = 1.0 makes ③ the same as ①, Example橋脚4 表 3.7.6);
- α = Teq / (Tg / αg) to 3 decimals, αg 0.7 for L1 and 0.5 for L2 (耐震標準 解説表7.3.6); νU = 1.0 and νL = 0.0 up to
  0.75, −2.0α + 2.5 and −2.0α + 1.5 below 1.10, 0.3 and −0.7 from it, to 2 decimals; when the 最大応答震度 is past the
  bend of the whole structure (Aggre-SE's 全体系折曲点震度 Kheq), νU is 1.0 (耐震標準 解10.2.9);
- Ra is the inertia force up to the 最大応答震度: KhL1 for L1, the larger Khmax of 復旧性 and 安全性 for L2.

Teq, Kheq and the Kh come from Aggre-SE's summary workbook of the inertia Cases (its sheet 応答値一覧表, 12 Cases a band,
calc.aggrese_summary), from the Case of ρm 1.0 and αf 1.0 pushed forward, the only one Aggre-SE gives the response values
of. Aggre-SE gives one Teq a Case, so L1 and L2 share it (Example橋脚4 has 1.05 and 1.138 along the track, without saying where they come from).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..core.printed import Precision, Printed
from ._exact import d, put
from .aggrese_summary import SHEET, summary_bands

ALPHA = Precision(3, "")
FACTOR = Precision(2, "")
PERIOD = Precision(3, "s")  # Teq as Aggre-SE prints it
KH = Precision(3, "")
STIFFNESS_REDUCTION = {"L1": Decimal("0.7"), "L2": Decimal("0.5")}  # αg
LEVELS = ("L1", "L2")
LOWER_BEND, UPPER_BEND = Decimal("0.75"), Decimal("1.10")
ONE = Decimal("1.0")
# the rows read, by (block, heading) in the band of the Case: the block is column A's label of the rows from it on, the
# heading column B
_ROWS = (("降伏点", "全体系折曲点震度"), ("降伏点", "等価固有周期"), ("復旧性", "最大応答震度"), ("復旧性", "L1地震動"),
         ("安全性", "最大応答震度"))


class ResponseError(ValueError):
    """Aggre-SE's summary workbook does not hold the response values decision 97 reads."""


@dataclass(frozen=True)
class InertiaResponse:
    """The response of the inertia Case the 応答変位法 takes its Teq and Kh from."""

    case: int  # Aggre-SE's Case number
    name: str
    teq: Printed
    kheq: Printed  # 全体系折曲点震度
    kh_l1: Printed  # L1地震動
    kh_l2: Printed  # the larger 最大応答震度 of 復旧性 and 安全性


def read_inertia(xlsx: bytes, file: str, case: int) -> InertiaResponse:
    """The response of Case *case* of the summary workbook bytes *xlsx* (published as *file*), which must be of ρm 1.0
    and αf 1.0."""
    band, column = next(((band, index) for band in summary_bands(xlsx, file, ResponseError)
                         for index, number in band.cases if number == case), (None, None))
    if band is None:
        raise ResponseError(f"{file} の「{SHEET}」に Case{case} がありません")

    def text(block: str, heading: str) -> str:
        row = band.row(heading, block)
        if row is None:
            raise ResponseError(f"{file} の「{SHEET}」に{block}の「{heading}」の行がありません")
        return row[column]

    if (text("解析ケース", "ρm"), text("解析ケース", "αf")) != ("1.0", "1.0"):
        raise ResponseError(f"{file} の Case{case} は ρm 1.0・αf 1.0 の Case ではありません")
    values = []
    for block, heading in _ROWS:
        value = text(block, heading)
        try:
            values.append(Decimal(value))
        except InvalidOperation:
            what = f"{block} {heading}" if block != "降伏点" else heading
            raise ResponseError(f"{file} の Case{case} の「{what}」が数値ではありません（{value!r}）") from None
    kheq, teq, recovery, l1, safety = values
    return InertiaResponse(case, text("解析ケース", "名称"), put(PERIOD, teq), put(KH, kheq), put(KH, l1),
                           put(KH, max(recovery, safety)))


@dataclass(frozen=True)
class Correction:
    """The correction factors of one level (L1 or L2) and the 最大応答震度 its Cases go up to."""

    level: str
    teq: Printed
    tg: Printed
    alpha_g: Printed
    alpha: Printed
    upper: Printed  # νU of the formulas
    lower: Printed  # νL
    kh: Printed
    kheq: Printed
    yielded: bool  # the 最大応答震度 is past the bend: νU is 1.0

    @property
    def adopted(self) -> Printed:
        """The νU the Cases take."""
        return FACTOR(1.0) if self.yielded else self.upper


def correction(level: str, teq: Printed, tg: Printed, kh: Printed, kheq: Printed) -> Correction:
    alpha_g = STIFFNESS_REDUCTION[level]
    alpha = put(ALPHA, d(teq) / (d(tg) / alpha_g))
    a = d(alpha)
    if a <= LOWER_BEND:
        upper, lower = ONE, Decimal(0)
    elif a < UPPER_BEND:
        upper, lower = -2 * a + Decimal("2.5"), -2 * a + Decimal("1.5")
    else:
        upper, lower = Decimal("0.3"), Decimal("-0.7")
    return Correction(level, teq, tg, put(FACTOR, alpha_g), alpha, put(FACTOR, upper), put(FACTOR, lower), kh, kheq,
                      d(kh) > d(kheq))


@dataclass(frozen=True)
class ResponseCase:
    """One Case: Rt = inertia × Ra + displacement × f(z), up to the 最大応答震度 *kh* of its level."""

    level: str
    number: int  # ① .. ④
    inertia: Printed
    displacement: Printed
    kh: Printed


def response_cases(*corrections: Correction) -> tuple[ResponseCase, ...]:
    """The Cases of each level, ① .. ④ but those alike to an earlier one of the level."""
    cases: list[ResponseCase] = []
    one = FACTOR(1.0)
    for found in corrections:
        ways = ((one, found.adopted), (one, found.lower), (found.adopted, one), (found.lower, one))
        seen: set[tuple[float, float]] = set()
        for number, (inertia, displacement) in enumerate(ways, 1):
            if (inertia.value, displacement.value) not in seen:
                seen.add((inertia.value, displacement.value))
                cases.append(ResponseCase(found.level, number, inertia, displacement, found.kh))
    return tuple(cases)


@dataclass(frozen=True)
class ResponseDisplacementResult:
    """What 0711 / 0721 adds for the 応答変位法 (decision 97): the inertia Case read, the factors of L1 and L2 and the
    Cases, which follow the inertia Cases in Aggre-SE's project."""

    inertia: InertiaResponse
    corrections: tuple[Correction, ...]  # L1, L2
    cases: tuple[ResponseCase, ...]
    first_case: int  # the Case of Aggre-SE's project the first of *cases* is: after the inertia and liquefaction Cases


def response_displacement(inertia: InertiaResponse, tg: Printed, first_case: int) -> ResponseDisplacementResult:
    corrections = (correction("L1", inertia.teq, tg, inertia.kh_l1, inertia.kheq),
                   correction("L2", inertia.teq, tg, inertia.kh_l2, inertia.kheq))
    return ResponseDisplacementResult(inertia, corrections, response_cases(*corrections), first_case)


__all__ = ["Correction", "InertiaResponse", "ResponseCase", "ResponseDisplacementResult", "ResponseError",
           "correction", "read_inertia", "response_cases", "response_displacement"]
