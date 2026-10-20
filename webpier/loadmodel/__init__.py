"""The 荷重モデル contract (CONTEXT.md, ADR-0010, decision 70): what a load model gives and what it may import.

A load model (the add-in of a project, read with ``--addin``) imports this package only. The application checks its
result with ``validate`` before it calculates.
"""

from .contract import (
    CONTRACT_VERSION, D1, D2, EQ2, PIER_WIND, SECTION_STAGES, WP_HIGH, WP_LOW, WP_NORMAL, BasicCase, BearingAction,
    BearingRef, BearingSlot, CantileverCombination, CantileverRow, CantileverTerm, Candidate, Combination, Context,
    ExtractionGroup, FrameDirection, Increment, LoadModel, LoadModelInputError, LoadModelResult, MaxResponse,
    Paragraph, Section, Seismic, SeismicCombination, SeismicDirection, Side, SpringTerm, Table, Term, pier_wind,
)
from .validate import bearing_label, validate

__all__ = [
    "CONTRACT_VERSION", "D1", "D2", "EQ2", "PIER_WIND", "SECTION_STAGES", "WP_HIGH", "WP_LOW", "WP_NORMAL",
    "BasicCase", "BearingAction", "BearingRef", "BearingSlot", "CantileverCombination", "CantileverRow",
    "CantileverTerm", "Candidate", "Combination", "Context", "ExtractionGroup", "FrameDirection", "Increment",
    "LoadModel", "LoadModelInputError", "LoadModelResult", "MaxResponse", "Paragraph", "Section", "Seismic",
    "SeismicCombination", "SeismicDirection", "Side", "SpringTerm", "Table", "Term", "bearing_label", "pier_wind",
    "validate",
]
