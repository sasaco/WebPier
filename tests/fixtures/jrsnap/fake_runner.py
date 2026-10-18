"""A stand-in for ``JRSNAP.Headless.exe``: ``run``, the static nonlinear analysis (decision 47, ADR-0007), and
``figures``, the データ確認図 and the 荷重図 (decisions 50, 51).

It follows the runner's protocol as WebPier uses it (structural-mcp JRSNAPHeadless/README.md): the arguments of
``webpier.pipeline.jrsnap.analyze_nonlinear``, an output directory that must be absent or empty, the files in it,
and one UTF-8 JSON envelope (protocolVersion 1, engine jrsnap) on stdout. Instead of JRSNAP it writes, for the input
``<stem>.ndu`` and each of its combinations n (the line ``SNAPConbNum=<count>``, else one), the analysis data
``<stem>(Case<n>_ρm10_αf1_正向).ndt`` with the line ``FAKE NDT <file name> <SHA256 of the input bytes>`` and the
results ``….DB1``, ``….LOG`` and ``….OUT`` with ``FAKE DB1 …``, ``FAKE LOG …`` and ``FAKE OUT …`` (UTF-8, LF), so a
test can tell which bytes were analyzed. Several combinations are analyzed in one run, as the real runner does.
When the real runner's protocol changes, change this too.

``figures`` (decisions 50, 51) answers only the arguments of ``webpier.pipeline.jrsnap.draw_figures``: the five
figures of the データ確認図 for combination 1, the 荷重図 of combinations in ascending order, and the runner's time
300 + 120 × the number of combinations (anything else is INVALID_ARGUMENT). The combinations of the input are its
line ``SNAPConbNum=<count>`` (else one) and its basic cases the line ``LoadNum=<count>`` (else one); a combination it
does not have is COMBINATION_NOT_FOUND. It returns one PDF of one page for each figure, ``<figure>.pdf``, in the order
asked, whose text is ``FAKE DATA CHECK <figure> <the first 16 digits of the SHA256 of the input bytes>``, then for
each combination k ``load-diagram-<k>.pdf`` with one page per basic case n, in case order, whose text is ``FAKE LOAD
DIAGRAM COMB <k> CASE <n> <the same 16 digits>`` (ASCII, which the standard font draws), and the runner's
``summary.dataCheck`` and ``summary.loadDiagram`` (titles ``CASE-<n> FAKE``). reportlab writes the PDFs without a date,
so the same input gives the same bytes.

``FAKE_JRSNAP`` makes ``run`` misbehave, for the error tests: fail, text, list, protocol, version, summary (no summary),
artifacts (one artifact listed twice), kind (an unknown kind), nested (a path in a folder), nondt (no .ndt), missing
(the last file not written), extra (a file not listed), sha (the last file's SHA256 wrong), exit, slow (sleeps).
``FAKE_JRSNAP_FIGURES`` makes ``figures`` misbehave the same way, so a test of the analysis is not disturbed by the
figures of the same generation: fail, exit, text, protocol, summary, slow; order (the figures of the データ確認図 in
another order), empty (the last figure a PDF without pages), broken (the last figure not a PDF); kind, missing and sha
(of the last load diagram); nocase (the last case's page and entry left out of the last combination's load diagram),
pages (one entry fewer in the last combination's ``pages`` than its PDF has pages), nocomb (the last combination's
load diagram left out of the artifacts and the summary) and nodiagram (no ``summary.loadDiagram``).
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
DATA_CHECK = ["--data-check", "nonlinear-numbers,section-numbers,element-table,section-detail,node-springs",
              "--data-check-combination", "1", "--load-diagram"]


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


def pdf(*texts):
    """One page for each of *texts*."""
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for text in texts:
        page.drawString(60, 780, text)
        page.showPage()
    page.save()
    return stream.getvalue()


def count(document, key):
    found = re.search(rb"^" + key.encode() + rb"=(\d+)\r?$", document, re.MULTILINE)
    return int(found[1]) if found else 1


def figures(argv, mode):
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "slow":
        time.sleep(2)
    asked = argv[10].split(",") if len(argv) == 13 else []
    numbers = [int(number) for number in asked if re.fullmatch(r"[1-9][0-9]*", number)]
    if (len(argv) != 13 or argv[1] != "--input" or argv[3] != "--output-dir" or argv[5:10] != DATA_CHECK
            or not numbers or len(numbers) != len(asked) or numbers != sorted(set(numbers))
            or argv[11:] != ["--timeout-seconds", str(300 + 120 * len(numbers))]):
        return failure("INVALID_ARGUMENT", " ".join(argv), "input")
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), "output")
    if mode == "fail":
        return failure("UNKNOWN_DIALOG", "S_DataCheck showed: データ確認図エラー", "execution")
    document = source.read_bytes()
    combinations, cases = count(document, "SNAPConbNum"), count(document, "LoadNum")
    if missing := [number for number in numbers if number > combinations]:
        return failure("COMBINATION_NOT_FOUND", f"The .ndu has no combination {missing[0]}.", "input")
    digest = hashlib.sha256(document).hexdigest()
    ndt = f"{source.stem}(Case{{}}_ρm10_αf1_正向).ndt"
    names = argv[6].split(",")
    if mode == "order":
        names.reverse()
    files = []  # (kind, file, content)
    for number, figure in enumerate(names, 1):
        last = number == len(names)
        content = (b"not a pdf" if mode == "broken" and last
                   else pdf() if mode == "empty" and last else pdf(f"FAKE DATA CHECK {figure} {digest[:16]}"))
        files.append(("data-check", f"{figure}.pdf", content))
    diagrams = []
    if mode == "nocomb":
        numbers = numbers[:-1]
    for combination in numbers:
        last = combination == numbers[-1]
        drawn = list(range(1, cases + (0 if mode == "nocase" and last else 1)))
        content = pdf(*(f"FAKE LOAD DIAGRAM COMB {combination} CASE {case} {digest[:16]}" for case in drawn))
        listed = [{"page": page, "case": case, "title": f"CASE-{case} FAKE"} for page, case in enumerate(drawn, 1)]
        diagrams.append({"combination": combination, "ndt": ndt.format(combination), "sha256": digest,
                         "file": f"load-diagram-{combination}.pdf",
                         "pages": listed[:-1] if mode == "pages" and last else listed})
        files.append(("load-diagram", f"load-diagram-{combination}.pdf", content))
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for number, (kind, name, content) in enumerate(files, 1):
        last = number == len(files)
        if not (mode == "missing" and last):
            (output / name).write_bytes(content)
        artifacts.append({"kind": "pdf" if mode == "kind" and last else kind, "mediaType": "application/pdf",
                          "relativePath": name, "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and last else content).hexdigest()})
    summary = {"jrsnap": {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"},
               "dataCheck": {"combination": 1, "ndt": ndt.format(1), "sha256": digest,
                             "figures": [{"figure": figure, "file": f"{figure}.pdf", "pages": 1} for figure in names]},
               "loadDiagram": None if mode == "nodiagram" else diagrams}
    changes = {"protocol": {"protocolVersion": 2}, "summary": {"summary": None}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts), "summary": summary, "messages": [], **changes}, ensure_ascii=False))
    return 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")  # the envelope names JRSNAP's files, as the real runner does
    if argv[:1] == ["figures"]:
        return figures(argv, os.environ.get("FAKE_JRSNAP_FIGURES", ""))
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
