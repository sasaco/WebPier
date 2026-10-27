"""Mud of 0611 and 0621 for Example2 by hand, without the implementation (decisions 103 and 105).

Decision 105 counts the side bars in the 安全性（破壊） bending (all the axial bars, as the R5 sample Example橋脚4 does) and
decision 103 puts the track rows' corner D32 in the main bars across the track, so Capacita's Mud is no longer the H16
sample's (08_線路.pdf 8-15, 09_直角.pdf 9-19). It is compared with this hand calculation instead: the concrete by the
RC標準 stress-strain curve (the parabola k1·f'cd·(ε'/0.002)(2 − ε'/0.002) up to 0.002, then k1·f'cd, k1 = 1 − 0.003·f'ck ≦
0.85, ε'cu = (155 − f'ck)／30000 ≦ 0.0035) integrated over thin strips, f'cd = f'ck／γc, the bars elastic-plastic at
fyd = fyk／γs, the neutral axis found for the sample's N'd, Mud = Mu／γb. The bars are those of the drawing at their own
centres (not the count by area WebPier writes): each main face and one bar of each side face at each side bar centre.
Capacita gives 39497.2 and 59170.6 (0.11 % and 0.08 % below). The side bars lie near the neutral axis, so the rectangular
block over β·x is not close enough (0.22 % and 0.36 %).
"""

FCK, GAMMA_C, GAMMA_B = 27.0, 1.3, 1.1  # 8-14, 9-18
FYK, GAMMA_S, ES = 390.0, 1.0, 200000.0  # SD390
D19, D32 = 286.5, 794.2  # mm2, JIS G 3112
STRIPS = 4000
# (b, h, one main face's (area, centre from its face), the side bars (area, centres from the upper face; a bar on each
# side face), N'd in N) of each stage (column_section_check.json, column_section_check_09.json)
SECTIONS = {
    "0611": (4500.0, 2700.0, ((29 * D32, 108.0),), (D19, tuple(350.0 + 250.0 * i for i in range(9))), 15089.9e3),
    "0621": (2700.0, 4500.0, ((9 * D19, 102.0), (2 * D32, 108.0)), (D32, tuple(300.0 + 150.0 * i for i in range(27))),
             13264.1e3),
}


def mud(stage: str) -> float:
    """Mud (kN·m) of 安全性（破壊）の曲げ of *stage*, the side bars counted."""
    b, h, face, (side_area, side_centres), n_d = SECTIONS[stage]
    fcd, fyd = FCK / GAMMA_C, FYK / GAMMA_S
    ecu = min((155 - FCK) / 30000, 0.0035)
    k1 = min(1 - 0.003 * FCK, 0.85)
    bars = [*face, *((area, h - y) for area, y in face), *((2 * side_area, y) for y in side_centres)]

    def concrete(strain: float) -> float:
        if strain <= 0:
            return 0.0
        if strain <= 0.002:
            return k1 * fcd * strain / 0.002 * (2 - strain / 0.002)
        return k1 * fcd

    def forces(x: float) -> tuple[float, float]:
        force = moment = 0.0
        for index in range(STRIPS):
            y = (index + 0.5) * h / STRIPS
            part = concrete(ecu * (x - y) / x) * b * h / STRIPS
            force += part
            moment += part * (h / 2 - y)
        for area, y in bars:
            stress = max(-fyd, min(fyd, ES * ecu * (x - y) / x))
            force += area * stress
            moment += area * stress * (h / 2 - y)
        return force, moment

    low, high = 1.0, 3 * h
    for _ in range(80):
        x = (low + high) / 2
        low, high = (low, x) if forces(x)[0] > n_d else (x, high)
    return forces((low + high) / 2)[1] / 1e6 / GAMMA_B
