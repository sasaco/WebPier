"""SOIL-JR 5.2-L03 input (.sdt) of the ground of a pile foundation (0500 杭基礎, ADR-0013, decision 85).

``build_sdt`` writes the .sdt of a ``calc.pile_ground.PileGroundResult`` as SOIL-JR 5.2.3 saves it; ``parse_sdr`` reads
the design limits of the 基礎照査連携用データ (.sdr) SOIL-JR returns. WebPier does not calculate the ground springs: SOIL-JR
does, with the JRSNAP runner (pipeline.jrsnap).
"""

from .sdr import SdrError, SdrFile, SdrTable, parse_sdr
from .sdt import SOIL_JR_VERSION, build_sdt

__all__ = ["SOIL_JR_VERSION", "SdrError", "SdrFile", "SdrTable", "build_sdt", "parse_sdr"]
