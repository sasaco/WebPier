"""Capacita (WebDanforCS / RcDan) input of the 0611 / 0621 柱の断面照査 (decision 48, ADR-0008).

``build_wdj`` writes the WDJ of the column bottom check from ``calc.column_check`` (without pickup data: Capacita's
Headless imports the PIK with ``run-rc --pickup``), ``point_index`` finds the point of a member's J end among the
points of the FEMPython PIK (``PickupError`` when it is not there), and ``write_wdj`` gives the bytes of the file
(``core.integrity.dump_json``).
"""

from .wdj import BODIES, PickupError, build_wdj, point_index, write_wdj

__all__ = ["BODIES", "PickupError", "build_wdj", "point_index", "write_wdj"]
