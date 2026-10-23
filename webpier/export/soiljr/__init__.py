"""SOIL-JR 5.2-L03 input (.sdt) of the ground of a pile foundation (0500 杭基礎, ADR-0013, decision 85).

``build_sdt`` writes the .sdt of a ``calc.pile_ground.PileGroundResult`` as SOIL-JR 5.2.3 saves it; ``parse_sdr`` reads
the design limits of the 基礎照査連携用データ (.sdr) SOIL-JR returns and ``parse_sdc`` the ground springs of the
解析連携データ (.sdc) the frame of 0610 and 0620 takes (decision 88). WebPier does not calculate the ground springs: SOIL-JR
does, with the JRSNAP runner (pipeline.jrsnap).
"""

from .sdc import SdcError, parse_sdc
from .sdr import SdrError, SdrFile, SdrTable, parse_sdr
from .sdt import SOIL_JR_VERSION, build_sdt

__all__ = ["SOIL_JR_VERSION", "SdcError", "SdrError", "SdrFile",
           "SdrTable", "build_sdt", "parse_sdc", "parse_sdr"]
