"""Real-app acceptance of the 0711 / 0721 reports: Aggre-SE's 耐震性能照査 (decision 56, ADR-0009).

For each direction, ``python -m webpier`` is generated from the input choosing 0711 (0721) and the items it uses
(decision 72) into a temporary folder with the real JRSNAP and Aggre-SE runners (``STRUCTURAL_MCP_JRSNAP_RUNNER``, ``STRUCTURAL_MCP_AGGRESE_RUNNER``, as a normal
generation finds them). From the published report (Aggre-SE's ``report.pdf`` as it is) the response values of each
Case are read: Kheq, δeq, and μ, δr and Khr for the safety and the restorability checks (the pages
「(2)非線形応答スペクトル法による設計応答値の算定」, one per Case), with the page count; of the published pickup
(decision 57), its SHA256, its lines and its pickup numbers; of the published summary workbook (decision 58), its
sheet names (its bytes differ each run). The longitudinal Case 1 is
compared with Example2 10-14; the transverse one is only recorded (its wind load differs: decisions 12, 35).

The record (tests/fixtures/acceptance/aggrese_report/record.json) holds the input, the project WebPier wrote for the
DB1 of the analysis (its SHA256 and the DB1 names, so tests/acceptance can check that the generator still writes it),
the runners' versions, the values and the comparison. Aggre-SE's judgement (OK / NG) is not recorded: the runner
returns none (ADR-0009).
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
import zipfile

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import canonical_sha256, content_sha256, dump_json, file_sha256, load_json  # noqa: E402
from webpier.pipeline import aggrese  # noqa: E402
from webpier.inputs.outputs import OUTPUT_KEYS, uses  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402
from webpier.pipeline.stages import STAGES  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "current.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "aggrese_report"
STAGES_ACCEPTED = ("0711", "0721")
RESPONSE = "(2)非線形応答スペクトル法による設計応答値の算定"
# Example2 10-14 (線路方向 Case1 ← ρm=1.0, αf=1.0).
EXAMPLE2 = {"0711": [{"kheq": 0.368, "delta_eq": 30.5, "safety": {"mu": 9.32, "delta_r": 284.3, "khr": 0.386},
                      "restorability": {"mu": 5.78, "delta_r": 176.3, "khr": 0.385}}]}


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def _number(pattern: str, text: str, what: str) -> float:
    found = re.findall(pattern, text)
    if not found:
        raise AcceptanceError(f"計算書に {what} がありません")
    return float(found[0])


def _check(text: str) -> dict[str, float]:
    return {"mu": _number(r"μ = ([\d.]+)", text, "μ"),
            "delta_r": _number(r"δr = μ・δeq = [\d.]+ × [\d.]+ = ([\d.]+) mm", text, "δr"),
            "khr": _number(r"Khr = ([\d.]+)", text, "Khr")}


def responses(pdf: bytes) -> tuple[int, list[dict[str, Any]]]:
    """The page count and the response values of each Case, from its 応答値の算定 page."""
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        texts = [page.get_text() for page in document]
    cases = []
    for text in texts:
        if not text.startswith(RESPONSE):
            continue
        safety, _, rest = text.partition("4)復旧性を検討するための地震動に対する応答値の算定")
        restorability = rest.partition("5) L1地震動に対する応答値の算定")[0]
        if not rest:
            raise AcceptanceError("計算書の応答値の算定に復旧性の節がありません")
        cases.append({"kheq": _number(r"Ｋheq = ([\d.]+)", text, "Kheq"),
                      "delta_eq": _number(r"δeq\s+= ([\d.]+) mm", text, "δeq"),
                      "safety": _check(safety.partition("2)応答塑性率および最大応答変位の算定")[2]),
                      "restorability": _check(restorability)})
    return len(texts), cases


def pickup(path: Path) -> dict[str, Any]:
    """The published PIK (decision 57): its bytes, its first line and the pickup numbers of its lines."""
    lines = path.read_bytes().decode("cp932").split("\r\n")
    if lines[-1] == "":
        lines.pop()
    numbers = sorted({int(line.split()[0]) for line in lines[1:]})
    return {"file": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size, "lines": len(lines),
            "header": lines[0], "pickups": numbers}


def workbook(path: Path) -> dict[str, Any]:
    """The published summary workbook (decision 58): its sheet names, in order."""
    with zipfile.ZipFile(path) as archive:
        listed = archive.read("xl/workbook.xml").decode("utf-8")
    return {"file": path.name, "bytes": path.stat().st_size,
            "sheets": [html.unescape(name) for name in re.findall(r'<sheet [^>]*name="([^"]*)"', listed)]}


def choosing(input_path: Path, stage: str, work: Path) -> Path:
    """A copy of the input at *input_path* choosing the 出力項目 of *stage* and every item it uses (decision 72)."""
    data = load_json(input_path.read_bytes())
    item = STAGES.item(stage)
    data["outputs"] = {key: key == item or key in uses(item) for key in OUTPUT_KEYS}
    path = work / f"{stage}-input.json"
    path.write_bytes(dump_json(data))
    return path


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict[str, Any]:
    if evidence.exists() and not overwrite:
        raise AcceptanceError(f"受入記録が既にあります（--overwrite で作り直します）: {evidence}")
    implementation = canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()})
    runner = aggrese.runner_path()
    directions: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="webpier-aggrese-report-acceptance-") as temporary:
        work = Path(temporary)
        for stage in STAGES_ACCEPTED:
            spec = STAGES.get(stage)
            analysis = spec.nonlinear_analysis
            generated = work / stage
            generate(GenerationOptions(choosing(input_path, stage, work), generated / "output", generated / "post"))
            post, report = generated / "post", generated / "output" / f"{spec.stem}.pdf"
            result = load_json((generated / "output" / f"{spec.stem}.json").read_bytes())
            folder = load_json((post / (analysis.folder + ".provenance.json")).read_bytes())
            pages, cases = responses(report.read_bytes())
            checked = result["seismic_check"]
            if len(cases) != len(checked["cases"]):
                raise AcceptanceError(f"{stage}: 応答値の算定のページが Case の数（{len(checked['cases'])}）と違います")
            direction = {
                "project": {"file": analysis.project.file_name,
                            "sha256": file_sha256(post / analysis.project.file_name),
                            "databases": sorted(path.name for path in (post / analysis.folder).glob("*.DB1"))},
                "jrsnap": {"folder": analysis.folder, "sha256": content_sha256(post / analysis.folder),
                           "runner_engine_version": folder["nonlinear_analysis"]["engine_version"],
                           "product": folder["nonlinear_analysis"]["runner_summary"]["jrsnap"]["product"]},
                "seismic_check": checked,
                "report": {"file": report.name, "bytes": report.stat().st_size, "pages": pages},
                "cases": cases,
                "pik": pickup(post / dict(spec.seismic_check.files)["pik"]),
                "xlsx": workbook(post / dict(spec.seismic_check.files)["xlsx"]),
            }
            if stage in EXAMPLE2:
                direction["example2"] = {"source": "Example橋脚2/10_線路(耐震).pdf 10-14", "values": EXAMPLE2[stage],
                                         "matches": cases == EXAMPLE2[stage]}
                if cases != EXAMPLE2[stage]:
                    raise AcceptanceError(f"{stage}: 応答値が見本 10-14 と違います: {cases} / {EXAMPLE2[stage]}")
            directions[stage] = direction
    record = {
        "schema_version": 1, "kind": "aggrese_report_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("本物の JRSNAP と Aggre-SE の runner で 0711・0721 を生成し、計算書（Aggre-SE の report.pdf そのもの）の"
                   "応答値の算定のページから Case ごとの Kheq・δeq と、安全性・復旧性の μ・δr・Khr を読んだ。線路方向は見本 "
                   "10-14 と比べ、線路直角方向は風荷重の差（決定12・35）があるので記録だけにした。Aggre-SE の照査の判定は"
                   "扱わない。"),
        "seismic_check_judged": False,
        "input": {"path": _relative(input_path), "sha256": file_sha256(input_path)},
        "implementation_sha256": implementation,
        "runner": {"path": str(runner), "sha256": file_sha256(runner)},
        "helpers": {_relative(Path(__file__)): file_sha256(Path(__file__))},
        "directions": directions,
    }
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)
    (evidence / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                          newline="\n")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        record = accept(args.input.resolve(), args.evidence.resolve(), args.overwrite)
    except AcceptanceError as exc:
        print(f"受入できません: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({stage: {"pages": value["report"]["pages"], "cases": value["cases"]}
                      for stage, value in record["directions"].items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
