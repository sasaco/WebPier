"""Render pages of a reference PDF and a current PDF side by side (left: reference, right: current).

Usage:
    uv run --project "." --locked python -X utf8 .claude/skills/pier-report-style/scripts/compare_pages.py \
        --reference ".claude/docs/Example橋脚/output/0500_直接基礎.pdf" --current output/0500_直接基礎.pdf \
        --pages 1,2 --out <dir>

Pages are 1-based. The input PDFs are only read. A page missing from one PDF is left blank.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

DPI = 100
GAP = 16


def _pages(text: str) -> list[int]:
    pages: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            first, last = (int(value) for value in part.split("-", 1))
            pages.extend(range(first, last + 1))
        elif part:
            pages.append(int(part))
    if not pages or any(page < 1 for page in pages):
        raise argparse.ArgumentTypeError(f"pages must be 1-based numbers: {text!r}")
    return pages


def _render(document: pymupdf.Document, page: int) -> Image.Image | None:
    if page > document.page_count:
        return None
    pixmap = document[page - 1].get_pixmap(dpi=DPI)
    return Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", required=True, type=Path, help="見本 PDF（左）")
    parser.add_argument("--current", required=True, type=Path, help="現行 PDF（右）")
    parser.add_argument("--pages", required=True, type=_pages, help="頁番号（1始まり）。例: 1,2 や 3-5")
    parser.add_argument("--out", required=True, type=Path, help="PNG の出力先フォルダ")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(args.reference) as reference, pymupdf.open(args.current) as current:
        for page in args.pages:
            left, right = _render(reference, page), _render(current, page)
            if left is None and right is None:
                print(f"p{page}: both PDFs have fewer pages; skipped")
                continue
            size = (left or right).size
            left = left or Image.new("RGB", size, "white")
            right = right or Image.new("RGB", size, "white")
            width = left.width + GAP + right.width
            height = max(left.height, right.height)
            canvas = Image.new("RGB", (width, height), (200, 200, 200))
            canvas.paste(left, (0, 0))
            canvas.paste(right, (left.width + GAP, 0))
            ImageDraw.Draw(canvas).text((4, 4), f"reference p{page}", fill=(255, 0, 0))
            ImageDraw.Draw(canvas).text((left.width + GAP + 4, 4), f"current p{page}", fill=(255, 0, 0))
            target = args.out / f"{args.current.stem}_p{page:02d}.png"
            canvas.save(target)
            print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
