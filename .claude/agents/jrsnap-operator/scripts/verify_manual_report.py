"""Verify report links, complete page coverage, and unchanged source-PDF hashes."""
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'manual-comparison-data'
REPORT = ROOT / 'JRSNAP_5.2と5.3体験版2_マニュアル比較レポート.md'
VERIFICATION = DATA / 'verification.json'

checks = {'links_checked': 0, 'source_pdfs_checked': 0, 'total_source_pages': 0, 'python_scripts_parsed': 0}
for document in [REPORT, DATA / 'README.md']:
    text = document.read_text(encoding='utf-8')
    assert '\ufffd' not in text, f'Replacement character in {document}'
    assert text.endswith('\n'), f'No final newline in {document}'
    for target in re.findall(r'\]\(([^\n]+?)\)', text):
        if not target.startswith(('https:', 'http:', '#')):
            path = document.parent / target.split('#')[0]
            if path.resolve() != VERIFICATION.resolve():
                assert path.exists(), f'Broken link: {path}'
            checks['links_checked'] += 1

summary = json.loads((DATA / 'summary.json').read_text(encoding='utf-8'))
assert len(summary['manuals']) == 6
assert not summary['new_only_files']
for manual in summary['manuals']:
    detail = json.loads((DATA / (manual['name']+'.json')).read_text(encoding='utf-8'))
    for version, index in [('old', 0), ('new', 1)]:
        record = detail[version]
        path = ROOT / record['file']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == record['sha256'] == manual[version+'_sha256'], f'Source changed: {path}'
        pages = len(record['pages'])
        assert pages == manual[version+'_pages']
        mapped = [pair[index] for pair in detail['alignment'] if pair[index] is not None]
        assert mapped == list(range(1, pages+1)), f'Incomplete page mapping: {path}'
        checks['source_pdfs_checked'] += 1
        checks['total_source_pages'] += pages
    assert len(detail['text_changes']) == manual['changed_pairs'] + len(manual['inserted_pages']) + len(manual['deleted_pages'])
assert checks['total_source_pages'] == 2415

ocr = json.loads((DATA / 'Soil-JR.ocr.json').read_text(encoding='utf-8'))
assert len(ocr) == 146
assert len({item['file'] for item in ocr}) == 146
assert all(item['text'].strip() for item in ocr)
checks['ocr_pages_checked'] = len(ocr)

for path in (ROOT / 'scripts').glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    checks['python_scripts_parsed'] += 1

checks['status'] = 'PASS'
VERIFICATION.write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
assert VERIFICATION.exists()
print(json.dumps(checks, ensure_ascii=False, indent=2))
