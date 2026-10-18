"""A stand-in for ``JRSNAP.Headless.exe``: ``run``, the static nonlinear analysis (decision 47, ADR-0007), and
``data-check``, the データ確認図 (decision 50).

It follows the runner's protocol as WebPier uses it (structural-mcp JRSNAPHeadless/README.md): the arguments of
``webpier.pipeline.jrsnap.analyze_nonlinear``, an output directory that must be absent or empty, the files in it,
and one UTF-8 JSON envelope (protocolVersion 1, engine jrsnap) on stdout. Instead of JRSNAP it writes, for the input
``<stem>.ndu`` and each of its combinations n (the line ``SNAPConbNum=<count>``, else one), the analysis data
``<stem>(Case<n>_ρm10_αf1_正向).ndt`` with the line ``FAKE NDT <file name> <SHA256 of the input bytes>`` and the
results ``….DB1``, ``….LOG`` and ``….OUT`` with ``FAKE DB1 …``, ``FAKE LOG …`` and ``FAKE OUT …`` (UTF-8, LF), so a
test can tell which bytes were analyzed. Several combinations are analyzed in one run, as the real runner does.
When the real runner's protocol changes, change this too.

``data-check`` (decision 50) answers the arguments of ``webpier.pipeline.jrsnap.draw_data_check`` with one PDF of one
page for each figure, ``<figure>.pdf``, in the order asked, whose text is ``FAKE DATA CHECK <figure> <the first 16
digits of the SHA256 of the input bytes>`` (ASCII, which the standard font draws); reportlab writes it without a
date, so the same input gives the same bytes.

``FAKE_JRSNAP`` makes ``run`` misbehave, for the error tests: fail, text, list, protocol, version, summary (no summary),
artifacts (one artifact listed twice), kind (an unknown kind), nested (a path in a folder), nondt (no .ndt), missing
(the last file not written), extra (a file not listed), sha (the last file's SHA256 wrong), exit, slow (sleeps).
``FAKE_JRSNAP_DATA_CHECK`` makes ``data-check`` misbehave the same way (fail, exit, text, protocol, summary, order (the
figures in another order), kind, missing, sha, empty (a PDF without pages), broken (not a PDF), slow), so a test of
the analysis is not disturbed by the データ確認図 of the same generation.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time

ANALYSIS = ["--analyze", "true", "--timeout-seconds", "1800"]
DATA_CHECK = ["--figures", "nonlinear-numbers,section-numbers,element-table,section-detail,node-springs", "--case", "1",
              "--timeout-seconds", "300"]


def envelope(ok, artifacts=(), errors=(), **changes):
    value = {"protocolVersion": 1, "engine": "jrsnap", "engineVersion": "fake-1", "readiness": "experimental",
             "ok": ok, "executionStatus": "success" if ok else "failed",
             "engineeringStatus": "not_checked" if ok else "not_applicable",
             "summary": {"jrsnap": {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"}, "analyzed": True,
                         "analysis": {"dialogs": [{"title": "耐力と変形性能の自動算定", "answer": "実行(&R)"}]}}
             if ok else None,
             "messages": [{"level": "warning", "code": "LOG_WARNING", "text": "FAKE WARNING"}] if ok else [],
             "artifacts": list(artifacts), "errors": list(errors)}
    value.update(changes)
    return value


def failure(code, message, category):
    print(json.dumps(envelope(False, errors=[{"code": code, "message": message, "category": category}])))
    return 1


def pdf(text, pages=1):
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for _ in range(pages):
        page.drawString(60, 780, text)
        page.showPage()
    page.save()
    return stream.getvalue()


def data_check(argv, mode):
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "slow":
        time.sleep(2)
    if argv[1] != "--input" or argv[3] != "--output-dir" or argv[5:] != DATA_CHECK:
        return failure("INVALID_ARGUMENT", " ".join(argv), "input")
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), "output")
    if mode == "fail":
        return failure("UNKNOWN_DIALOG", "S_DataCheck showed: データ確認図エラー", "execution")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    figures = argv[6].split(",")
    if mode == "order":
        figures.reverse()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for number, figure in enumerate(figures, 1):
        last = number == len(figures)
        content = (b"not a pdf" if mode == "broken" and last
                   else pdf(f"FAKE DATA CHECK {figure} {digest[:16]}", 0 if mode == "empty" and last else 1))
        if not (mode == "missing" and last):
            (output / f"{figure}.pdf").write_bytes(content)
        artifacts.append({"kind": "pdf" if mode == "kind" and last else "data-check", "mediaType": "application/pdf",
                          "relativePath": f"{figure}.pdf", "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and last else content).hexdigest()})
    summary = {"jrsnap": {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"},
               "case": {"case": 1, "ndt": f"{source.stem}(Case1_ρm10_αf1_正向).ndt", "sha256": digest},
               "figures": [{"figure": figure, "file": f"{figure}.pdf", "pages": 1} for figure in figures]}
    changes = {"protocol": {"protocolVersion": 2}, "summary": {"summary": None}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts), "summary": summary, "messages": [], **changes}, ensure_ascii=False))
    return 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")  # the envelope names JRSNAP's files, as the real runner does
    if argv[:1] == ["data-check"]:
        return data_check(argv, os.environ.get("FAKE_JRSNAP_DATA_CHECK", ""))
    mode = os.environ.get("FAKE_JRSNAP", "")
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "list":
        sys.stdout.write("[]")
        return 0
    if mode == "slow":
        time.sleep(2)
    if argv[:1] != ["run"] or argv[1] != "--input" or argv[3] != "--output-dir" or argv[5:] != ANALYSIS:
        return failure("INVALID_ARGUMENT", " ".join(argv), "input")
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), "output")
    if mode == "fail":
        return failure("ANALYSIS_FAILED", "S_ANALYSIS.exe ended with exit code 1.", "calculation")
    document = source.read_bytes()
    digest = hashlib.sha256(document).hexdigest()
    count = re.search(rb"^SNAPConbNum=(\d+)\r?$", document, re.MULTILINE)
    outputs = [(f"{source.stem}(Case{case}_ρm10_αf1_正向).{suffix}", kind,
                f"FAKE {word} {source.name} {digest}\n".encode())
               for case in range(1, (int(count[1]) if count else 1) + 1)
               for suffix, kind, word in (("ndt", "ndt", "NDT"), ("DB1", "analysis-result", "DB1"),
                                          ("LOG", "analysis-result", "LOG"), ("OUT", "analysis-result", "OUT"))]
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for number, (name, kind, content) in enumerate(outputs, 1):
        last = number == len(outputs)
        if not (mode == "missing" and last):
            (output / name).write_bytes(content)
        artifacts.append({"kind": kind, "mediaType": "application/octet-stream", "relativePath": name,
                          "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and last else content).hexdigest()})
    if mode == "extra":
        (output / "extra.txt").write_bytes(b"x")
    changes = {"protocol": {"protocolVersion": 2}, "version": {"engineVersion": ""}, "summary": {"summary": None},
               "artifacts": {"artifacts": [*artifacts, artifacts[0]]},
               "kind": {"artifacts": [{**artifacts[0], "kind": "pdf"}, *artifacts[1:]]},
               "nested": {"artifacts": [{**artifacts[0], "relativePath": "sub/" + artifacts[0]["relativePath"]},
                                        *artifacts[1:]]},
               "nondt": {"artifacts": [{**item, "kind": "analysis-result"} for item in artifacts]}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts), **changes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
