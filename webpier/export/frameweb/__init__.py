"""FrameWeb (FEMPython / FrameWebforCS) input of the non-seismic frames.

``build`` writes the document of a frame and its case tables, ``cases`` builds those tables from a resolved
calc result and a ``Profile`` (the labels and spring sets of one direction), ``validate`` checks the native
rules. ``build_frameweb`` is 0610; 0620 is another profile and entry point next to it. The bytes of the file are
``core.integrity.dump_json(document)``.
"""

from .longitudinal import LONGITUDINAL, build_frameweb
from .profile import Label, Profile
from .validate import validate_frameweb

__all__ = ["LONGITUDINAL", "Label", "Profile", "build_frameweb", "validate_frameweb"]
