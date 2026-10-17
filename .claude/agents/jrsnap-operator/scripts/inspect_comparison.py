"""Review normalized differences or render selected page pairs from compare_manuals.py.

Examples:
  uv run --with pymupdf --with pillow python scripts/inspect_comparison.py Soil-JR
  uv run --with pymupdf --with pillow python scripts/inspect_comparison.py JRSNAP --start 300 --end 340
  uv run --with pymupdf --with pillow python scripts/inspect_comparison.py JRSNAP --pairs 69:69,335:335
"""
import argparse
import difflib
import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw
from compare_manuals import ROOT, norm

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('manual')
parser.add_argument('--start', type=int, default=0)
parser.add_argument('--end', type=int, default=9999)
parser.add_argument('--pages', help='Full text of selected new-version PDF pages')
parser.add_argument('--visual', action='store_true')
parser.add_argument('--pairs', help='old:new page pairs to render in side-by-side sheets; comma-separated')
args = parser.parse_args()
folder = ROOT / 'manual-comparison-data'
d = json.loads((folder / (args.manual+'.json')).read_text(encoding='utf-8'))
if args.pages:
    for page in map(int, args.pages.split(',')):
        p = d['new']['pages'][page-1]
        print(f"\nPDF {page} ({p['printed_page']})\n{p['text']}")
elif args.pairs:
    with pymupdf.open(ROOT/d['old']['file']) as a, pymupdf.open(ROOT/d['new']['file']) as b:
        for oldpage, newpage in (map(int, pair.split(':')) for pair in args.pairs.split(',')):
            images = []
            for doc, num in [(a,oldpage),(b,newpage)]:
                pix = doc[num-1].get_pixmap(dpi=96, alpha=False)
                images.append(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
            sheet = Image.new('RGB',(sum(im.width for im in images),max(im.height for im in images)+30),'white')
            draw = ImageDraw.Draw(sheet)
            x = 0
            for im, label in zip(images,[f'5.2-L03 / PDF {oldpage}', f'5.3-L01 trial2 / PDF {newpage}']):
                draw.text((x+10,8),label,fill='black'); sheet.paste(im,(x,30)); x += im.width
            path = folder / f'{args.manual}_compare_{oldpage:03d}_{newpage:03d}.png'
            sheet.save(path); print(path)
elif args.visual:
    for c in d['visual_changes']:
        if c['text_equal'] and c.get('changed_pixel_fraction',0)>.001:
            p = d['new']['pages'][c['new_page']-1]
            print(c['old_page'],c['new_page'],c['new_label'],round(c['changed_pixel_fraction'],3),p['text'].replace('\n',' ')[:140])
else:
    for c in d['text_changes']:
        if not args.start <= (c['old_page'] or c['new_page']) <= args.end:
            continue
        print(f"\nPDF {c['old_page']} ({c['old_label']}) -> {c['new_page']} ({c['new_label']})")
        a,b = norm(c['old_text']), norm(c['new_text'])
        for group in difflib.SequenceMatcher(None,a,b,autojunk=False).get_grouped_opcodes(n=30):
            for op,a0,a1,b0,b1 in group:
                if op=='equal': print('  '+a[a0:a1])
                else:
                    if a0!=a1: print('- '+a[a0:a1])
                    if b0!=b1: print('+ '+b[b0:b1])
