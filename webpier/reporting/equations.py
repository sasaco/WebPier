"""Structured formula helpers with paper-coordinate equal/result anchors."""

from __future__ import annotations

from dataclasses import dataclass, replace

from gridlayoutpdf import (
    Block, Equation, EquationAnchors, EquationGroup, LayoutContext, MathNode,
    MeasuredBlock, Script, measure_block,
)

from .document import indent_to
from .styles import BODY, finite, grid_units


def script(base: str | MathNode, *, superscript: str | MathNode | None = None,
           subscript: str | MathNode | None = None) -> Script:
    return Script(base, superscript=superscript, subscript=subscript, scale=6.5 / 9.9,
                  superscript_rise=4.92 if superscript is not None else None,
                  subscript_drop=1.92 if subscript is not None else None)


@dataclass(frozen=True)
class _PaperEquations:
    equations: tuple[Equation, ...]
    left: float
    first_equal: float
    second_equal: float | None
    result_right: float | None
    unit_start: float | None
    block_id: str
    label_width: float | None = None

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        pitch = context.profile.grid.pitch_x

        def relative(value: float | None) -> int | None:
            return None if value is None else grid_units(value - self.left, pitch)

        parts = []
        for index, equation in enumerate(self.equations):
            style = equation.style or BODY

            def relation_center(value: float | None, relation: str) -> int | None:
                if value is None:
                    return None
                # EquationAnchors uses relation centers; the application API
                # accepts native PDF text origins (left edges) from the reference.
                center = finite(value - self.left, "relation offset") + context.fonts.measure(relation, style).width / 2
                # Nearest fine-grid center introduces at most half a pitch.
                return round(center / pitch)

            first = relation_center(self.first_equal, equation.relation)
            assert first is not None
            anchors = EquationAnchors(first, relation_center(self.second_equal, equation.result_relation),
                                      relative(self.result_right), relative(self.unit_start))
            labels = None if self.label_width is None else grid_units(self.label_width, pitch)
            measured = measure_block(EquationGroup(equation, anchors=anchors, style=BODY, label_columns=labels,
                                                     gap=4.08, block_id=self.block_id), context, available_width)
            parts.extend(replace(part, metadata={**part.metadata, "equation_index": index}) for part in measured.parts)
        return MeasuredBlock(available_width, context.profile.grid.pitch_y, tuple(parts),
                             prefer_keep=True, block_id=self.block_id)


def equation_group(*equations: Equation, left: float = 117, first_equal: float = 169.92,
                   second_equal: float | None = None, result_right: float | None = None,
                   unit_start: float | None = None, block_id: str = "",
                   label_width: float | None = None) -> Block:
    """Use paper text-origin x values for relations, and right edges for results.

    Relation centers are rounded to the nearest 0.12 pt grid column at measure
    time, so their native text origins differ by at most 0.06 pt from the target.
    Each equation resolves its own relation font/width; no text is resized.
    An equation label (text written left-aligned at *left*, before the lhs) needs
    an explicit *label_width*: GridLayoutPdf sizes automatic labels for coarse grids.
    """
    return indent_to(_PaperEquations(equations, left, first_equal, second_equal,
                                     result_right, unit_start, block_id, label_width), left)
