"""A stand-in for ``JRSNAP.Headless.exe``: ``run``, the static nonlinear analysis (decision 47, ADR-0007), and
``figures``, the データ確認図 and the 荷重図 (decisions 50, 51).

It follows the runner's protocol as WebPier uses it (structural-mcp JRSNAPHeadless/README.md): the arguments of
``webpier.pipeline.jrsnap.analyze_nonlinear``, an output directory that must be absent or empty, the files in it,
and one UTF-8 JSON envelope (protocolVersion 1, engine jrsnap) on stdout. Instead of JRSNAP it writes, for the input
``<stem>.ndu`` and each of its combinations n (the line ``SNAPConbNum=<count>``, else one), the analysis data
``<stem>(Case<n>_ρm<ρm×10>_αf<αf>_正向|逆向).ndt`` (from its line ``SNAPConb<n>``, decision 76) with the line ``FAKE NDT <file name> <SHA256 of the input bytes>`` and the
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

``soil`` (decision 85, ADR-0013) answers only the arguments of ``webpier.pipeline.jrsnap.calculate_ground`` (``--input
<.sdt> --output-dir <folder> --timeout-seconds 600``). It returns ``<stem>.sdr`` (the SOIL-JR 5.2 sample's .sdr, tests/
fixtures/soiljr/pile_cast.sdr, with its title line replaced by ``FAKE SOIL-JR <the first 16 digits of the SHA256 of the
input bytes>``), ``<stem>.sdc`` (the sample's .sdc, tests/fixtures/soiljr/pile_cast.sdc, with its title line replaced by ``FAKE SDC <SHA256>``), with ``<stem>(液状化時用).sdr`` (pile_cast_liquefaction.sdr, the sample E's for it) and
``.sdc`` when the input's 液状化の低減係数 section starts with 1, and ``<stem>.pdf`` of two pages (``FAKE SOIL-JR REPORT
<16 digits>``), and the runner's ``summary.input`` (name and SHA256), ``summary.liquefaction`` and one warning.
``FAKE_JRSNAP_SOIL`` makes it misbehave: fail, input (a SOIL-JR rejection of the input), exit, text, protocol, summary,
sha, kind, missing, extra, header (a .sdr of another pile), pdf (a PDF without pages), broken, name (another input name in the summary), digest (another
SHA256), liquefaction (the opposite flag), slow.

``FAKE_JRSNAP`` makes ``run`` misbehave, for the error tests: fail, text, list, protocol, version, summary (no summary),
artifacts (one artifact listed twice), kind (an unknown kind), nested (a path in a folder), nondt (no .ndt), missing
(the last file not written), extra (a file not listed), sha (the last file's SHA256 wrong), exit, slow (sleeps).
``FAKE_JRSNAP_ERRLOG`` adds the file the real S_ANALYSIS.exe writes beside every analysis and that carries no NDU's name,
``解析実行Err.log``: ``same`` (empty, as it is when all is well) or ``differ`` (it names the input).
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


def case_name(document, stem, number):
    """JRSNAP's name of combination *number*: ``<stem>(Case<n>_ρm<ρm×10, 2 digits>_αf<αf>_正向|逆向)`` from its line
    ``SNAPConb<n>=ρm,αf,direction,…`` (else ρm 1.0, αf 1.0, 正向)."""
    found = re.search(rb"^SNAPConb" + str(number).encode() + rb"=([^,]*),([^,]*),([^,]*),", document, re.MULTILINE)
    rho, alpha, reverse = (float(found[1]), float(found[2]), found[3] == b"1") if found else (1.0, 1.0, False)
    return f"{stem}(Case{number}_ρm{round(rho * 10):02d}_αf{round(alpha)}_{'逆向' if reverse else '正向'})"


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
        diagrams.append({"combination": combination, "ndt": f"{case_name(document, source.stem, combination)}.ndt",
                         "sha256": digest,
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
               "dataCheck": {"combination": 1, "ndt": f"{case_name(document, source.stem, 1)}.ndt", "sha256": digest,
                             "figures": [{"figure": figure, "file": f"{figure}.pdf", "pages": 1} for figure in names]},
               "loadDiagram": None if mode == "nodiagram" else diagrams}
    changes = {"protocol": {"protocolVersion": 2}, "summary": {"summary": None}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts), "summary": summary, "messages": [], **changes}, ensure_ascii=False))
    return 0


SOIL = ["--timeout-seconds", "600"]


def soil(argv, mode):
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "slow":
        time.sleep(2)
    if len(argv) != 7 or argv[1] != "--input" or argv[3] != "--output-dir" or argv[5:] != SOIL:
        return failure("INVALID_ARGUMENT", " ".join(argv), "input")
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), "output")
    if mode == "fail":
        return failure("UNKNOWN_DIALOG", "SOIL_JR showed: 計算中にエラーが発生しました。", "execution")
    if mode == "input":
        return failure("SDT_REJECTED", "SOIL-JR rejected the .sdt (入力の検査): 杭長Lを入力してください", "input")
    document = source.read_bytes()
    digest = hashlib.sha256(document).hexdigest()
    lines = document.decode("cp932").split("\r\n")
    liquefied = lines[lines.index("●液状化の低減係数") + 1].strip() == "1"
    stem, folder = source.stem, Path(__file__).parents[1] / "soiljr"

    # the pile of the input: the header of a .sdr names it (type, length, diameter, columns, piles)
    base, pile = lines.index("●基本条件●"), lines[lines.index("●杭条件●") + 1].split(",")
    second = lines[lines.index("●杭条件●") + 2].split(",")
    piles = float(lines[base + 3 + int(lines[base + 2]) + 2])
    header = (f"1, {pile[9]}, {float(second[0]):g}, {float(second[6]):.3f}, {pile[1]}, {pile[2]}, {pile[3]}, {pile[4]}, "
              f"{piles:g}")

    def sdr(name):
        text = (folder / name).read_bytes().decode("cp932").split("\r\n")
        text[1] = f"FAKE SOIL-JR {digest[:16]}"
        text[3] = "1, 9, 99, 9.999, 9, 9, 9, 9, 99" if mode == "header" else header
        return "\r\n".join(text).encode("cp932")

    def sdc(name="pile_cast.sdc", word="FAKE SDC"):
        """The SOIL-JR 5.2 sample's .sdc (pile_cast.sdc; for the liquefaction pile_cast_liquefaction.sdc), its title line
        replaced by ``FAKE SDC <SHA256>`` (``FAKE SDC LIQUEFACTION <SHA256>``)."""
        text = (folder / name).read_bytes().decode("cp932").split("\r\n")
        text[4] = f"{word} {digest}"
        return "\r\n".join(text).encode("cp932")

    pdf_content = (b"not a pdf" if mode == "broken" else pdf() if mode == "pdf"
                   else pdf(f"FAKE SOIL-JR REPORT {digest[:16]}", f"FAKE SOIL-JR REPORT 2 {digest[:16]}"))
    files = [(f"{stem}.sdr", "soil-sdr", sdr("pile_cast.sdr")),
             (f"{stem}.sdc", "soil-sdc", sdc())]
    if liquefied:
        files += [(f"{stem}(液状化時用).sdr", "soil-sdr-liquefaction", sdr("pile_cast_liquefaction.sdr")),
                  (f"{stem}(液状化時用).sdc", "soil-sdc-liquefaction",
                   sdc("pile_cast_liquefaction.sdc", "FAKE SDC LIQUEFACTION"))]
    files.append((f"{stem}.pdf", "soil-report", pdf_content))
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for number, (name, kind, content) in enumerate(files, 1):
        last = number == len(files)
        if not (mode == "missing" and last):
            (output / name).write_bytes(content)
        artifacts.append({"kind": "soil-sdc" if mode == "kind" and last else kind,
                          "mediaType": "application/pdf" if name.endswith(".pdf") else "application/octet-stream",
                          "relativePath": name, "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and last else content).hexdigest()})
    if mode == "extra":
        (output / "extra.txt").write_bytes(b"x")
    summary = {"jrsnap": {"product": "5.2-L03", "assemblyVersion": "5.2.3.1", "soilVersion": "5.2.3.0"},
               "input": {"name": "other.sdt" if mode == "name" else source.name,
                         "sha256": "0" * 64 if mode == "digest" else digest},
               "liquefaction": (not liquefied) if mode == "liquefaction" else liquefied, "reportPages": 2}
    messages = [{"level": "warning", "code": "SOIL_WARNING", "text": "FAKE SOIL WARNING"}]
    changes = {"protocol": {"protocolVersion": 2}, "summary": {"summary": None}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts), "summary": summary, "messages": messages, **changes},
                     ensure_ascii=False))
    return 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")  # the envelope names JRSNAP's files, as the real runner does
    if argv[:1] == ["figures"]:
        return figures(argv, os.environ.get("FAKE_JRSNAP_FIGURES", ""))
    if argv[:1] == ["soil"]:
        return soil(argv, os.environ.get("FAKE_JRSNAP_SOIL", ""))
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
    outputs = [(f"{case_name(document, source.stem, case)}.{suffix}", kind,
                f"FAKE {word} {source.name} {digest}\n".encode())
               for case in range(1, (int(count[1]) if count else 1) + 1)
               for suffix, kind, word in (("ndt", "ndt", "NDT"), ("DB1", "analysis-result", "DB1"),
                                          ("LOG", "analysis-result", "LOG"), ("OUT", "analysis-result", "OUT"))]
    if errlog := os.environ.get("FAKE_JRSNAP_ERRLOG", ""):  # the real S_ANALYSIS.exe's file that carries no NDU's name
        outputs.append(("解析実行Err.log", "analysis-result", b"" if errlog == "same" else f"ERR {source.name}".encode()))
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
