"""FrameWeb (FEMPython / FrameWebforCS) input of the non-seismic frames.

``build`` writes the document of a frame and its case tables, ``cases`` builds those tables from a resolved
calc result and a ``Profile`` (the labels and spring sets of one direction), ``validate`` checks the native
rules. ``build_frameweb`` is 0610 and ``build_frameweb_transverse`` 0620, each a profile and the reading of its
result into ``cases.Source``; ``build_frameweb_generic`` is either with a load model (decision 70). The bytes of the file are ``core.integrity.dump_json(document)``.
"""

from .generic import build_frameweb_generic
from .longitudinal import LONGITUDINAL, build_frameweb
from .profile import Label, Profile
from .transverse import TRANSVERSE, build_frameweb_transverse
from .validate import validate_frameweb

__all__ = ["LONGITUDINAL", "TRANSVERSE", "Label", "Profile", "build_frameweb", "build_frameweb_generic",
           "build_frameweb_transverse", "validate_frameweb"]
