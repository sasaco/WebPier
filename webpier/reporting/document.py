"""Flow helpers built only on GridLayoutPdf public APIs; positions are grid columns from the body's left edge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from gridlayoutpdf import (
    Block, Columns, Document, Heading, Indent, LayoutContext, LayoutOverflowError, Leading, MathBlock, MathNode,
    MeasuredBlock, PageDecoration, Paragraph, Spacer, TextStyle, measure_block,
)

from .styles import BODY, HEADING, PITCH_X, REPORT_STYLE, columns_pt, count, report_profile

# A tagged heading's tag ("【基礎標準 13.2.2.2】") stands from this body column (the reference's 340.8 pt).
TAG_COLUMN = 18


def indent_to(block: Block, column: int) -> Indent:
    """Place a body block from the body column *column*."""
    return Indent(block, columns_pt(column))


def paragraph(
    text: str, *, left: int = 4, style: TextStyle = BODY, align: str = "left", block_id: str = "",
    min_first: int = 2, min_last: int = 2,
) -> Block:
    """A paragraph from the body column *left*, one grid row per line."""
    return indent_to(Leading(Paragraph(text, style=style, align=align, block_id=block_id,
                                       min_first=min_first, min_last=min_last), 1), left)


@dataclass(frozen=True)
class _TaggedHeading:
    """A one-line heading followed on its row by a source tag in columns of its own."""

    text: str
    tag: str
    tag_column: int  # from the heading's left edge
    block_id: str

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        width = context.fonts.measure(context.fonts.normalize_text(self.text), HEADING).width
        # The tag stands at its column, or whole columns further right while it would come closer than one
        # full-width character to the heading.
        first = max(self.tag_column, math.ceil((width + HEADING.size) / PITCH_X - 1e-9))
        total = math.floor(available_width / PITCH_X + 1e-9)
        tag = math.ceil(context.fonts.measure(context.fonts.normalize_text(self.tag), HEADING).width / PITCH_X - 1e-9)
        if first + tag > total:
            raise LayoutOverflowError(f"{self.block_id or 'heading'}: the heading and its tag need {first + tag} "
                                      f"grid columns; {total} are available", block_id=self.block_id,
                                      needed=(first + tag) * PITCH_X, available=available_width)
        block = Columns(Heading(self.text, style=HEADING, block_id=self.block_id),
                        Paragraph(self.tag, style=HEADING, block_id=self.block_id + ".tag"),
                        col_spans=(first, total - first), gap_cols=0, block_id=self.block_id + ".row")
        return measure_block(block, context, available_width)


def heading(text: str, *, left: int = 0, tag: str | None = None, tag_column: int = TAG_COLUMN,
            block_id: str = "") -> Block:
    """A heading from the body column *left*; *tag* (e.g. "【基礎標準 13.2.2.2】") from the body column
    *tag_column*, or further right when the heading is long."""
    block: Block = Heading(text, style=HEADING, block_id=block_id) if tag is None else _TaggedHeading(
        text, tag, count(tag_column, "tag_column") - count(left, "left"), block_id)
    return indent_to(Leading(block, 1), left)


def math_line(node: MathNode | str, *, left: int = 4, style: TextStyle = BODY, block_id: str = "") -> Block:
    """One body line of text or math on one grid row from the body column *left* (a taller line raises
    LayoutOverflowError)."""
    return indent_to(Leading(MathBlock(node, style=style, block_id=block_id), 1, minimum=False), left)


def spacer(rows: int = 1) -> Spacer:
    """A blank line; one that would come first on a page is dropped, so every page starts at its first row."""
    return Spacer(count(rows, "rows"), discard_at_page_top=True)


def is_blank(block: Block) -> bool:
    """A Spacer, possibly inside flow wrappers such as KeepWithNext."""
    while not isinstance(block, Spacer):
        child = getattr(block, "block", None)
        if child is None:
            return False
        block = child
    return True


def blank(out: list[Block]) -> None:
    """Append one blank line unless *out* is empty or already ends with one (blank lines never stack)."""
    if out and not is_blank(out[-1]):
        out.append(spacer())


def columns(*blocks: Block, widths: Sequence[int], gap: int = 1, block_id: str = "") -> Columns:
    """Blocks side by side, *widths* and *gap* in grid columns."""
    return Columns(*blocks, col_spans=tuple(count(width, "width", minimum=1) for width in widths),
                   gap_cols=count(gap, "gap"), block_id=block_id)


def report(*blocks: Block, header: str | None = None) -> Document:
    """A document without page numbers on the report's A4 grid; *header* heads every page."""
    title = None if header is None else PageDecoration(header, rows=1, gap_rows=1, align="left", style=HEADING)
    return Document(*blocks, profile=report_profile(), style=REPORT_STYLE, header=title)
