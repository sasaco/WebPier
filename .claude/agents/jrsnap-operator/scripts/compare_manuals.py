"""Reproducible read-only comparison of the supplied JRSNAP manuals.

Run: uv run --with pymupdf --with pillow python scripts/compare_manuals.py
PDF page references are 1-based. Originals are never modified.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]


def norm(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def extract(path):
    with pymupdf.open(path) as doc:
        pages = []
        for i, page in enumerate(doc):
            raw = page.get_text(sort=True)
            bottom = page.get_text(clip=pymupdf.Rect(0, page.rect.height - 65, page.rect.width, page.rect.height))
            labels = re.findall(r"(付\s*)?([0-9０-９]+)[-－−]([0-9０-９]+)(?!\d)", bottom)
            label = (('付' if labels[0][0] else '') + '-'.join(unicodedata.normalize('NFKC', s) for s in labels[0][1:])) if labels else ''
            # Remove only the page-number/version footer, not version mentions in the body.
            lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
            body = [line for line in lines if not re.search(r"操作説明書[：:]第|_Ver\d.*操作説明書", norm(line))
                    and not re.fullmatch(r"\d+[-−]\d+", norm(line))]
            text = "\n".join(body)
            pages.append({"pdf_page": i + 1, "printed_page": label, "text": text,
                          "normalized": norm(text), "raw_text": raw})
        return {"file": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size, "metadata": doc.metadata, "pages": pages}


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def align(a, b):
    """Anchor equal pages, then align intervening pages by ordered text similarity."""
    matcher = difflib.SequenceMatcher(None, [x['normalized'] for x in a], [x['normalized'] for x in b], autojunk=False)
    result = []
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == 'equal':
            result.extend(zip(range(a0, a1), range(b0, b1)))
            continue
        aa, bb = a[a0:a1], b[b0:b1]
        n, m = len(aa), len(bb)
        # Same-length runs almost always retain pagination; use labels as a shortcut.
        if n == m and all(x['printed_page'] == y['printed_page'] for x, y in zip(aa, bb)):
            result.extend(zip(range(a0, a1), range(b0, b1)))
            continue
        scores = [[0.0] * (m + 1) for _ in range(n + 1)]
        steps = [[None] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            scores[i][0], steps[i][0] = -0.45 * i, 'delete'
        for j in range(1, m + 1):
            scores[0][j], steps[0][j] = -0.45 * j, 'insert'
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                sim = similarity(aa[i-1]['normalized'], bb[j-1]['normalized'])
                candidates = [(scores[i-1][j-1] + 2 * sim - 1, 'pair'),
                              (scores[i-1][j] - 0.45, 'delete'), (scores[i][j-1] - 0.45, 'insert')]
                scores[i][j], steps[i][j] = max(candidates, key=lambda x: x[0])
        seq, i, j = [], n, m
        while i or j:
            op = steps[i][j]
            if op == 'pair':
                seq.append((a0+i-1, b0+j-1)); i -= 1; j -= 1
            elif op == 'delete':
                seq.append((a0+i-1, None)); i -= 1
            else:
                seq.append((None, b0+j-1)); j -= 1
        result.extend(reversed(seq))
    return result


def raster(page, dpi=60):
    # Footer excluded so the expected per-page version replacement does not mask figures.
    clip = pymupdf.Rect(0, 0, page.rect.width, page.rect.height - 45)
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False, clip=clip)
    return Image.frombytes('L', (pix.width, pix.height), pix.samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'manual-comparison-data')
    parser.add_argument('--skip-visual', action='store_true')
    parser.add_argument('--dpi', type=int, default=110)
    parser.add_argument('--render', nargs=3, metavar=('VERSION', 'MANUAL_PREFIX', 'PAGES'),
                        help='Render comma-separated 1-based pages, e.g. 53 Soil-JR 10,11')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    olddir, newdir = ROOT / 'JRSNAP_Ver5.2-L03', ROOT / 'JRSNAP_Ver5.3-L01体験版2'
    if args.render:
        version, prefix, nums = args.render
        path = next((olddir if version == '52' else newdir).glob(prefix + '*.pdf'))
        with pymupdf.open(path) as doc:
            numbers = []
            for part in nums.split(','):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    numbers.extend(range(start, end+1))
                else:
                    numbers.append(int(part))
            for number in numbers:
                dst = args.output / f'{prefix}_{version}_p{number:03d}.png'
                doc[number-1].get_pixmap(dpi=args.dpi, alpha=False).save(dst)
                print(dst)
        return
    manuals = []
    for oldpath in sorted(olddir.glob('*.pdf')):
        newpath = newdir / oldpath.name
        if not newpath.exists():
            raise FileNotFoundError(newpath)
        print('Extracting', oldpath.name, flush=True)
        old, new = extract(oldpath), extract(newpath)
        pairs = align(old['pages'], new['pages'])
        changes, visual, equal_count = [], [], 0
        with pymupdf.open(oldpath) as odoc, pymupdf.open(newpath) as ndoc:
            for ai, bi in pairs:
                a = old['pages'][ai] if ai is not None else None
                b = new['pages'][bi] if bi is not None else None
                same = a is not None and b is not None and a['normalized'] == b['normalized']
                entry = {'old_page': ai+1 if ai is not None else None, 'new_page': bi+1 if bi is not None else None,
                         'old_label': a['printed_page'] if a else '', 'new_label': b['printed_page'] if b else ''}
                if same:
                    equal_count += 1
                else:
                    entry.update(old_text=a['text'] if a else '', new_text=b['text'] if b else '')
                    entry['similarity'] = round(similarity(a['normalized'], b['normalized']), 4) if a and b else 0
                    changes.append(entry)
                if not args.skip_visual and ai is not None and bi is not None:
                    ia, ib = raster(odoc[ai]), raster(ndoc[bi])
                    if ia.size != ib.size:
                        metric = {'size_changed': True}
                    else:
                        delta = ImageChops.difference(ia, ib)
                        hist = delta.histogram()
                        metric = {'mae': round(ImageStat.Stat(delta).mean[0], 5),
                                  'changed_pixel_fraction': round(sum(hist[20:]) / (ia.width * ia.height), 6)}
                    if metric.get('size_changed') or metric.get('mae', 0) > 0:
                        visual.append({**{k:v for k,v in entry.items() if k.endswith('page') or k.endswith('label')},
                                       'text_equal': same, **metric})
        name = oldpath.stem.split('_')[0]
        record = {'name': name, 'old': old, 'new': new, 'equal_normalized_pages': equal_count,
                  'alignment': [[a+1 if a is not None else None, b+1 if b is not None else None] for a,b in pairs],
                  'text_changes': changes, 'visual_changes': visual}
        (args.output / f'{name}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        diff = []
        for c in changes:
            diff.append(f"\n=== {name}: old PDF {c['old_page']} ({c['old_label']}) -> new PDF {c['new_page']} ({c['new_label']}) ===\n")
            diff.extend(difflib.unified_diff((c['old_text']+'\n').splitlines(True), (c['new_text']+'\n').splitlines(True),
                                           fromfile='5.2-L03', tofile='5.3-L01 trial2', n=2))
        (args.output / f'{name}.diff.txt').write_text(''.join(diff), encoding='utf-8')
        summary = {'name': name, 'old_pages': len(old['pages']), 'new_pages': len(new['pages']),
                   'equal_normalized_pages': equal_count, 'changed_pairs': sum(c['old_page'] is not None and c['new_page'] is not None for c in changes),
                   'inserted_pages': [c['new_page'] for c in changes if c['old_page'] is None],
                   'deleted_pages': [c['old_page'] for c in changes if c['new_page'] is None],
                   'old_sha256': old['sha256'], 'new_sha256': new['sha256'],
                   'visual_diff_pages': len(visual), 'visual_only_pages': [c for c in visual if c['text_equal']]}
        manuals.append(summary)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('visual_only_pages','old_sha256','new_sha256')}, ensure_ascii=False), flush=True)
    extra = sorted(p.name for p in newdir.glob('*.pdf') if not (olddir / p.name).exists())
    (args.output / 'summary.json').write_text(json.dumps({'manuals':manuals, 'new_only_files':extra,
        'normalization':'NFKC + remove whitespace and page/version footers; no body-version or date removal',
        'raster':'PyMuPDF grayscale 60 dpi, bottom 45 pt excluded, changed pixel threshold 20/255'}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
