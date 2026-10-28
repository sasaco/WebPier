"""A stand-in for ``WebDanforCS.Headless.exe run-rc``: the 柱の断面照査 of 0611 and 0621 with ``--pickup`` (decision 48,
ADR-0008) and the フーチングの断面照査 of 0810 and 0820 without it (decision 60).

It follows the runner's protocol as WebPier uses it (Capacita README「Headless runner の run-rc」): the arguments of
``webpier.pipeline.capacita`` (``run-rc --input <wdj> --output-dir <dir> --output-format pdf --pickup <pik>``), an
output directory that must be absent or empty, the files in it, and one UTF-8 JSON envelope (protocolVersion 1,
engine webdan2, engineeringStatus not_evaluated) on stdout. Instead of calculating it writes:

- ``report.pdf``: the sections section_forces (2 pages), bending_safety_destruction, shear_safety_destruction,
  bending_durability, shear_durability, bending_serviceability (only when the WDJ's crack row has ``vis_u`` true),
  bending_restorability, shear_restorability and bending_rebar_amount (1 page each), in that order, each page saying
  ``FAKE CAPACITA <id> <page>/<pages> <SHA256 of the WDJ, 16 hex>`` so a test can find the pages in a report;
  ``summary.reportSections`` gives their page ranges;
- ``model.wdj``: the given WDJ with ``pickup_filename`` the PIK's file name and ``pickup_data``
  ``{"fake": "<SHA256 of the PIK bytes>"}``, as ``json.dumps(document, ensure_ascii=False, indent=2)`` in UTF-8;
- ``result.json``: ``{"returnCode": "OK", "outputFormat": "pdf", "messages": []}``.

Without ``--pickup`` (``run-rc --input <wdj> --output-dir <dir> --output-format pdf``, the WDJ holding its forces), it
writes ``result.json`` and a ``report.pdf`` of the sections the force table asks for, as the real runner of 2026-10-19
does: a row of the table (Md<id>_Md, Vd<id>_Vd, Mt<id>_Mt, by limit state id) gives its section (SECTION_OF_ROW), the
appearance check only with ``vis_u``, with the real runner's page counts (FORCE_SECTIONS, R5 of 2026-10-21; the footing
WDJ of 0810 and 0820 gives bending_safety_destruction, shear_safety_destruction, bending_durability,
bending_restorability_eq, shear_restorability_eq and bending_rebar_amount, the beam WDJ of 0910 every section but the
appearance), with the warnings WD-408 / WD-409 the real runner gives for the bending / shear rows without forces (the
beam's table has them all: none); no ``model.wdj`` comes back.

A circular WDJ (``shape`` 3: the pile body of a cast-in-place pile of 0612 and 0622, decision 91) is answered as the real runner of
2026-10-24 answers it: the force table gives bending_safety_destruction (1 page) and shear_safety_destruction (2 pages), but only
when every point has both ``isUpperCalc`` and ``isLowerCalc`` (with the lower side not calculated the real runner returns no
section at all), and its bars are the circle's: ``rebar1`` only, ``members[].n`` the piles and ``c_type`` set. Mode ``pile-skip``
leaves shear_safety_destruction out with the info message WD-1920 (Capacita skipped the shear check for zero forces).

``run-steel --input <wsj> --output-dir <dir>`` (the pile body of a steel pipe pile of 0612 and 0622, decision 89) writes ``result.json``
only, with the verifications SteelDan returns (engine steeldan, readiness experimental): for each point and force case 6, 7 and 8 of the
WSJ the checks pipePileBending, pipePileShear and pipePileCombined with their values, calculated by the same formulas as
Capacita/SteelDan PipePileVerifier (the same rounding), and the info message SD-NO-REPORT-SECTION. Modes ``steel-fail``,
``steel-engine``, ``steel-artifacts``, ``steel-sha``, ``steel-missing``, ``steel-short`` (a check left out), ``steel-duplicate``,
``steel-text-value`` (a value that is no number) and ``steel-version`` misbehave in it.

``--commentary-chapter <n> --commentary-first-section <k>`` (both or neither, after the others; decision 121) number the
commentary of a WDJ with ``calc.print_commentary_checked`` true: each reportSections item has ``heading``, "n.k" for the
first printed section of each commentary group (COMMENTARY_GROUPS, RcDan CommentaryGroups) numbered from k over the
printed groups, else null (the key is always there, as the real runner of 2026-10-29 writes it). Mode ``heading``
writes a heading of another chapter on the first section, ``headingtype`` a number in place of one.

When the real runner's protocol changes, change this too (the real-runner test is the signal). ``FAKE_CAPACITA`` makes
it misbehave, for the error tests: fail, pickup, exit, text, list, protocol, engine, version, artifacts (one artifact
listed twice), missing (model.wdj not written), sha (model.wdj's SHA256 wrong), extra (an unlisted file), sections
(no reportSections), order (the sections reversed), gap (the last section ends past the PDF), hole (the second
section starts a page late), broken (report.pdf is not a PDF). Two modes stand for Capacita skipping checks for zero
section forces (RcDan CheckValidation, as across the track in Example2): skip (shear_durability and
bending_serviceability left out, with the info messages WD-1919 and WD-1914), skipnocode (shear_durability left
out without its message).
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
            ("bending_restorability", 1), ("shear_restorability", 1), ("bending_rebar_amount", 1))
# The sections of a WDJ calculated as given, in the real runner's order with its page counts (2026-10-19).
FORCE_SECTIONS = (("bending_safety_destruction", 1), ("shear_safety_destruction", 2),
                  ("shear_deep_beam_safety_destruction", 1), ("torsion_safety_destruction", 3),
                  ("bending_safety_fatigue", 1), ("shear_safety_fatigue", 2), ("bending_durability", 2),
                  ("shear_durability", 2), ("torsion_durability", 2), ("bending_serviceability", 1),
                  ("bending_restorability", 1), ("shear_restorability", 2), ("torsion_restorability", 3),
                  ("bending_restorability_eq", 1), ("shear_restorability_eq", 2), ("torsion_restorability_eq", 3),
                  ("bending_rebar_amount", 3))
# The commentary groups, in report order (Capacita RcDan/Printers/Commentary/CommentaryGroups.cs): the first printed
# section of a group carries its heading.
COMMENTARY_GROUPS = (("section_forces",),
                     ("bending_safety_destruction", "shear_safety_destruction", "shear_deep_beam_safety_destruction",
                      "torsion_safety_destruction"),
                     ("bending_safety_fatigue", "shear_safety_fatigue"),
                     ("bending_durability", "shear_durability", "torsion_durability"), ("bending_serviceability",),
                     ("bending_restorability", "shear_restorability", "torsion_restorability"),
                     ("bending_restorability_eq", "shear_restorability_eq", "torsion_restorability_eq"),
                     ("bending_rebar_amount",))
# The section each row of the force table asks for, by the row's prefix and limit state id.
SECTION_OF_ROW = {("Md", 0): "bending_durability", ("Md", 1): "bending_durability", ("Md", 3): "bending_safety_fatigue",
                  ("Md", 4): "bending_safety_fatigue", ("Md", 5): "bending_safety_destruction",
                  ("Md", 6): "bending_restorability", ("Md", 7): "bending_restorability_eq",
                  ("Md", 8): "bending_rebar_amount",
                  ("Vd", 0): "shear_durability", ("Vd", 1): "shear_durability", ("Vd", 2): "shear_durability",
                  ("Vd", 3): "shear_safety_fatigue", ("Vd", 4): "shear_safety_fatigue",
                  ("Vd", 5): "shear_safety_destruction", ("Vd", 6): "shear_restorability",
                  ("Vd", 7): "shear_restorability_eq",
                  ("Mt", 0): "torsion_durability", ("Mt", 1): "torsion_durability", ("Mt", 5): "torsion_safety_destruction",
                  ("Mt", 6): "torsion_restorability", ("Mt", 7): "torsion_restorability_eq"}


def force_sections(document):
    """The sections the WDJ's force table asks for, in the real runner's order."""
    asked = set()
    for row in document.get("force") or ():
        for (prefix, number), section in SECTION_OF_ROW.items():
            if row.get(f"{prefix}{number}_{prefix}") is not None:
                asked.add(section)
    crack = (document.get("crack") or [{}])[0]
    if crack.get("vis_u") and "bending_durability" in asked:
        asked.add("bending_serviceability")
    # the points with a shear[].deep_beam (the footing of a pile foundation, decision 96) have the deep beam check in a section of
    # its own, a page each, and are not in the ordinary shear's
    deep = [row for row in document.get("shear") or () if row.get("deep_beam")]
    if deep:
        asked.discard("shear_safety_destruction")
        asked.add("shear_deep_beam_safety_destruction")
    else:
        asked.discard("shear_deep_beam_safety_destruction")
    if any(member.get("shape") == 3 for member in document.get("members") or ()) and not all(
            point.get("isUpperCalc") and point.get("isLowerCalc") for point in document.get("points") or ()):
        asked.clear()
    return [(name, len(deep) if name == "shear_deep_beam_safety_destruction" else pages)
            for name, pages in FORCE_SECTIONS if name in asked]


def circle_error(document):
    """What the real runner would not read of a circular WDJ (None when it reads it): a circle has a diameter B, a ``c_type`` and the
    piles in ``n``, and its bars are the first face's only."""
    for member in document.get("members") or ():
        if member.get("shape") == 3 and (not member.get("B") or member.get("c_type") not in (1, 2, 3) or not member.get("n")):
            return f"部材 {member.get('m_no')} の円形断面の入力が不足しています（B・c_type・n）"
    if any(member.get("shape") == 3 for member in document.get("members") or ()):
        for bar in document.get("bar") or ():
            if any(value is not None for key, value in bar["rebar2"].items() if key not in ("title", "enable")):
                return "円形断面は rebar2 を読みません"
    return None


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


def number_headings(ranges, numbering):
    """Each range's ``heading``: with *numbering* (chapter, first section), "chapter.k" on the first printed section of
    each commentary group, k counted over the printed groups; else null."""
    group, following = None, None if numbering is None else numbering[1]
    for item in ranges:
        own = next(index for index, sections in enumerate(COMMENTARY_GROUPS) if item["id"] in sections)
        item["heading"] = None
        if own != group:
            group = own
            if numbering is not None:
                item["heading"] = f"{numbering[0]}.{following}"
                following += 1


def round_half_up(value, digits):
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def pipe_pile(document, mode):
    """The verifications of the pile body (SteelDan PipePileVerifier): per point and case 6, 7, 8 of the force row."""
    import math

    members = {member["m_no"]: member for member in document["members"]}
    factors = document["safety"]["safety_factor"]["1"][1]
    gamma_i, gamma_t, gamma_c, gamma_s, gamma_m = (factors[key] for key in ("ri", "rb_T", "rb_C", "rb_S", "rs"))
    material = document["safety"]["material_steel"]["1"][0]
    verifications = []
    for point in document["points"]:
        section = next(item for item in document["sections"] if item["index"] == point["index"])
        row = next(item for item in document["force"] if item["index"] == point["index"])
        count = members[point["m_no"]]["n"] or 1
        outer, wall = section["h"], section["t"]
        inner = outer - 2 * wall
        area = round_half_up(math.pi / 4 * (outer ** 2 - inner ** 2) / 1e6, 5)
        inertia = round_half_up(math.pi / 64 * (outer ** 4 - inner ** 4) / 1e12, 8)
        distance = round_half_up(outer / 2, 1)
        fsyd = round_half_up(material["fsyk"] / gamma_m, 0)
        fsvyd = round_half_up(material["fsvyk"] / gamma_m, 0)
        tension = round_half_up(area * fsyd * 1000 / gamma_t, 1)
        compression = round_half_up(area * fsyd * 1000 / gamma_c, 1)
        bending_t = round_half_up(inertia / (distance / 1000) * fsyd * 1000 / gamma_t, 1)
        bending_c = round_half_up(inertia / (distance / 1000) * fsyd * 1000 / gamma_c, 1)
        shear = round_half_up(area * fsvyd * 1000 / gamma_s, 1)
        for case in (6, 7, 8):
            if row.get(f"{case}_Md") is None:
                continue
            md = round_half_up(abs(row[f"{case}_Md"] / count), 1)
            nd = round_half_up(row[f"{case}_Nd"] / count, 1)
            vd = round_half_up(abs(row[f"{case}_Vd"] / count), 1)
            common = {"case": case, "D": outer, "t": wall, "A": area, "I": inertia, "y": distance, "fsyk": material["fsyk"],
                      "fsvyk": material["fsvyk"], "gamma_s": gamma_m, "gamma_b_T": gamma_t, "gamma_b_C": gamma_c,
                      "gamma_b_S": gamma_s, "gamma_i": gamma_i, "fsyd": fsyd, "fsvyd": fsvyd, "Md": md, "Nd": nd, "Vd": vd}
            ratio_t = round_half_up(gamma_i * (-nd / tension + md / bending_t), 2)
            ratio_c = round_half_up(gamma_i * (nd / compression + md / bending_c), 2)
            ratio_s = round_half_up(gamma_i * vd / shear, 2)
            ratio_k = round_half_up((gamma_i / 1.1) ** 2 * ((nd / compression + md / bending_c) ** 2 + (vd / shear) ** 2), 2)
            for kind, ratio, own in (
                    ("pipePileBending", max(ratio_t, ratio_c), {"Nud": tension, "Nu0d": compression, "Mutd": bending_t,
                                                              "Mucd": bending_c, "ratio_tension": ratio_t,
                                                              "ratio_compression": ratio_c}),
                    ("pipePileShear", ratio_s, {"Vyd": shear}),
                    ("pipePileCombined", ratio_k, {"Nu0d": compression, "Mucd": bending_c, "Vyd": shear})):
                verifications.append({"kind": kind, "pointIndex": point["index"], "groupName": "G", "pointName": "P",
                                      "side": "-", "ratio": ratio, "status": "ok" if ratio <= 1 else "notOk",
                                      "values": {**common, **own, "ratio": ratio}})
    if mode == "steel-short":
        verifications.pop()
    if mode == "steel-duplicate":
        verifications.append(verifications[0])
    if mode == "steel-text-value":
        verifications[0]["values"]["A"] = "x"
    return verifications


def run_steel(argv, mode):
    if len(argv) != 5 or argv[1] != "--input" or argv[3] != "--output-dir":
        return failure("invalid_arguments", " ".join(argv), 2)
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("output_not_empty", str(output), 5)
    if mode == "steel-fail":
        print(json.dumps({**envelope(False, errors=[{"code": "calculation_failed", "message": "x"}]), "engine": "steeldan",
                          "messages": [{"level": "error", "code": "SD-FORCE-CASE", "text": "断面力がありません"}]},
                         ensure_ascii=False))
        return 4
    document = json.loads(source.read_bytes().decode("utf-8"))
    result = json.dumps({"status": "success", "hasEngineeringFailure": False, "messages": [],
                         "verifications": pipe_pile(document, mode)}, ensure_ascii=False).encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    if mode != "steel-missing":
        (output / "result.json").write_bytes(result)
    artifact = {"kind": "result", "mediaType": "application/json; charset=utf-8", "relativePath": "result.json",
                "bytes": len(result), "sha256": hashlib.sha256(b"other" if mode == "steel-sha" else result).hexdigest()}
    changes = {"steel-engine": {"engine": "webdan2"}, "steel-version": {"engineVersion": ""},
               "steel-artifacts": {"artifacts": [artifact, artifact]}}.get(mode, {})
    print(json.dumps({**envelope(True, [artifact], summary={"verificationCount": 0}), "engine": "steeldan",
                      "readiness": "experimental", "messages": [{"level": "info", "code": "SD-NO-REPORT-SECTION",
                                                                  "text": "PDFを生成しません。"}], **changes},
                     ensure_ascii=False))
    return 0


def run_pile_joint(argv, mode):
    """``run-pile-joint`` (the joint of a steel pipe pile, decision 90): ``result.json`` alone with Mu by row id. The Mu is a
    stand-in (2400 + 0.145 N'd, kN m) and the confinement is not calculated. Modes ``joint-fail``, ``joint-engine``, ``joint-version``,
    ``joint-artifacts``, ``joint-missing``, ``joint-sha``, ``joint-short``, ``joint-duplicate`` and ``joint-text-value`` misbehave in it."""
    if len(argv) != 5 or argv[1] != "--input" or argv[3] != "--output-dir":
        return failure("invalid_arguments", " ".join(argv), 2)
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("output_not_empty", str(output), 5)
    if mode == "joint-fail":
        print(json.dumps({**envelope(False, errors=[{"code": "calculation_failed", "message": "x"}]),
                          "messages": [{"level": "error", "code": "calculation_failed", "text": "HsCalc が計算できません"}]},
                         ensure_ascii=False))
        return 4
    document = json.loads(source.read_bytes().decode("utf-8"))
    rows = [{"id": row["id"], "axialForce": row["axialForce"],
             "mu": "x" if mode == "joint-text-value" else round_half_up(2400 + 0.145 * row["axialForce"], 1)}
            for row in document["rows"]]
    if mode == "joint-short":
        rows.pop()
    if mode == "joint-duplicate":
        rows.append(rows[0])
    result = json.dumps({"rows": rows}, ensure_ascii=False).encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    if mode != "joint-missing":
        (output / "result.json").write_bytes(result)
    artifact = {"kind": "result", "mediaType": "application/json; charset=utf-8", "relativePath": "result.json",
                "bytes": len(result), "sha256": hashlib.sha256(b"other" if mode == "joint-sha" else result).hexdigest()}
    changes = {"joint-engine": {"engine": "steeldan"}, "joint-version": {"engineVersion": ""},
               "joint-artifacts": {"artifacts": [artifact, artifact]}}.get(mode, {})
    print(json.dumps({**envelope(True, [artifact], summary={"rowCount": len(rows)}), "readiness": "experimental", **changes},
                     ensure_ascii=False))
    return 0


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
    if argv and argv[0] == "run-steel":
        return run_steel(argv, mode)
    if argv and argv[0] == "run-pile-joint":
        return run_pile_joint(argv, mode)
    numbering = None
    if len(argv) >= 4 and argv[-4] == "--commentary-chapter" and argv[-2] == "--commentary-first-section":
        if not all(text.isdigit() and int(text) > 0 for text in (argv[-3], argv[-1])):
            return failure("invalid_commentary_number", " ".join(argv), 2)
        numbering, argv = (int(argv[-3]), int(argv[-1])), argv[:-4]
    if (len(argv) not in (7, 9) or argv[0] != "run-rc" or argv[1] != "--input" or argv[3] != "--output-dir"
            or argv[5:7] != ["--output-format", "pdf"] or (len(argv) == 9 and argv[7] != "--pickup")
            or "--commentary-chapter" in argv or "--commentary-first-section" in argv):
        return failure("invalid_arguments", " ".join(argv), 2)
    source, output = Path(argv[2]), Path(argv[4])
    pickup = Path(argv[8]) if len(argv) == 9 else None
    if output.exists() and any(output.iterdir()):
        return failure("output_not_empty", str(output), 5)
    if mode == "fail":
        return failure("calculation_failed", "RcDanが計算を完了できませんでした。", 4)
    if mode == "pickup":
        return failure("pickup_import_failed", "IMPORT-EXISTING-POINT-IDENTITY /points/0/position: 一致しません", 2)
    wdj = source.read_bytes()
    document = json.loads(wdj.decode("utf-8"))
    digest = hashlib.sha256(wdj).hexdigest()
    skipped = {"skip": {"shear_durability": "WD-1919", "bending_serviceability": "WD-1914"},
               "skipnocode": {"shear_durability": None}}.get(mode, {})
    if pickup is None:
        if (message := circle_error(document)) is not None:
            return failure("calculation_failed", message, 4)
        shown = force_sections(document)
        if mode == "pile-skip":
            shown = [(name, pages) for name, pages in shown if name != "shear_safety_destruction"]
        row = (document.get("force") or [{}])[0]
        missing = {"WD-408": any(row.get(f"Md{id_}_Md") is None for id_ in (0, 1, 3, 4, 5, 6, 7, 8)),
                   "WD-409": any(row.get(f"Vd{id_}_Vd") is None for id_ in range(8))}
        messages = [{"level": "warn", "code": code, "text": text} for code, text in (
            ("WD-408", "曲げ照査用断面力データが見つかりませんでした。"), ("WD-409", "せん断照査用断面力データが見つかりませんでした。"))
            if missing[code]]
        if mode == "pile-skip":
            messages.append({"level": "info", "code": "WD-1920", "text": "shear_safety_destruction をスキップしました"})
    else:
        shown = [(name, pages) for name, pages in SECTIONS
                 if (name != "bending_serviceability" or document["crack"][0]["vis_u"]) and name not in skipped]
        messages = [{"level": "info", "code": code, "text": f"{name} をスキップしました"}
                    for name, code in skipped.items() if code is not None]
    pdf, ranges = report(shown, digest)
    if mode == "broken":
        pdf = b"not a pdf"
    result = json.dumps({"returnCode": "OK", "outputFormat": "pdf", "messages": []}).encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    files = [("result", "application/json; charset=utf-8", "result.json", result),
             ("report", "application/pdf", "report.pdf", pdf)]
    if pickup is not None:
        document["pickup_filename"] = pickup.name
        document["pickup_data"] = {"fake": hashlib.sha256(pickup.read_bytes()).hexdigest()}
        completed = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        files.append(("wdj", "application/json; charset=utf-8", "model.wdj", completed))
    artifacts = []
    for kind, media, name, content in files:
        if not (mode == "missing" and name == "model.wdj"):
            (output / name).write_bytes(content)
        artifacts.append({"kind": kind, "mediaType": media, "relativePath": name, "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and name == "model.wdj"
                                                   else content).hexdigest()})
    if mode == "extra":
        (output / "summary.xlsx").write_bytes(b"x")
    number_headings(ranges, numbering if (document.get("calc") or {}).get("print_commentary_checked") else None)
    if mode == "heading":
        ranges[0]["heading"] = "1.5"
    if mode == "headingtype":
        ranges[0]["heading"] = 8.5
    if mode == "order":
        ranges.reverse()
    if mode == "gap":
        ranges[-1]["lastPage"] += 1
    if mode == "hole":
        ranges[1]["firstPage"] += 1
    summary = {"returnCode": "OK", "outputFormat": "pdf", "messageCounts": {}, "reportSections": ranges}
    if mode == "sections":
        del summary["reportSections"]
    changes = {"protocol": {"protocolVersion": 2}, "engine": {"engine": "steeldan"}, "version": {"engineVersion": ""},
               "artifacts": {"artifacts": [*artifacts, artifacts[0]]}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts, summary=summary, messages=messages), **changes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
