"""Flow helpers and diagnostic output built only on GridLayoutPdf public APIs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path

from gridlayoutpdf import (
    Block, Columns, Document, FontRegistry, Heading, Indent, LayoutContext, LayoutOverflowError, Leading,
    Line, MathBlock, MathNode, MeasuredBlock, PageDecoration, PageProfile, Paragraph, ScenePage, Spacer,
    Text, TextStyle, layout_trace, render_pdf,
)

from .fonts import load_fonts
from .styles import BODY, BODY_LEADING, HEADING, INDENT, REPORT_STYLE, finite, grid_units, report_profile


def indent_to(block: Block, left: float) -> Indent:
    """Place a body block at an authored paper x-coordinate of the report page."""
    return Indent(block, finite(left, "left") - report_profile().grid.origin_x)


def paragraph(
    text: str, *, left: float = 117, leading: float = BODY_LEADING,
    style: TextStyle = BODY, align: str = "left", block_id: str = "",
    min_first: int = 2, min_last: int = 2,
) -> Block:
    return indent_to(Leading(Paragraph(text, style=style, align=align, block_id=block_id,
                                       min_first=min_first, min_last=min_last),
                             grid_units(leading)), left)


@dataclass(frozen=True)
class _TaggedHeading:
    """A one-line heading followed on its baseline by a source tag in a column of its own."""

    text: str
    tag: str
    tag_offset: float
    block_id: str

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        measured = Heading(self.text, style=HEADING, block_id=self.block_id).measure(context, available_width)
        texts = [command for part in measured.parts for command in part.commands if isinstance(command, Text)]
        tag = context.fonts.normalize_text(self.tag)
        tag_width = context.fonts.measure(tag, HEADING).width
        if len(measured.parts) != 1 or len({command.y for command in texts}) != 1:
            raise LayoutOverflowError(f"{self.block_id or 'heading'}: a tagged heading must fit one line",
                                      block_id=self.block_id, available=available_width)
        right = max(command.x + context.fonts.measure(command.text, HEADING).width for command in texts)
        # Reference 0500: the tag stands at 340.8, or one 14.52 pt indent further per
        # step while it would come closer than one full-width character to the heading.
        steps = max(0, math.ceil((right + HEADING.size - self.tag_offset) / INDENT - 1e-9))
        x = self.tag_offset + steps * INDENT
        if x + tag_width > available_width:
            raise LayoutOverflowError(f"{self.block_id or 'heading'}: tag needs {x + tag_width:g} pt; "
                                      f"available width is {available_width:g} pt",
                                      block_id=self.block_id, needed=x + tag_width, available=available_width)
        part = measured.parts[0]
        return replace(measured, parts=(replace(part, commands=(
            *part.commands, Text(x, texts[0].y, tag, HEADING))),))


def heading(text: str, *, left: float = 58.92, tag: str | None = None, tag_left: float = 340.8,
            block_id: str = "") -> Block:
    """A heading; *tag* (e.g. "【基礎標準 13.2.2.2】") goes at *tag_left* + k × 14.52 on the same line."""
    block: Block = Heading(text, style=HEADING, block_id=block_id) if tag is None else _TaggedHeading(
        text, tag, finite(tag_left, "tag_left") - finite(left, "left"), block_id)
    return indent_to(Leading(block, grid_units(BODY_LEADING)), left)


def math_line(node: MathNode | str, *, left: float = 117, style: TextStyle = BODY,
              block_id: str = "") -> Block:
    """One body line of text or math on the 14.28 pt row; the baseline is the report's 11.52 pt.

    The row is strict: a taller line raises LayoutOverflowError. A 6.5 pt subscript reaches
    0.07 pt below the row, so a 0.12 pt overhang keeps the row.
    """
    return indent_to(Leading(MathBlock(node, style=style, block_id=block_id), grid_units(BODY_LEADING),
                             minimum=False, overhang=0.12), left)


def spacer(points: float = BODY_LEADING) -> Spacer:
    """A blank line; one that would come first on a page is dropped, so every page starts at its first row."""
    return Spacer(grid_units(points), discard_at_page_top=True)


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


def columns(*blocks: Block, widths: Sequence[float], gap: float = 14.52,
            block_id: str = "") -> Columns:
    return Columns(*blocks, col_spans=tuple(grid_units(width) for width in widths),
                   gap_cols=grid_units(gap), block_id=block_id)


def report(*blocks: Block, fonts: FontRegistry | None = None,
           profile: PageProfile | None = None, header: str | None = None) -> Document:
    """Build a document without page numbers; the caller still controls its staged destination."""
    title = None if header is None else PageDecoration(
        header, rows=grid_units(BODY_LEADING), gap_rows=grid_units(BODY_LEADING),
        align="left", style=HEADING,
    )
    return Document(*blocks, fonts=fonts or load_fonts(), profile=profile or report_profile(),
                    style=REPORT_STYLE, header=title)


def coarse_overlay(pages: Sequence[ScenePage], *, step_x: float = 14.52,
                   step_y: float = 14.28) -> tuple[ScenePage, ...]:
    """Append sparse inspection lines to the exact already-computed scenes."""
    finite(step_x, "step_x", positive=True)
    finite(step_y, "step_y", positive=True)
    result = []
    color = (.84, .87, .9)
    for page in pages:
        grid = page.profile.grid
        left, top = grid.origin_x, grid.origin_y
        right, bottom = grid.x(grid.columns), grid.y(grid.rows)
        lines = tuple(Line(left + number * step_x, top, left + number * step_x, bottom, .12, color)
                      for number in range(int((right - left) / step_x) + 1))
        lines += tuple(Line(left, top + number * step_y, right, top + number * step_y, .12, color)
                       for number in range(int((bottom - top) / step_y) + 1))
        result.append(replace(page, commands=(*page.commands, *lines)))
    return tuple(result)


def validate_overlay(normal: Sequence[ScenePage], overlay: Sequence[ScenePage]) -> None:
    """Reject body drift or non-diagnostic additions before rendering QA PDFs."""
    if len(normal) != len(overlay):
        raise ValueError("overlay changed body page count")
    for page, diagnostic in zip(normal, overlay, strict=True):
        if (page.profile != diagnostic.profile or page.metadata != diagnostic.metadata
                or diagnostic.commands[:len(page.commands)] != page.commands):
            raise ValueError("overlay changed the body scene")
        additions = diagnostic.commands[len(page.commands):]
        if not additions or any(not isinstance(command, Line) or command.width != .12
                                or command.color != (.84, .87, .9) for command in additions):
            raise ValueError("overlay contains non-diagnostic scene additions")


@dataclass(frozen=True)
class ProofArtifacts:
    normal: Path
    overlay: Path
    trace: Path


def write_proof(pages: Sequence[ScenePage], fonts: FontRegistry,
                directory: str | Path, *, stem: str = "proof") -> ProofArtifacts:
    """Explicit QA output only; never invoked by ordinary staged report rendering."""
    import pymupdf

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = ProofArtifacts(directory / f"{stem}.pdf", directory / f"{stem}-overlay.pdf",
                               directory / f"{stem}-trace.json")
    diagnostic = coarse_overlay(pages)
    validate_overlay(pages, diagnostic)
    render_pdf(pages, artifacts.normal, fonts, invariant=True)
    render_pdf(diagnostic, artifacts.overlay, fonts, invariant=True)
    artifacts.trace.write_text(json.dumps(layout_trace(pages, fonts), ensure_ascii=False, indent=2),
                               encoding="utf-8")
    for path in (artifacts.normal, artifacts.overlay):
        with pymupdf.open(path) as pdf:
            for index, page in enumerate(pdf, 1):
                page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(
                    directory / f"{path.stem}-{index:03}.png")
    return artifacts
