"""A stand-in for ``FrameWebforCS.Headless.exe run`` drawing the load diagram (decision 44, ADR-0005).

It follows the runner's protocol as WebPier uses it (FEMPython FrameWebforCS/Headless/README.md): the arguments of
``webpier.pipeline.fempython``, an output directory that must be absent or empty, ``report.pdf`` in it, and one
UTF-8 JSON envelope (protocolVersion 1) on stdout. Instead of the drawing it writes one page per two load cases of
the FrameWeb file, each page saying which file and cases it stands for, so a test can find the pages in a report.
When the real runner's protocol changes, change this too (the real-runner test is the signal).

``FAKE_FEMPYTHON`` makes it misbehave, for the error tests: fail, text, list, protocol, version, artifacts,
missing, sha, badpdf, empty, exit.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import sys

from reportlab.pdfgen import canvas

EXPECTED = ["--generate-pik", "false", "--pdf-sections", "load_diagram", "--pdf-paper", "A4",
            "--pdf-orientation", "vertical", "--load-diagram-layout", "split_horizontal", "--load-diagram-axis",
            "false"]


def envelope(ok, artifacts=(), errors=(), **changes):
    value = {"protocolVersion": 1, "engine": "fempython", "engineVersion": "fake-1", "readiness": "experimental",
             "ok": ok, "executionStatus": "success" if ok else "failed",
             "engineeringStatus": "not_checked" if ok else "not_applicable",
             "summary": {"calculated": False}, "messages": [], "artifacts": list(artifacts), "errors": list(errors)}
    value.update(changes)
    return value


def drawing(name, cases):
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for first in range(0, len(cases), 2):
        page.drawString(60, 780, f"FAKE LOAD DIAGRAM {name} CASES {' '.join(cases[first:first + 2])}")
        page.showPage()
    page.save()
    return stream.getvalue()


def main(argv):
    mode = os.environ.get("FAKE_FEMPYTHON", "")
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "list":
        sys.stdout.write("[]")
        return 0
    if argv[:1] != ["run"] or argv[1] != "--input" or argv[3] != "--output-dir" or argv[5:] != EXPECTED:
        print(json.dumps(envelope(False, errors=[{"code": "INVALID_ARGUMENT", "message": " ".join(argv),
                                                    "category": "input"}])))
        return 1
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        print(json.dumps(envelope(False, errors=[{"code": "OUTPUT_NOT_EMPTY", "message": str(output),
                                                    "category": "output"}])))
        return 1
    if mode == "fail":
        print(json.dumps(envelope(False, errors=[{"code": "LOAD_DIAGRAM_REQUIRES_2D", "message": "2D only",
                                                    "category": "input"}])))
        return 1
    document = json.loads(source.read_text(encoding="utf-8"))
    pdf = {"badpdf": b"%PDF-1.4 broken", "empty": drawing(source.name, [])}.get(
        mode, drawing(source.name, list(document["load"])))
    output.mkdir(parents=True, exist_ok=True)
    if mode != "missing":
        (output / "report.pdf").write_bytes(pdf)
    artifact = {"kind": "pdf", "mediaType": "application/pdf", "relativePath": "report.pdf", "bytes": len(pdf),
                "sha256": hashlib.sha256(b"other" if mode == "sha" else pdf).hexdigest()}
    changes = {"protocol": {"protocolVersion": 2}, "version": {"engineVersion": ""},
               "artifacts": {"artifacts": [artifact, artifact]}}.get(mode, {})
    print(json.dumps({**envelope(True, [artifact]), **changes}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
