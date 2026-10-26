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
- ``summary.xlsx``: a workbook (openpyxl) with the real one's sheets 応答値一覧表・設計総括表・安全率一覧表・直接基礎;
  the 応答値一覧表 has the real layout decision 59 reads (row No with the Case numbers from column D, row 名称, rows αf
  and ρm from the DB1 name, the blocks 復旧性 and 安全性 with a row 最大応答震度 of text values: Case n gives
  0.385 + 0.01(n − 1) and 0.386 + 0.01(n − 1); the rows 全体系折曲点震度 0.408, 等価固有周期 0.982 + 0.01(n − 1) and
  L1地震動 0.321 that decision 97 reads), and
  設計総括表 A1 says ``FAKE XLSX <SHA256 of the XML, 16 hex>``; its properties are dated 1980-01-01 so the bytes are the
  same each run (the real workbook's are not);
- ``foundation-steps.csv``: the step table of the direct foundation (decision 60), UTF-8 and CRLF, with the real
  runner's columns and, for each Case, node 7 at output steps 1〜4 with the values of WebPier's 線路方向 DB1
  (Rvd reached at step 3: V 16825.97 ≧ Rvd 16655.87; M at steps 3 and 4 grows by 100 per Case index, so each Case
  reaches at a different Md; H negative as the real spring sum is);
- ``result.json``: ``{"command": "run", "cases": [...]}``;
and ``summary.cases`` lists each Case (caseNumber from 1, the DB1 name without its suffix, selected and aggregated).

A pile foundation (the XML's ``FoundationType`` 0, decision 94) is given ``--sdr <.sdr> --sdr-direction axial|transverse``
after the switches, without ``--foundation-steps``: the .sdr must exist (it is the limit values of the stability, which a
pile foundation with none is refused: SDR_REQUIRED), the direction is checked, no ``foundation-steps.csv`` is returned, and the
report has one more page ``FAKE AGGRESE LIMITS <direction> <the first 16 digits of the SHA256 of the .sdr>``. ``--sdr`` for a
direct foundation is INVALID_ARGUMENT.

``--sdr-liquefied <.sdr>`` (decision 95) follows ``--sdr-direction``: the .sdr for the liquefaction, for a project that has a
Case for the liquefaction (``dgEkijoCase1``, ``dgEkijoCase21`` or ``dgEkijoCase2`` holding -1). Such a project without it is
SDR_REQUIRED; it without such a Case is INVALID_ARGUMENT; the report then has its own page ``FAKE AGGRESE LIMITS LIQUEFIED
<the first 16 digits of the SHA256 of that .sdr>``.

When the real runner's protocol changes, change this too. ``FAKE_AGGRESE`` makes it misbehave, for the error tests:
fail, exit, text, list, protocol, engine, version, artifacts (one artifact listed twice), missing (report.pdf not
written), nopik (no pickup.pik returned), noxlsx (no summary.xlsx returned), notzip (summary.xlsx is not a zip), nocsv (no
foundation-steps.csv returned), badcsv (its header is wrong), notutf8csv (it is not UTF-8), sha
(report.pdf's SHA256 wrong), extra (an unlisted file), cases (no summary.cases), unaggregated (the first Case not
aggregated), broken (report.pdf is not a PDF), empty (report.pdf has no page), write (a file written beside the
DB1).
"""

from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from openpyxl import Workbook
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

SWITCHES = ["--summary-xlsx", "true", "--report-pdf", "true", "--check-tables", "false", "--pik", "true",
            "--pile-anchor-bar-pdf", "false", "--foundation-steps", "true"]
PILE_SWITCHES = SWITCHES[:-2]
HEADER = "case_index,case_name,node,step,V,H,M,qvd,qd,Rvd,Mmd,plasticity"
# (step, H, M, qvd, qd, Rvd, Mmd, plasticity) of node 7; V is 16825.97 throughout.
STEPS = [(1, "0", "580.25", "8650.41", "8710.57", "543358.71", "57085.22", "0"),
         (2, "-5747.86", "52784.78", "3318.49", "3378.65", "22069.94", "54235.64", "0.0026"),
         (3, "-5901.07", "54168.43", "3236.74", "3296.9", "16655.87", "54120.2", "0.081"),
         (4, "-5949.26", "54514.06", "3236.74", "3296.9", "16655.87", "54120.2", "0.081")]


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


def workbook(text, names):
    """The summary workbook with the 応答値一覧表 of one Case per DB1 name (decision 59 reads its 最大応答震度)."""
    book = Workbook()
    sheet = book.active
    sheet.title = "応答値一覧表"
    sheet["A1"], sheet["A3"], sheet["A4"], sheet["B4"], sheet["B5"] = "地盤区分", "応答値一覧表", "解析ケース", "No", "名称"
    sheet["B6"], sheet["B7"], sheet["A8"], sheet["B8"], sheet["C8"] = "αf", "ρm", "降伏点", "初期降伏震度", "Khy"
    sheet["B9"], sheet["C9"], sheet["B12"], sheet["C12"] = "全体系折曲点震度", "Kheq", "等価固有周期", "Teq(sec)"
    sheet["B16"], sheet["C16"] = "L1地震動", "KhL1"
    sheet["A13"], sheet["B13"], sheet["C13"] = "復旧性", "応答塑性率", "μ"
    sheet["B15"], sheet["C15"] = "最大応答震度", "Khmax"
    sheet["A17"], sheet["B17"], sheet["C17"] = "安全性", "応答塑性率", "μ"
    sheet["B19"], sheet["C19"] = "最大応答震度", "Khmax"
    for index, name in enumerate(names):
        column = 4 + index
        sheet.cell(row=4, column=column, value=index + 1)
        sheet.cell(row=5, column=column, value=name)
        found = re.search(r"_ρm(\d)(\d)_αf(\d)_", name)  # JRSNAP's name of the Case (decision 76)
        rho, alpha = (f"{found[1]}.{found[2]}", f"{found[3]}.0") if found else ("1.0", "1.0")
        sheet.cell(row=6, column=column, value=alpha)
        sheet.cell(row=7, column=column, value=rho)
        sheet.cell(row=9, column=column, value="0.408")
        sheet.cell(row=12, column=column, value=f"{0.982 + 0.01 * index:.3f}")
        sheet.cell(row=16, column=column, value="0.321")
        sheet.cell(row=15, column=column, value=f"{0.385 + 0.01 * index:.3f}")
        sheet.cell(row=19, column=column, value=f"{0.386 + 0.01 * index:.3f}")
    for title in ("設計総括表", "安全率一覧表", "直接基礎"):
        book.create_sheet(title)
    book["設計総括表"]["A1"] = text
    book.properties.created = book.properties.modified = datetime(1980, 1, 1)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def foundation_steps(databases):
    rows = [HEADER]
    for index, path in enumerate(databases):
        for step, h, m, qvd, qd, rvd, mmd, plasticity in STEPS:
            moment = f"{float(m) + 100 * index:.2f}"
            rows.append(f"{index},{path.stem},7,{step},16825.97,{h},{moment},{qvd},{qd},{rvd},{mmd},{plasticity}")
    return ("\r\n".join(rows) + "\r\n").encode("utf-8")


def seismic_forces(member):
    """(Md, Vd, Nd of the largest case, Md, Vd, Nd of the smallest) at an end of the member *member* in the pickup of 復旧性L2."""
    return (2000.0 + member, -(500.0 + member), 0.0, -(80.0 + member), 400.0 + member, 0.0)


def pickup_lines():
    """The lines of pickup 2 (復旧性L2) of the members 1 to 99 (the stand-in does not read the NDU: the member numbers the
    footing reads are the elements of its model): the focus M and S at both ends, in the pickup's fixed columns."""
    return "".join(f"{2:>5}{focus:>5}{member:>5}{1:>5}{1:>5}{point:>5}{position:>10.3f}"
                   + "".join(f"{value:>10.2f}" for value in seismic_forces(member)) + "\r\n"
                   for member in range(1, 100) for focus in ("M", "S") for point, position in (("ITAN", 0.0), ("JTAN", 1.0)))


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
    piled = "--sdr" in argv
    wet = "--sdr-liquefied" in argv
    switches = PILE_SWITCHES if piled else SWITCHES
    if (len(argv) != 7 + len(switches) + (4 if piled else 0) + (2 if wet else 0) or argv[0] != "run"
            or argv[1] != "--input" or argv[3] != "--output-dir" or argv[5] != "--snap-map"
            or argv[7:7 + len(switches)] != switches
            or (piled and (argv[7 + len(switches)] != "--sdr" or argv[9 + len(switches)] != "--sdr-direction"
                           or argv[10 + len(switches)] not in ("axial", "transverse")))
            or (wet and (not piled or argv[11 + len(switches)] != "--sdr-liquefied"))):
        return failure("INVALID_ARGUMENTS", " ".join(argv), 2)
    project, output, snaps = Path(argv[2]), Path(argv[4]), Path(argv[6])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), 2)
    data = project.read_bytes()
    root = ET.fromstring(data.decode("cp932").replace('encoding="utf-16"', "", 1))
    kind = root.find("Foundation/基礎照査/clsFoundation/FoundationType")  # (a minimal project of a test has none: direct)
    foundation = 1 if kind is None else int(kind.text)
    if piled and foundation != 0:
        return failure("INVALID_ARGUMENT", "--sdr requires a project with a pile foundation.", 2)
    if foundation == 0 and not piled:
        return failure("SDR_REQUIRED", "A pile foundation project with blank limit values requires --sdr.", 2)
    sdr = Path(argv[8 + len(switches)]) if piled else None
    if sdr is not None and not sdr.is_file():
        return failure("INVALID_SDR", f"Could not read --sdr: {sdr}", 2)
    liquefaction = any(re.search(rf"<{tag}>([\s\S]*?)</{tag}>", data.decode("cp932")) and "<int>-1</int>" in
                       re.search(rf"<{tag}>([\s\S]*?)</{tag}>", data.decode("cp932"))[1]
                       for tag in ("dgEkijoCase1", "dgEkijoCase21", "dgEkijoCase2"))
    if wet and not liquefaction:
        return failure("INVALID_ARGUMENT", "--sdr-liquefied requires a project with a liquefaction Case.", 2)
    if liquefaction and piled and not wet:
        return failure("SDR_REQUIRED", "A pile foundation project with liquefaction Cases requires --sdr-liquefied.", 2)
    wet_sdr = Path(argv[12 + len(switches)]) if wet else None
    if wet_sdr is not None and not wet_sdr.is_file():
        return failure("INVALID_SDR", f"Could not read --sdr-liquefied: {wet_sdr}", 2)
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
    limits = [] if sdr is None else [f"FAKE AGGRESE LIMITS {argv[10 + len(switches)]} "
                                     f"{hashlib.sha256(sdr.read_bytes()).hexdigest()[:16]}"]
    if wet_sdr is not None:
        limits.append(f"FAKE AGGRESE LIMITS LIQUEFIED {hashlib.sha256(wet_sdr.read_bytes()).hexdigest()[:16]}")
    pdf = report([*pages, f"FAKE AGGRESE SUMMARY {hashlib.sha256(data).hexdigest()[:16]}", *limits])
    pdf = {"broken": b"not a pdf", "empty": blank()}.get(mode, pdf)
    cases = [{"caseNumber": number, "name": path.stem, "selected": True, "aggregated": not (mode == "unaggregated"
                                                                                            and number == 1)}
             for number, path in enumerate(databases, 1)]
    result = json.dumps({"command": "run", "cases": cases}, ensure_ascii=False).encode("utf-8")
    pik = f"Batch ver1.0.0\r\nFAKE PIK {hashlib.sha256(data).hexdigest()[:16]}\r\n{pickup_lines() if piled else ''}".encode("cp932")
    xlsx = (b"not a zip" if mode == "notzip"
            else workbook(f"FAKE XLSX {hashlib.sha256(data).hexdigest()[:16]}", [path.stem for path in databases]))
    csv = {"badcsv": b"case,step\r\n0,1\r\n", "notutf8csv": "直接基礎\r\n".encode("cp932")}.get(
        mode, foundation_steps(databases))
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    files = [("result-json", "application/json", "result.json", result),
             ("report-pdf", "application/pdf", "report.pdf", pdf),
             ("pickup-pik", "text/plain; charset=shift_jis", "pickup.pik", pik),
             ("summary-xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "summary.xlsx",
              xlsx)]
    if not piled:
        files.append(("foundation-steps-csv", "text/csv; charset=utf-8", "foundation-steps.csv", csv))
    dropped = {"nopik": "pickup.pik", "noxlsx": "summary.xlsx", "nocsv": "foundation-steps.csv"}.get(mode)
    for kind, media, name, content in (file for file in files if file[2] != dropped):
        if not (mode == "missing" and name == "report.pdf"):
            (output / name).write_bytes(content)
        artifacts.append({"kind": kind, "mediaType": media, "relativePath": name, "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and name == "report.pdf"
                                                   else content).hexdigest()})
    if mode == "extra":
        (output / "unlisted.txt").write_bytes(b"x")
    summary = {"command": "run", "inputVersion": "5.3.0.1", "productStyle": 1, "cases": cases,
               "spectralDuctility": [], "outputs": ["summary.xlsx", "report.pdf", "pickup.pik"]
               + ([] if piled else ["foundation-steps.csv"]),
               "warnings": []}
    if mode == "cases":
        del summary["cases"]
    changes = {"protocol": {"protocolVersion": 2}, "engine": {"engine": "webdan2"}, "version": {"engineVersion": ""},
               "artifacts": {"artifacts": [*artifacts, artifacts[0]]}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts, summary=summary), **changes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
