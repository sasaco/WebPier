"""A stand-in for ``FrameWebforCS.Headless.exe run``: the load diagram (decision 44, ADR-0005) and the frame analysis
(decision 46, ADR-0006).

It follows the runner's protocol as WebPier uses it (FEMPython FrameWebforCS/Headless/README.md): the arguments of
``webpier.pipeline.fempython`` (``ARGUMENTS`` or ``ANALYSIS_ARGUMENTS``), an output directory that must be absent or
empty, the files in it, and one UTF-8 JSON envelope (protocolVersion 1) on stdout. Instead of the drawing it writes
``report.pdf`` with one page per two load cases of the FrameWeb file, each page saying which file and cases it stands
for, so a test can find the pages in a report. Instead of the analysis it writes ``result.json`` and, for the three
files WebPier publishes, the line ``FAKE PIK <file name> <SHA256 of the input bytes>`` (``pickup.pik``), ``FAKE
DISPLACEMENT …`` (``pickup-displacement.csv``), UTF-8 with LF, so a test can tell which bytes were analyzed, and the
reaction pickup (``pickup-reaction.csv``) in the real runner's columns: a header (units as the real runner leaves
them), then for every pickup, focus component (fx, fy, mz) and node of the file one row of the largest and the
smallest extreme over the pickup's combinations, with the forces of that combination. Only the support nodes
(``fix_node``) have forces, those of ``reaction(c)`` for combination c, so a test knows what the 基礎の照査 reads
(decision 54); every other node has zeros and the pickup's first combination. In the PIK that line stands for the header and is followed by the points
of the first pickup in the real runner's fixed columns (PickUpNo, 着目力 M, 部材No, cases, 着目点, 着目点距離, zero
forces): every member in order with ITAN, a numbered point where a member load on it starts or ends inside it, and
JTAN, so the place of a point (export.capacita.point_index) is the real runner's for the same file. When the real
runner's protocol changes, change this too (the real-runner tests are the signal).

A FrameWeb document of a pile foundation (it has ``fix_member``, decision 88) also has, for the 基礎の照査 of 0612 / 0622 (decision 89),
a line of the axial force N at the head (ITAN) of each member that has a distributed spring, for every pickup, after the
points (``head(member, pickup)``), and a displacement pickup CSV in the real runner's columns, for every pickup, node and
focus component (dx, dy, rz) one row of the largest and the smallest extreme (``motion(node, pickup, focus)``).

``FAKE_FEMPYTHON`` makes it misbehave, for the error tests: fail, text, list, protocol, version, artifacts (one
artifact listed twice), missing (the last file not written), sha (the last file's SHA256 wrong), exit, and for the
load diagram badpdf and empty. Prefixed with ``analysis-`` a mode applies to the analysis call only.
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
ANALYSIS = ["--generate-pdf", "false", "--generate-pik", "true", "--generate-pickup-displacement-csv", "true",
            "--generate-pickup-reaction-csv", "true"]
MEDIA = {"pdf": "application/pdf", "result": "application/json", "pik": "text/plain; charset=utf-8"}


def envelope(ok, artifacts=(), errors=(), calculated=False, **changes):
    value = {"protocolVersion": 1, "engine": "fempython", "engineVersion": "fake-1", "readiness": "experimental",
             "ok": ok, "executionStatus": "success" if ok else "failed",
             "engineeringStatus": "not_checked" if ok else "not_applicable",
             "summary": {"calculated": calculated}, "messages": [], "artifacts": list(artifacts),
             "errors": list(errors)}
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


def points(document):
    """(member, point, position) of every member of a FrameWeb document, in member order."""
    nodes = document.get("node", {})
    for number, member in document.get("member", {}).items():
        start, end = nodes[str(member["ni"])], nodes[str(member["nj"])]
        length = round(((end["x"] - start["x"]) ** 2 + (end["y"] - start["y"]) ** 2) ** 0.5, 3)
        inside = sorted({round(position, 3) for case in document["load"].values()
                         for load in case.get("load_member", []) if str(load.get("m1")) == number
                         for position in (load["L1"], length - load["L2"]) if 0 < round(position, 3) < length})
        yield number, "ITAN", 0.0
        yield from ((number, str(index), position) for index, position in enumerate(inside, 1))
        yield number, "JTAN", length


def pik(source, digest):
    document = json.loads(source.read_text(encoding="utf-8"))
    rows = [f"{1:>5}{'M':>5}{number:>5}{1:>5}{1:>5}{point:>5}{position:>10.3f}" + f"{0:>10.2f}" * 6
            for number, point, position in points(document)]
    return "".join(f"{line}\n" for line in [f"FAKE PIK {source.name} {digest}", *rows, *pile_heads(document), *pile_points(document)]).encode()


def head(member, pickup):
    """(largest, smallest axial force) of the head of a pile member in a pickup: compression is negative, and the
    largest is a tension (the member's number added) in the pickups of even number."""
    return (60.0 + member if pickup % 2 == 0 else -50.0), -(3000.0 + 10.0 * member + 100.0 * pickup)


def motion(node, pickup, focus):
    """(largest, smallest) of the displacement component *focus* of a node in a pickup: dx and dy in m, rz in rad."""
    scale = {"dx": 0.001, "dy": 0.0005, "rz": 0.0001}[focus]
    return scale * (pickup + node / 10), -scale * (2 * pickup + node / 10)


def pile_members(document):
    return sorted({int(row["m"]) for rows in document.get("fix_member", {}).values() for row in rows})


def pile_heads(document):
    """The N lines of the heads of the pile members, for every pickup, in the PIK's fixed columns."""
    lines = []
    for number, pickup in document.get("pickup", {}).items():
        combinations = [pickup[key] for key in pickup if key.startswith("C")]
        for member in pile_members(document):
            largest, smallest = head(member, int(number))
            lines.append(f"{number:>5}{'N':>5}{member:>5}{combinations[0]:>5}{combinations[-1]:>5}{'ITAN':>5}{0.0:>10.3f}"
                         + f"{0.0:>10.2f}" * 2 + f"{largest:>10.2f}" + f"{0.0:>10.2f}" * 2 + f"{smallest:>10.2f}")
    return lines


def pile_points(document):
    """The lines of the inner point (3.75 m from the head) of the pile members, for every pickup: the focus M, S and N, each with
    the forces of its largest and its smallest case (``inner(member)``), so that the pile body takes them (decision 89)."""
    lines = []
    for number, pickup in document.get("pickup", {}).items():
        combinations = [pickup[key] for key in pickup if key.startswith("C")]
        for member in pile_members(document):
            for focus, (largest, smallest) in inner(member).items():
                lines.append(f"{number:>5}{focus:>5}{member:>5}{combinations[0]:>5}{combinations[-1]:>5}{'1':>5}{3.75:>10.3f}"
                             + "".join(f"{value:>10.2f}" for value in (*largest, *smallest)))
    return lines


def inner(member):
    """((Md, Vd, Nd) of the largest, of the smallest case) of each focus at the inner point of a pile member."""
    return {"M": ((200.0 + member, 20.0, -(1000.0 + member)), (-(150.0 + member), -20.0, -900.0)),
            "S": ((50.0, 300.0 + member, -2000.0), (-50.0, -(250.0 + member), -1800.0)),
            "N": ((10.0, 5.0, -500.0), (30.0, 40.0, -(4000.0 + 10.0 * member)))}


DISPLACEMENT_HEADER = ("pickup_id,focus_component,node_id,max_combine_id,min_combine_id,"
                       + ",".join(f"{side}_{name} ({unit})" for side in ("max", "min")
                                  for name, unit in (("dx", "unspecified"), ("dy", "unspecified"), ("dz", "unspecified"),
                                                     ("rx", "rad"), ("ry", "rad"), ("rz", "rad"))))


def displacements(document):
    """The displacement pickup CSV of a pile document (see the module docstring): the extreme of the row's focus
    component, the other components zero; the combinations are the pickup's first (largest) and last (smallest)."""
    lines = [DISPLACEMENT_HEADER]
    for number, pickup in document.get("pickup", {}).items():
        combinations = [pickup[key] for key in pickup if key.startswith("C")]
        for focus in ("dx", "dy", "rz"):
            for node in document.get("node", {}):
                largest, smallest = motion(int(node), int(number), focus)
                values = [[largest if name == focus else 0.0 for name in ("dx", "dy", "dz", "rx", "ry", "rz")],
                          [smallest if name == focus else 0.0 for name in ("dx", "dy", "dz", "rx", "ry", "rz")]]
                cells = [f"{v!r}" for row in values for v in row]
                lines.append(f"{number},{focus},{node},{combinations[0]},{combinations[-1]}," + ",".join(cells))
    return "".join(f"{line}\n" for line in lines).encode()


def reaction(combination):
    """(fx, fy, mz) at a support node for *combination*: fy downward, so the vertical reaction is upward (negative)."""
    sign = -1 if combination % 2 else 1
    return 10.5 * combination * sign, -(15000.0 + 125.25 * combination), -40.5 * combination * sign


REACTION_HEADER = ("pickup_id,focus_component,node_id,max_combine_id,min_combine_id,"
                   + ",".join(f"{side}_{name} ({unit})" for side in ("max", "min")
                              for name, unit in (("fx", "unspecified"), ("fy", "unspecified"), ("fz", "unspecified"),
                                                 ("mx", "unspecified*unspecified"), ("my", "unspecified*unspecified"),
                                                 ("mz", "unspecified*unspecified"))))


def reactions(document):
    """The reaction pickup CSV of a FrameWeb document (see the module docstring)."""
    supports = {str(item["n"]) for rows in document.get("fix_node", {}).values() for item in rows}
    lines = [REACTION_HEADER]
    for number, pickup in document.get("pickup", {}).items():
        combinations = [pickup[key] for key in pickup if key.startswith("C")]
        for focus, index in (("fx", 0), ("fy", 1), ("mz", 2)):
            for node in document.get("node", {}):
                if node in supports:
                    largest = max(combinations, key=lambda c: reaction(c)[index])
                    smallest = min(combinations, key=lambda c: reaction(c)[index])
                else:
                    largest = smallest = combinations[0]
                forces = [reaction(c) if node in supports else (0.0, 0.0, 0.0) for c in (largest, smallest)]
                values = [f"{fx!r},{fy!r},0,0,0,{mz!r}" for fx, fy, mz in forces]
                lines.append(f"{number},{focus},{node},{largest},{smallest},{values[0]},{values[1]}")
    return "".join(f"{line}\n" for line in lines).encode()


def analysis(source):
    """(file, kind, bytes) of a frame analysis of *source*, in the order the real runner lists them."""
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    document = json.loads(source.read_text(encoding="utf-8"))
    return [("result.json", "result", json.dumps({"kind": "frameweb_analysis", "input": digest}).encode()),
            ("pickup.pik", "pik", pik(source, digest)),
            ("pickup-displacement.csv", "pickup-displacement",
             displacements(document) if "fix_member" in document else
             f"FAKE DISPLACEMENT {source.name} {digest}\n".encode()),
            ("pickup-reaction.csv", "pickup-reaction", reactions(document))]


def failure(code, message, category):
    print(json.dumps(envelope(False, errors=[{"code": code, "message": message, "category": category}])))
    return 1


def main(argv):
    analyzing = argv[5:] == ANALYSIS
    mode = os.environ.get("FAKE_FEMPYTHON", "")
    if mode.startswith("analysis-"):
        mode = mode.removeprefix("analysis-") if analyzing else ""
    if mode == "exit":
        return 3
    if mode == "text":
        sys.stdout.write("not json")
        return 1
    if mode == "list":
        sys.stdout.write("[]")
        return 0
    if argv[:1] != ["run"] or argv[1] != "--input" or argv[3] != "--output-dir" or argv[5:] not in (EXPECTED,
                                                                                                   ANALYSIS):
        return failure("INVALID_ARGUMENT", " ".join(argv), "input")
    source, output = Path(argv[2]), Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", str(output), "output")
    if mode == "fail":
        return (failure("EMPTY_PIK", "PIK output contains no data rows.", "output") if analyzing
                else failure("LOAD_DIAGRAM_REQUIRES_2D", "2D only", "input"))
    if analyzing:
        outputs = analysis(source)
    else:
        document = json.loads(source.read_text(encoding="utf-8"))
        pdf = {"badpdf": b"%PDF-1.4 broken", "empty": drawing(source.name, [])}.get(
            mode, drawing(source.name, list(document["load"])))
        outputs = [("report.pdf", "pdf", pdf)]
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for number, (name, kind, content) in enumerate(outputs, 1):
        last = number == len(outputs)
        if not (mode == "missing" and last):
            (output / name).write_bytes(content)
        artifacts.append({"kind": kind, "mediaType": MEDIA.get(kind, "text/csv; charset=utf-8"), "relativePath": name,
                          "bytes": len(content),
                          "sha256": hashlib.sha256(b"other" if mode == "sha" and last else content).hexdigest()})
    changes = {"protocol": {"protocolVersion": 2}, "version": {"engineVersion": ""},
               "artifacts": {"artifacts": [*artifacts, artifacts[0]]}}.get(mode, {})
    print(json.dumps({**envelope(True, artifacts, calculated=analyzing), **changes}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
