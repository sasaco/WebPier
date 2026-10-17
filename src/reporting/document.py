"""Flow helpers and diagnostic output built only on GridLayoutPdf public APIs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import json
from pathlib import Path

from gridlayoutpdf import (
    Block, Columns, Document, FontRegistry, Heading, LayoutContext, LayoutOverflowError, LayoutPart,
    Line, MeasuredBlock, PageDecoration, PageProfile, Paragraph, ScenePage, Spacer,
    TextStyle, layout_trace, measure_block, render_pdf,
)

from .fonts import load_fonts
from .styles import BODY, BODY_LEADING, HEADING, REPORT_STYLE, finite, grid_units, report_profile


@dataclass(frozen=True)
class Leading:
    """Reserve an explicit baseline advance while preserving legal line splits."""

    block: Block
    leading: float = BODY_LEADING

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        rows = grid_units(self.leading, context.profile.grid.pitch_y)
        if rows <= 0:
            raise ValueError("leading must be positive")
        child = measure_block(self.block, context, available_width)
        if child.prefix:
            raise ValueError("Leading accepts paragraph/heading lines, not repeating headers")
        for part in child.parts:
            if part.rows > rows:
                raise LayoutOverflowError(
                    f"{child.block_id}: leading {self.leading} pt is smaller than the measured line",
                    block_id=child.block_id, needed=part.rows * child.row_pitch, available=self.leading,
                )
        return replace(child, parts=tuple(replace(part, rows=rows) for part in child.parts))


@dataclass(frozen=True)
class IndentTo:
    """Indent to a paper x-coordinate without fixed vertical positioning."""

    block: Block
    left: float

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        indent = finite(self.left, "left") - context.profile.grid.origin_x
        if indent < 0 or indent >= available_width:
            raise LayoutOverflowError("indent leaves no report width", needed=indent, available=available_width)
        child = measure_block(self.block, context, available_width - indent)

        def shifted(parts: tuple[LayoutPart, ...]) -> tuple[LayoutPart, ...]:
            return tuple(replace(part, commands=tuple(command.translated(indent, 0)
                                                     for command in part.commands),
                                 metadata={**part.metadata, "indent_pt": indent}) for part in parts)

        return replace(child, width=child.width + indent,
                       parts=shifted(child.parts), prefix=shifted(child.prefix))


def paragraph(
    text: str, *, left: float = 117, leading: float = BODY_LEADING,
    style: TextStyle = BODY, align: str = "left", block_id: str = "",
    min_first: int = 2, min_last: int = 2,
) -> Block:
    return IndentTo(Leading(Paragraph(text, style=style, align=align, block_id=block_id,
                                     min_first=min_first, min_last=min_last), leading), left)


def heading(text: str, *, left: float = 58.92, block_id: str = "") -> Block:
    return IndentTo(Leading(Heading(text, style=HEADING, block_id=block_id)), left)


def spacer(points: float = BODY_LEADING) -> Spacer:
    return Spacer(grid_units(points))


def columns(*blocks: Block, widths: Sequence[float], gap: float = 14.52,
            block_id: str = "") -> Columns:
    return Columns(*blocks, col_spans=tuple(grid_units(width) for width in widths),
                   gap_cols=grid_units(gap), block_id=block_id)


def report(*blocks: Block, fonts: FontRegistry | None = None,
           profile: PageProfile | None = None, header: str | None = None,
           footer: str | None = "{page}") -> Document:
    """Build a document; the caller still controls its staged destination."""
    decoration = None if footer is None else PageDecoration(
        footer, rows=grid_units(BODY_LEADING), gap_rows=grid_units(BODY_LEADING),
        align="right", style=BODY,
    )
    title = None if header is None else PageDecoration(
        header, rows=grid_units(BODY_LEADING), gap_rows=grid_units(BODY_LEADING),
        align="left", style=HEADING,
    )
    return Document(*blocks, fonts=fonts or load_fonts(), profile=profile or report_profile(),
                    style=REPORT_STYLE, header=title, footer=decoration)


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
