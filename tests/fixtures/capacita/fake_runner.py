"""A stand-in for ``WebDanforCS.Headless.exe run-rc --pickup``: the 柱の断面照査 of 0611 (decision 48, ADR-0008).

It follows the runner's protocol as WebPier uses it (Capacita README「Headless runner の run-rc」): the arguments of
``webpier.pipeline.capacita`` (``run-rc --input <wdj> --output-dir <dir> --output-format pdf --pickup <pik>``), an
output directory that must be absent or empty, the files in it, and one UTF-8 JSON envelope (protocolVersion 1,
engine webdan2, engineeringStatus not_evaluated) on stdout. Instead of calculating it writes:

- ``report.pdf``: the sections section_forces (2 pages), bending_safety_destruction, shear_safety_destruction,
  bending_durability, shear_durability, bending_serviceability (only when the WDJ's crack row has ``vis_u`` true),
  bending_restorability and shear_restorability (1 page each), in that order, each page saying
  ``FAKE CAPACITA <id> <page>/<pages> <SHA256 of the WDJ, 16 hex>`` so a test can find the pages in a report;
  ``summary.reportSections`` gives their page ranges;
- ``model.wdj``: the given WDJ with ``pickup_filename`` the PIK's file name and ``pickup_data``
  ``{"fake": "<SHA256 of the PIK bytes>"}``, as ``json.dumps(document, ensure_ascii=False, indent=2)`` in UTF-8;
- ``result.json``: ``{"returnCode": "OK", "outputFormat": "pdf", "messages": []}``.

When the real runner's protocol changes, change this too (the real-runner test is the signal). ``FAKE_CAPACITA`` makes
it misbehave, for the error tests: fail, pickup, exit, text, list, protocol, engine, version, artifacts (one artifact
listed twice), missing (model.wdj not written), sha (model.wdj's SHA256 wrong), extra (an unlisted file), sections
(no reportSections), order (the sections reversed), gap (the last section ends past the PDF).
"""

import hashlib
import io
import json
import os
from pathlib import Path
import sys

from reportlab.pdfgen import canvas

SECTIONS = (("section_forces", 2), ("bending_safety_destruction", 1), ("shear_safety_destruction", 1),
            ("bending_durability", 1), ("shear_durability", 1), ("bending_serviceability", 1),
            ("bending_restorability", 1), ("shear_restorability", 1))


def envelope(ok, artifacts=(), errors=(), summary=None, **changes):
    value = {"protocolVersion": 1, "engine": "webdan2", "engineVersion": "fake-1", "readiness": "production",
             "ok": ok, "executionStatus": "success" if ok else "failed", "engineeringStatus": "not_evaluated",
             "summary": summary, "messages": [], "artifacts": list(artifacts), "errors": list(errors)}
    value.update(changes)
    return value


def failure(code, message, exit_code):
    print(json.dumps(envelope(False, errors=[{"code": code, "message": message}]), ensure_ascii=False))
    return exit_code


def report(sections, digest):
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    ranges, number = [], 0
    for section, pages in sections:
        ranges.append({"id": section, "firstPage": number + 1, "lastPage": number + pages})
        for index in range(1, pages + 1):
            number += 1
            page.drawString(60, 780, f"FAKE CAPACITA {section} {index}/{pages} {digest[:16]}")
            page.showPage()
    page.save()
    return stream.getvalue(), ranges


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    mode = os.environ.get("FAKE_CAPACITA", "")
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "list":
        sys.stdout.write("[]")
        return 0
    if (len(argv) != 9 or argv[0] != "run-rc" or argv[1] != "--input" or argv[3] != "--output-dir"
            or argv[5:7] != ["--output-format", "pdf"] or argv[7] != "--pickup"):
        return failure("invalid_arguments", " ".join(argv), 2)
    source, output, pickup = Path(argv[2]), Path(argv[4]), Path(argv[8])
    if output.exists() and any(output.iterdir()):
        return failure("output_not_empty", str(output), 5)
    if mode == "fail":
        return failure("calculation_failed", "RcDanが計算を完了できませんでした。", 4)
    if mode == "pickup":
        return failure("pickup_import_failed", "IMPORT-EXISTING-POINT-IDENTITY /points/0/position: 一致しません", 2)
    wdj = source.read_bytes()
    document = json.loads(wdj.decode("utf-8"))
    digest = hashlib.sha256(wdj).hexdigest()
    shown = [(name, pages) for name, pages in SECTIONS
             if name != "bending_serviceability" or document["crack"][0]["vis_u"]]
    pdf, ranges = report(shown, digest)
    document["pickup_filename"] = pickup.name
    document["pickup_data"] = {"fake": hashlib.sha256(pickup.read_bytes()).hexdigest()}
    completed = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    result = json.dumps({"returnCode": "OK", "outputFormat": "pdf", "messages": []}).encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    files = (("result", "application/json; charset=utf-8", "result.json", result),
             ("report", "application/pdf", "report.pdf", pdf),
             ("wdj", "application/json; charset=utf-8", "model.wdj", completed))
    artifacts = []
    for kind, media, name, content in files:
        if not (mode == "missing" and name == "model.wdj"):
            (output / name).write_bytes(content)
        artifacts.append({"kind": kind, "mediaType": media, "relativePath": name, "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and name == "model.wdj"
                                                   else content).hexdigest()})
    if mode == "extra":
        (output / "summary.xlsx").write_bytes(b"x")
    if mode == "order":
        ranges.reverse()
    if mode == "gap":
        ranges[-1]["lastPage"] += 1
    summary = {"returnCode": "OK", "outputFormat": "pdf", "messageCounts": {}, "reportSections": ranges}
    if mode == "sections":
        del summary["reportSections"]
    changes = {"protocol": {"protocolVersion": 2}, "engine": {"engine": "steeldan"}, "version": {"engineVersion": ""},
               "artifacts": {"artifacts": [*artifacts, artifacts[0]]}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts, summary=summary), **changes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
