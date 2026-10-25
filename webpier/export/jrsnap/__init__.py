"""JRSNAP 5.2-L03 input (NDU) of the 0710 / 0720 seismic frames (CONTEXT.md JRSNAP入力モデル).

``build`` makes the ``model.NduModel`` of one direction from the calc results and its ``profile``; ``records``
lays it out in the native record order; ``writer`` formats the records as CP932 / CRLF bytes and checks them with
``validate``, the strict validator of this dialect. Saving or reading back an NDU is not an analysis. ``diagrams``
decides which combination each basic case of the 荷重図 is drawn from.
"""

from .build import build_ndu
from .build_pile import build_pile_ndu
from .diagrams import diagram_combinations
from .profile import LONGITUDINAL, TRANSVERSE, Profile
from .validate import validate_ndu
from .writer import write_ndu, write_pile_ndu

__all__ = ["LONGITUDINAL", "TRANSVERSE", "Profile", "build_ndu", "build_pile_ndu", "diagram_combinations", "validate_ndu",
           "write_ndu", "write_pile_ndu"]
