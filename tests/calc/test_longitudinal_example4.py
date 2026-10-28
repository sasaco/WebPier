"""0610 basic cases of Example橋脚4 against the sample's load diagrams (第III編 2.2 荷重図, III-58〜III-67).

The sample is transcribed independently in tests/fixtures/example4/longitudinal_loads.json (36 cases, notes in
longitudinal_frame_notes.md). Each value WebPier makes is compared with it: equal to the printed digits, or, where it
differs for a classified reason, equal to an independent hand calculation from printed operands (the 0600 values
already hand-checked in tests/calc/test_reaction*.py, the input's levers f, the factors) and different from the
transcription. Codes (reaction_notes.md「WebPier との照合」):

- (見本) error n: the sample's error n of reaction_notes.md「見本の中の食い違い」
    1 RA/RB of ① (RB 368.3 against WebPier 379.44), 2 placing ② (WebPier picks A-17, RB 415.14),
    3 placing ③ (RC 913.75 / RD 786.25), 4 the pier-body ratio of ① (0.800 against 0.799), 5 the long rail
    (400.0 / 300.0 against 160.00 / 500.00).
- (見本) 表2.3.2: 表2.3.2's remarks put Wp2-1 in the low-water and Wp2-2 in the high-water combinations; the load
  diagrams head them 高水位 / 低水位 the other way round. WebPier follows the table (as
  tests/calc/test_longitudinal_combinations.py), so the low-water buoyancy (none) is compared with Wp2-1's diagram.
- (2): not expressible in the input. The input has the single-track girder impact only; WebPier derives the
  double-track one as i × (1 − L/200) (decision 23: origin 0.542 × (1 − 7.2/200) = 0.522 against the sample's
  0.512 from the girder calculation; end 0.591 × 0.88 = 0.520 equal) and the serviceability one as 0.75 × it
  (0.392 against 0.384; end 0.390 equal).
- (3): standard or method. The modelling of the pile frame (the beam weight at the beam top, the column as its own
  line load, the footing and soil at the footing centroid: decision 81; the sample spreads them along members), the
  braking of one track for double track (question 11), and the girder impact (1 + i) in the bearing's Rm (0600; the
  sample adds the pier-body impact loads of 表2.1.6 / 2.1.7).

Decision 119 (the braking-maximum Rm without impact) and decision 120 (the reduced dead loads 0.9 D1 + 0.8 D2) are
what the sample does too (III-47〜III-49 ② ③ have no I; ③ and ⑤ are reduced), so they cause no difference here.

Sign: the sample prints M = R起 × 0.70 − R終 × 0.20 (III-30, III-34); WebPier's M is positive as N × (+x lever),
the end side +x (frame.PointLoad), so its M is the sample's with the sign reversed. H is +x in both.
"""

from decimal import Decimal
import json

import pytest

from reaction_support import D, FIXTURES, value
from test_longitudinal_combinations import SYMBOL, example4
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import BasicCase, Layout

B = BasicCase
BOTH, ORIGIN, END = Layout.BOTH, Layout.ORIGIN, Layout.END
LOADS = json.loads((FIXTURES / "example4" / "longitudinal_loads.json").read_text(encoding="utf-8"))
SAMPLE = {case["symbol"]: case for case in LOADS["cases"]}

E1, E2, E3, E4, E5 = (f"(見本) error {n}" for n in range(1, 6))
WATER = "(見本) 表2.3.2"
INPUT, METHOD = "(2)", "(3)"

COLUMN = D("9.2")  # the column line from the beam top to the footing top: H2 + H3 + H4 = 1.5 + 0.5 + 7.2 (III-28 9.20)
HALF_PILES = D("2.5")  # nodes 4 and 5 from the footing centre: the printed 5.00 / 2
I2 = "I2"  # the serviceability impact: not a basic case in WebPier, compared from Impacts.service_double
PLACING = {"1": BOTH, "2": ORIGIN, "3": END}


def webpier_case(symbol):
    """(BasicCase or I2, placing) of a sample symbol; the mapping of 表2.3.1 / 2.3.2 (SYMBOL)."""
    if symbol in ("D1", "D2", "Wp1"):
        return {"D1": B.D1, "D2": B.D2, "Wp1": B.BUOYANCY_NORMAL}[symbol], None
    if symbol in ("Wp2-1", "Wp2-2"):
        return SYMBOL[symbol], None
    prefix, placing = symbol.removesuffix("-使").rsplit("-", 1)
    if prefix == "(LR)6":
        return B.SERVICE_LR08, None
    if prefix == "I2":
        return I2, PLACING[placing]
    return SYMBOL[prefix], PLACING[placing]


def quantities(symbol):
    if symbol == "D1":
        return ("P", "M", "H", "q_column", "N_column_bottom", "P_footing", "M_footing")
    if symbol == "D2":
        return ("P", "M", "H", "P_footing", "M_footing")
    if symbol.startswith("Wp"):
        return ("P_footing", "M_footing")
    if symbol.startswith("I2"):
        return ("P", "M")
    return ("P", "M", "H")


# --- the sample's values (from the transcription) ------------------------------------------------------------------

def sample_values(symbol):
    case = SAMPLE[symbol]
    top = {load["type"]: D(load.get("value_kN", load.get("value_kNm")))
           for load in case["nodal_loads"] if load["node"] == 1}
    found = {"P": top.get("P", Decimal(0)), "M": -top.get("M", Decimal(0)), "H": top.get("H", Decimal(0))}
    # A line load is printed without sign; its direction is the arrow (Wp2-1's 176.00 kN/m points up).
    lines = {line["member"]: D(line["value_kN_per_m"]) * (-1 if line["direction"].startswith("上向き") else 1)
             for line in case["distributed_loads"]}
    # Footing resultant: the end P at nodes 4 and 5, the footing line load over 5.00, and the moment about the centre
    # (ΣM + P5 × 2.5 − P4 × 2.5). Wp2-1's two moments overlap and their signs are unreadable (sign_uncertain): read
    # as D1's rule for an upward load, left +88.00 and right −88.00 (notes), so they cancel as D1's ∓215.60 do.
    ends = [load for load in case["nodal_loads"] if load["node"] in (4, 5)]
    p = sum((D(load["value_kN"]) for load in ends if load["type"] == "P"), Decimal(0))
    moment = Decimal(0)
    for load in ends:
        sign = -1 if load["node"] == 4 else 1
        if load["type"] == "P":
            moment += sign * HALF_PILES * D(load["value_kN"])
        elif load.get("sign_uncertain"):
            moment += -sign * abs(D(load["value_kNm"]))
        else:
            moment += D(load["value_kNm"])
    found["P_footing"] = p + lines.get("(3)(4)", Decimal(0)) * 2 * HALF_PILES
    found["M_footing"] = moment
    if "(1)" in lines:
        found["q_column"] = lines["(1)"]
        found["N_column_bottom"] = found["P"] + lines["(1)"] * COLUMN
    return {key: found[key] for key in quantities(symbol)}


# --- WebPier's values ------------------------------------------------------------------------------------------------

def webpier_values(result, symbol):
    case, placing = webpier_case(symbol)
    if case == I2:
        impacts = {BOTH: result.impact, ORIGIN: result.one_girder[0].impact, END: result.one_girder[1].impact}
        table = impacts[placing].service_double
        return {"P": value(table.n), "M": value(table.m)}
    basic = result.basic(case, placing or BOTH)
    assert (basic.case, basic.layout) == (case, placing)
    points = {point.anchor: point for point in basic.points}
    assert set(points) <= {NodeRole.CAP_TOP, NodeRole.FOOTING_CENTROID}
    found = {}
    if NodeRole.CAP_TOP in points:
        cap = points[NodeRole.CAP_TOP]
        assert cap.node == 1  # the train path's seat: the beam top (no pedestal), the sample's node 1
        found.update(P=value(cap.n), M=value(cap.m), H=value(cap.h))
    else:
        found.update(P=Decimal(0), M=Decimal(0), H=Decimal(0))
    footing = points.get(NodeRole.FOOTING_CENTROID)
    found["P_footing"] = value(footing.n) if footing else Decimal(0)
    found["M_footing"] = value(footing.m) if footing else Decimal(0)
    if basic.line_loads:
        (column,) = basic.line_loads
        assert column.members == (1, 2, 3)  # beam top → beam bottom → column top → footing top
        found["q_column"] = value(column.n)
        found["N_column_bottom"] = found["P"] + found["q_column"] * COLUMN
    return {key: found[key] for key in quantities(symbol)}


# --- the expected differences: {symbol: {quantity: (WebPier by hand, codes)}}; every other quantity agrees ----------

def h(total):
    """A horizontal case: only H differs (N = M = 0 in both)."""
    return {"H": total}


DIFFERENT = {
    # D1. Sample: P = 5960.00 at node 1 and the whole body 2422.6 / 9.20 = 263.30 kN/m along the column. WebPier
    # (decision 81): the beam at the beam top, prism 2.5 × 7.7 × 1.5 × 24.5 = 707.44 and haunch
    # 0.5/6 × (2.5 × 7.7 + 2.5 × 3.5 + 2 × (2.5 × 7.7 + 2.5 × 3.5)) = 7.000 m³ × 24.5 = 171.50, the column
    # q = 3.5 × 2.5 × 24.5 = 214.375 -> 214.38 from the beam top, less the overlap q × (H2 + H3):
    # P = 1710.00 + 4250.00 + 707.44 + 171.50 − 214.38 × 2.0 = 6410.18. The resultant at the column bottom
    # 6410.18 + 214.38 × 9.2 = 8382.476 against 5960.00 + 263.30 × 9.2 = 8382.36: the sample's Ds 2422.6 (rows
    # rounded, V3 2.63) and its 263.30 rounding against WebPier's Ds 2422.44 and the q rounding (+0.04).
    # M = −1710.00 × 0.70 + 4250.00 × 0.20 = −347.00 agrees (the beam centred, lever 0). The footing
    # 7.0 × 8.0 × 2.2 × 24.5 = 3018.40 at the centroid equals the sample's 431.20 × 5.00 + 2 × 431.20.
    "D1": {"P": ("6410.18", (METHOD,)), "q_column": ("214.38", (METHOD,)),
           "N_column_bottom": ("8382.476", (METHOD,))},
    # D2: P = 470.00 + 1050.00 = 1520.00 and M = −470.00 × 0.70 + 1050.00 × 0.20 = −119.00 agree. The soil at the
    # centroid: (7.0 × 8.0 × 0.5 − 2.5 × 3.5 × 0.5) × 18.0 = 504.00 − 78.75 = 425.25; the sample spreads
    # 425.3 / 7.00 = 60.80 kN/m (rounded) with end loads, 60.80 × 7 = 425.60.
    "D2": {"P_footing": ("425.25", (METHOD,))},
    # Low water hw3 = 0 is at the footing base: no buoyancy. The diagram Wp2-1 (headed 高水位) is
    # −176.00 × 5.00 − 2 × 176.00 = −1232.00, which is WebPier's high-water buoyancy (asserted below).
    "Wp2-1": {"P_footing": ("0", (WATER,))},
    # High water hw1 = 2.2 at the footing top: −10.0 × 7.0 × 8.0 × 2.2 = −1232.00; the diagram Wp2-2 (headed 低水位)
    # is empty.
    "Wp2-2": {"P_footing": ("-1232.00", (WATER,))},
    # Train, double track (× 2), lever −0.70 / +0.20, each row rounded:
    # ① P = 2 × 379.44 + 2 × 697.71 = 758.88 + 1395.42 = 2154.30; M = −531.216 -> −531.22 + 279.084 -> 279.08
    #   = −252.14 (sample 2132.0, 236.5 from RB 368.3).
    "L1-1": {"P": ("2154.30", (E1,)), "M": ("-252.14", (E1,))},
    # ② (A-17): P = 2 × 415.14 = 830.28; M = −830.28 × 0.70 = −581.196 -> −581.20 (sample 698.8, 489.2).
    "L1-2": {"P": ("830.28", (E2,)), "M": ("-581.20", (E2,))},
    # ③: P = 2 × 913.75 = 1827.50; M = 1827.50 × 0.20 = 365.50 (sample 1763.8, −352.8).
    "L1-3": {"P": ("1827.50", (E3,)), "M": ("365.50", (E3,))},
    # Impact (safety): i = girder i0 (double) × β, β = 1 − Ds / (L + Du + Ds), Ds = 2422.44, Du = 7480.00, L the
    # placing's double-track train; 3 decimals each. i0: origin 0.522 (2), end 0.520.
    # ① β = 1 − 2422.44 / (2154.30 + 7480.00 + 2422.44) = 0.799 (sample 0.800, error 4);
    #   i = 0.522 × 0.799 = 0.417, 0.520 × 0.799 = 0.415; P = 758.88 × 0.417 = 316.45 + 1395.42 × 0.415 = 579.10
    #   = 895.55; M = −316.45 × 0.70 = −221.515 -> −221.52 + 579.10 × 0.20 = 115.82 = −105.70.
    "I1-1": {"P": ("895.55", (E1, E4, INPUT)), "M": ("-105.70", (E1, E4, INPUT))},
    # ② β = 1 − 2422.44 / (830.28 + 9902.44) = 0.774; i = 0.522 × 0.774 = 0.404; P = 830.28 × 0.404 = 335.43;
    #   M = −335.43 × 0.70 = −234.801 -> −234.80.
    "I1-2": {"P": ("335.43", (E2, INPUT)), "M": ("-234.80", (E2, INPUT))},
    # ③ β = 1 − 2422.44 / (1827.50 + 9902.44) = 0.793; i = 0.520 × 0.793 = 0.412 (the sample's 0.412 too);
    #   P = 1827.50 × 0.412 = 752.93; M = 752.93 × 0.20 = 150.586 -> 150.59.
    "I1-3": {"P": ("752.93", (E3,)), "M": ("150.59", (E3,))},
    # Impact (serviceability, I2): i0 = 0.75 × 0.522 = 0.392 (2), 0.75 × 0.520 = 0.390, × the same β.
    # ① 0.392 × 0.799 = 0.313, 0.390 × 0.799 = 0.312; P = 758.88 × 0.313 = 237.53 + 1395.42 × 0.312 = 435.37
    #   = 672.90; M = −237.53 × 0.70 = −166.271 -> −166.27 + 435.37 × 0.20 = 87.074 -> 87.07 = −79.20.
    "I2-1": {"P": ("672.90", (E1, E4, INPUT)), "M": ("-79.20", (E1, E4, INPUT))},
    # ② 0.392 × 0.774 = 0.303; P = 830.28 × 0.303 = 251.57; M = −251.57 × 0.70 = −176.099 -> −176.10.
    "I2-2-使": {"P": ("251.57", (E2, INPUT)), "M": ("-176.10", (E2, INPUT))},
    # ③ 0.390 × 0.793 = 0.309 (the sample's 0.309 too); P = 1827.50 × 0.309 = 564.70; M = 112.94.
    "I2-3-使": {"P": ("564.70", (E3,)), "M": ("112.94", (E3,))},
    # Bearing forces (0600, the sum at the beam top). μ = 0.1, n = 2; LR 10 kN/m × 8.000 × 2 = 160.00 (origin),
    # × 25.000 × 2 = 500.00 (end) (error 5); braking of one track (3): ① origin 0.25 × (190.56 + 379.44) = 142.50
    # (error 1: the sample's 127.5 per track leaves out E-17's following 50 kN/m), end 0.25 × (697.71 + 832.29)
    # = 382.50; ② origin 0.25 × (94.86 + 415.14) = 127.50 (A-17, error 2), end 0; ③ origin 0, end
    # 0.25 × (913.75 + 786.25) = 425.00. Rm (movable B: D at B and RB; fixed C: the far D and RD) takes the train
    # × 2 × (1 + girder i0) (3), or without impact in the braking maxima (decision 119, as the sample).
    # H1 = min(T/n, max(μRm, μT/n)): T/n in every case here (μRm above it). H2 = max(T − ½μRm, T/n).
    # (B+LR)1, 1.1D1 + 1.2D2 + 1.1(L + I) + 1.0LR + 1.0B:
    # ① H1 = (160.00 + 142.50)/2 = 151.25 (μRm = 0.1 × (1881 + 564 + 1.1 × 758.88 × 1.522) = 371.55);
    #   H2 = 882.50 − 0.05 × (4675 + 1260 + 1.1 × 1664.58 × 1.520 = 8718.18) = 446.59 (> 441.25). H = 597.84.
    "(B+LR)1-1": h(("597.84", (E1, E5, METHOD))),
    # ② H1 = (160.00 + 127.50)/2 = 143.75; H2 = T/n = 500.00/2 = 250.00 (500.00 − 0.05 × 5935.00 = 203.25). 393.75.
    "(B+LR)1-2": h(("393.75", (E2, E5, METHOD))),
    # ③ H1 = 160.00/2 = 80.00; H2 = 925.00 − 0.05 × (5935 + 1.1 × 1572.50 × 1.520 = 8564.22) = 496.79. 576.79.
    "(B+LR)1-3": h(("576.79", (E3, E5, METHOD))),
    # (1.1B+LR)2, 1.1D1 + 1.2D2 + 1.0L (no impact) + 1.0LR + 1.1B:
    # ① H1 = (160.00 + 1.1 × 142.50)/2 = 316.75/2 = 158.375 -> 158.38; H2 = 920.75 − 0.05 × (5935 + 1664.58
    #   = 7599.58) = 540.771 -> 540.77 (test_reaction_longitudinal). H = 699.15.
    "(1.1B+LR)2-1": h(("699.15", (E1, E5, METHOD))),
    # ② H1 = (160.00 + 140.25)/2 = 150.125 -> 150.13; H2 = 250.00. H = 400.13.
    "(1.1B+LR)2-2": h(("400.13", (E2, E5, METHOD))),
    # ③ H1 = 80.00; H2 = (500 + 1.1 × 425.00 = 967.50) − 0.05 × (5935 + 1572.50 = 7507.50) = 592.125 -> 592.13.
    #   H = 672.13.
    "(1.1B+LR)2-3": h(("672.13", (E3, E5, METHOD))),
    # (1.1B+LR)3, 0.9D1 + 0.8D2 (decision 120): ① H1 = 158.38; H2 = 920.75 − 0.05 × (3825 + 840 + 1664.58
    #   = 6329.58) = 604.27 (test_reaction_longitudinal). H = 762.65.
    "(1.1B+LR)3-1": h(("762.65", (E1, E5, METHOD))),
    # ② H1 = 150.13; H2 = 500.00 − 0.05 × 4665.00 = 266.75 (> 250.00). H = 416.88.
    "(1.1B+LR)3-2": h(("416.88", (E2, E5, METHOD))),
    # ③ H1 = 80.00; H2 = 967.50 − 0.05 × (4665 + 1572.50 = 6237.50) = 655.625 -> 655.63. H = 735.63.
    "(1.1B+LR)3-3": h(("735.63", (E3, E5, METHOD))),
    # (B+1.1LR)4, 1.1D1 + 1.2D2 + 1.0(L + I) + 1.1LR + 1.0B:
    # ① H1 = (176.00 + 142.50)/2 = 159.25; H2 = 932.50 − 0.05 × (5935 + 1664.58 × 1.520 = 8465.16) = 509.242
    #   -> 509.24. H = 668.49.
    "(B+1.1LR)4-1": h(("668.49", (E1, E5, METHOD))),
    # ② H1 = (176.00 + 127.50)/2 = 151.75; H2 = T/n = 550.00/2 = 275.00. H = 426.75.
    "(B+1.1LR)4-2": h(("426.75", (E2, E5, METHOD))),
    # ③ H1 = 176.00/2 = 88.00; H2 = 975.00 − 0.05 × (5935 + 1572.50 × 1.520 = 8325.20) = 558.74. H = 646.74.
    "(B+1.1LR)4-3": h(("646.74", (E3, E5, METHOD))),
    # (B+1.1LR)5, 0.9D1 + 0.8D2 (decision 120): ① H1 = 159.25; H2 = 932.50 − 0.05 × 7195.16 = 572.742 -> 572.74
    #   (test_reaction_longitudinal). H = 731.99.
    "(B+1.1LR)5-1": h(("731.99", (E1, E5, METHOD))),
    # ② H1 = 151.75; H2 = 550.00 − 0.05 × 4665.00 = 316.75. H = 468.50.
    "(B+1.1LR)5-2": h(("468.50", (E2, E5, METHOD))),
    # ③ H1 = 88.00; H2 = 975.00 − 0.05 × (4665 + 2390.20 = 7055.20) = 622.24. H = 710.24.
    "(B+1.1LR)5-3": h(("710.24", (E3, E5, METHOD))),
    # (LR)6, D1 + D2, 8 kN/m: LR 8 × 8.000 × 2 = 128.00, 8 × 25.000 × 2 = 400.00. H1 = 64.00 (μRm = 218.00);
    #   H2 = max(400.00 − 0.05 × 5300.00 = 135.00, 200.00) = 200.00. H = 264.00 (sample 160.0 + 120.0 = 280.0).
    "(LR)6-1": h(("264.00", (E5,))),
    # (LR)7, D1 + D2 + 1.0(L + I serviceability) + 1.0LR, no braking: H1 = 80.00, H2 = T/n = 250.00 for every
    #   placing (T − ½μRm < 250: ① 500 − 0.05 × 7613.77 = 119.31). H = 330.00 (sample 200.0 + 150.0 = 350.0).
    "(LR)7-1": h(("330.00", (E5,))),
    "(LR)7-2": h(("330.00", (E5,))),
    "(LR)7-3": h(("330.00", (E5,))),
    # (B+LR)8, D1 + D2 + 1.0(L + I) + 1.0LR + 1.0B:
    # ① H1 = 151.25; H2 = 882.50 − 0.05 × (5300 + 2530.16 = 7830.16) = 490.992 -> 490.99. H = 642.24.
    "(B+LR)8-1": h(("642.24", (E1, E5, METHOD))),
    # ② H1 = 143.75; H2 = 250.00 (500.00 − 0.05 × 5300.00 = 235.00). H = 393.75.
    "(B+LR)8-2": h(("393.75", (E2, E5, METHOD))),
    # ③ H1 = 80.00; H2 = 925.00 − 0.05 × (5300 + 1572.50 × 1.520 = 7690.20) = 540.49. H = 620.49.
    "(B+LR)8-3": h(("620.49", (E3, E5, METHOD))),
}
CODES = {E1, E2, E3, E4, E5, WATER, INPUT, METHOD}


@pytest.mark.parametrize("symbol", list(SAMPLE))
def test_each_basic_case_against_the_load_diagram(symbol):
    sample = sample_values(symbol)
    made = webpier_values(example4(), symbol)
    assert set(made) == set(sample)
    different = DIFFERENT.get(symbol, {})
    assert set(different) <= set(sample)
    for quantity in sample:
        if quantity in different:
            hand, codes = different[quantity]
            assert codes and set(codes) <= CODES
            assert made[quantity] == Decimal(hand), quantity
            assert Decimal(hand) != sample[quantity], quantity
        else:
            assert made[quantity] == sample[quantity], quantity


def test_the_count_of_compared_values():
    """108 values: D1 7, D2 5, the three buoyancies 2 each, L and I1 3 each (P, M, H), I2 2 each, the 22 horizontal
    cases 3 each; 46 differ by a classified reason, 62 agree."""
    compared = sum(len(quantities(symbol)) for symbol in SAMPLE)
    differing = sum(len(found) for found in DIFFERENT.values())
    assert (len(SAMPLE), compared, differing) == (36, 108, 46)


def test_the_diagram_heading_of_wp2_1_is_webpiers_high_water_buoyancy():
    """The contradiction of the sample, seen from the other side: the diagram headed 浮力（高水位）(Wp2-1) is
    WebPier's high-water buoyancy, and the empty one headed 浮力（低水位）(Wp2-2) its low-water one."""
    result = example4()
    assert value(result.basic(B.BUOYANCY_HIGH).points[0].n) == sample_values("Wp2-1")["P_footing"] == D("-1232.00")
    assert value(result.basic(B.BUOYANCY_LOW).points[0].n) == sample_values("Wp2-2")["P_footing"] == 0


# WebPier's basic cases in the order made, with the sample's symbol where one corresponds (its number in the
# diagrams is diagram_case). The orders differ: WebPier makes the buoyancies high, normal, low (the sample Wp1, Wp2-1,
# Wp2-2 read by 表2.3.2 as normal, low, high), the long-rail cases (LR)6 and (LR)7 before the braking ones, and the
# 1.1 LR maxima (4, 5) before the 1.1 B maxima (2, 3) (Define order, test_longitudinal_combinations). WebPier has
# SAFETY_LR10 and RESTORABILITY_LR10 (the 1.0 LR cases without the train of 0600) with no sample diagram; the sample's
# I2-1〜I2-3 are not basic cases in WebPier (the serviceability impact is the combination's basis of IMPACT_DOUBLE,
# decision 77). SERVICE_LR10 is made for each placing, as the sample's (LR)7-1〜7-3, with the same value.
ORDER = [
    (B.D1, None, "D1"), (B.D2, None, "D2"),
    (B.BUOYANCY_HIGH, None, "Wp2-2"), (B.BUOYANCY_NORMAL, None, "Wp1"), (B.BUOYANCY_LOW, None, "Wp2-1"),
    *((B.TRAIN_DOUBLE, layout, f"L1-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    *((B.IMPACT_DOUBLE, layout, f"I1-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    (B.SERVICE_LR08, None, "(LR)6-1"),
    *((B.SERVICE_LR10, layout, f"(LR)7-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    *((B.SAFETY_LR10_B, layout, f"(B+LR)1-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    *((B.SAFETY_LR11_B, layout, f"(B+1.1LR)4-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    *((B.SAFETY_LR11_B_REDUCED, layout, f"(B+1.1LR)5-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    *((B.SAFETY_LR10_BMAX, layout, f"(1.1B+LR)2-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    *((B.SAFETY_LR10_BMAX_REDUCED, layout, f"(1.1B+LR)3-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    (B.SAFETY_LR10, None, None),
    *((B.RESTORABILITY_LR10_B, layout, f"(B+LR)8-{n}") for n, layout in ((1, BOTH), (2, ORIGIN), (3, END))),
    (B.RESTORABILITY_LR10, None, None),
]


def test_the_order_made_against_the_sample_numbering():
    result = example4()
    assert [(basic.number, basic.case, basic.layout) for basic in result.basic_cases] == [
        (number, case, layout) for number, (case, layout, _) in enumerate(ORDER, 1)]
    # Each sample symbol of the list maps to that case (webpier_case), and every sample diagram but I2-1〜I2-3 has
    # its basic case.
    for case, layout, symbol in ORDER:
        if symbol is not None:
            assert webpier_case(symbol) == (case, layout)
    numbers = sorted(SAMPLE[symbol]["diagram_case"] for *_, symbol in ORDER if symbol is not None)
    assert numbers == [n for n in range(1, 37) if n not in (12, 13, 14)]
    assert [SAMPLE[s]["diagram_case"] for s in ("I2-1", "I2-2-使", "I2-3-使")] == [12, 13, 14]
    # The sample numbers in WebPier's order: equal positions up to I1-3, then the permutation above.
    assert [SAMPLE[symbol]["diagram_case"] if symbol else None for *_, symbol in ORDER] == [
        1, 2, 5, 3, 4, 6, 7, 8, 9, 10, 11, 30, 31, 32, 33, 15, 16, 17, 24, 25, 26, 27, 28, 29, 18, 19, 20, 21, 22, 23,
        None, 34, 35, 36, None]
