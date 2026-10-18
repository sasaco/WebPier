"""A stand-in for ``AggreSE.Headless.exe run``: the 耐震性能照査 of 0711 and 0721 (decisions 56, 57, ADR-0009).

It follows the runner's protocol as WebPier uses it (Batch/Aggre-SE/Headless/README.md): the arguments of
``webpier.pipeline.aggrese`` (``run --input <xml> --output-dir <dir> --snap-map <json>`` and the fixed switches of
``ARGUMENTS``), an output directory that must be absent or empty, a snap map that must name, by index, exactly the
DB1 the XML's ``SNAP/SnapDBPath`` names (resolved from the XML's folder) and that must exist, the files in the output
directory, and one UTF-8 JSON envelope (protocolVersion 1, engine aggrese, engineeringStatus not_evaluated) on stdout.
It reads the XML as Aggre-SE does (Shift-JIS, though it declares utf-16). Instead of calculating it writes:

- ``report.pdf``: one page per Case saying ``FAKE AGGRESE Case<n> <SHA256 of its DB1, 16 hex>``, then one
  page ``FAKE AGGRESE SUMMARY <SHA256 of the XML, 16 hex>``;
- ``pickup.pik``: ``Batch ver1.0.0`` and one line ``FAKE PIK <SHA256 of the XML, 16 hex>``, in Shift-JIS with CRLF;
- ``result.json``: ``{"command": "run", "cases": [...]}``;
and ``summary.cases`` lists each Case (caseNumber from 1, the DB1 name without its suffix, selected and aggregated).

When the real runner's protocol changes, change this too. ``FAKE_AGGRESE`` makes it misbehave, for the error tests:
fail, exit, text, list, protocol, engine, version, artifacts (one artifact listed twice), missing (report.pdf not
written), nopik (no pickup.pik returned), sha (report.pdf's SHA256 wrong), extra (an unlisted file), cases (no summary.cases), unaggregated (the
first Case not aggregated), broken (report.pdf is not a PDF), empty (report.pdf has no page), write (a file written
beside the DB1).
"""

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from pypdf import PdfWriter
from reportlab.pdfgen import canvas

SWITCHES = ["--summary-xlsx", "false", "--report-pdf", "true", "--check-tables", "false", "--pik", "true",
            "--pile-anchor-bar-pdf", "false"]


def envelope(ok, artifacts=(), errors=(), summary=None, **changes):
    value = {"protocolVersion": 1, "engine": "aggrese", "engineVersion": "fake-1", "readiness": "experimental",
             "ok": ok, "executionStatus": "success" if ok else "failed", "engineeringStatus": "not_evaluated",
             "summary": summary, "messages": [], "artifacts": list(artifacts), "errors": list(errors)}
    value.update(changes)
    return value


def failure(code, message, exit_code):
    print(json.dumps(envelope(False, errors=[{"code": code, "message": message}]), ensure_ascii=False))
    return exit_code


def report(lines):
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for line in lines:
        page.drawString(60, 780, line)
        page.showPage()
    page.save()
    return stream.getvalue()


def blank():
    stream = io.BytesIO()
    PdfWriter().write(stream)
    return stream.getvalue()


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    mode = os.environ.get("FAKE_AGGRESE", "")
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "list":
        sys.stdout.write("[]")
        return 0
    if (len(argv) != 7 + len(SWITCHES) or argv[0] != "run" or argv[1] != "--input" or argv[3] != "--output-dir"
            or argv[5] != "--snap-map" or argv[7:] != SWITCHES):
        return failure("INVALID_ARGUMENTS", " ".join(argv), 2)
    project, output, snaps = Path(argv[2]), Path(argv[4]), Path(argv[6])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), 2)
    data = project.read_bytes()
    root = ET.fromstring(data.decode("cp932").replace('encoding="utf-16"', "", 1))
    named = {str(index): str((project.parent / item.text).resolve())
             for index, item in enumerate(root.find("SNAP/SnapDBPath")) if item.text}
    mapped = json.loads(snaps.read_text(encoding="utf-8"))
    if mapped != named:
        return failure("SNAP_MAP_MISMATCH", f"{mapped!r} != {named!r}", 2)
    if missing := [path for path in mapped.values() if not Path(path).is_file()]:
        return failure("SNAP_DB_NOT_FOUND", " ".join(missing), 2)
    if mode == "fail":
        return failure("CALCULATION_FAILED", "集計できませんでした。", 1)
    databases = [Path(mapped[key]) for key in sorted(mapped, key=int)]
    if mode == "write":
        (databases[0].parent / "written.xlsx").write_bytes(b"x")
    pages = [f"FAKE AGGRESE Case{number} {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}"
             for number, path in enumerate(databases, 1)]
    pdf = report([*pages, f"FAKE AGGRESE SUMMARY {hashlib.sha256(data).hexdigest()[:16]}"])
    pdf = {"broken": b"not a pdf", "empty": blank()}.get(mode, pdf)
    cases = [{"caseNumber": number, "name": path.stem, "selected": True, "aggregated": not (mode == "unaggregated"
                                                                                            and number == 1)}
             for number, path in enumerate(databases, 1)]
    result = json.dumps({"command": "run", "cases": cases}, ensure_ascii=False).encode("utf-8")
    pik = f"Batch ver1.0.0\r\nFAKE PIK {hashlib.sha256(data).hexdigest()[:16]}\r\n".encode("cp932")
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    files = [("result-json", "application/json", "result.json", result),
             ("report-pdf", "application/pdf", "report.pdf", pdf),
             ("pickup-pik", "text/plain; charset=shift_jis", "pickup.pik", pik)]
    for kind, media, name, content in files[:2] if mode == "nopik" else files:
        if not (mode == "missing" and name == "report.pdf"):
            (output / name).write_bytes(content)
        artifacts.append({"kind": kind, "mediaType": media, "relativePath": name, "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and name == "report.pdf"
                                                   else content).hexdigest()})
    if mode == "extra":
        (output / "summary.xlsx").write_bytes(b"x")
    summary = {"command": "run", "inputVersion": "5.3.0.1", "productStyle": 1, "cases": cases,
               "spectralDuctility": [], "outputs": ["report.pdf", "pickup.pik"], "warnings": []}
    if mode == "cases":
        del summary["cases"]
    changes = {"protocol": {"protocolVersion": 2}, "engine": {"engine": "webdan2"}, "version": {"engineVersion": ""},
               "artifacts": {"artifacts": [*artifacts, artifacts[0]]}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts, summary=summary), **changes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
