"""The Capacita runner of the 0611 / 0621 柱の断面照査 (decision 48, ADR-0008).

The runner is found from STRUCTURAL_MCP_WEBDAN_RUNNER (environment, then .env; the name structural-mcp uses) and called
as ``run-rc --pickup`` with the WDJ and the PIK of the same generation. Its envelope, its three files and the page
ranges of the report sections are checked as the Capacita README states; a section asked for may be missing only with
Capacita's code for a check skipped for zero section forces. Every case but the last two uses the stand-in of
tests/fixtures/capacita/fake_runner.py (tests/conftest.py); the last two run the real runner on the Example2 input in
both directions, only when one is set up.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from webpier.pipeline import capacita
from webpier.pipeline.capacita import RUNNER_KEY, check_column, check_section, runner_path
from webpier.pipeline.fempython import RunnerError

SECTIONS = ("section_forces", "bending_safety_destruction", "shear_safety_destruction", "bending_durability",
            "shear_durability", "bending_serviceability", "bending_restorability", "shear_restorability",
            "bending_rebar_amount")
WDJ = json.dumps({"crack": [{"vis_u": True}], "points": []}).encode("utf-8")
PIK = b"PickUpNo\n    1    M    1\n"
FOOTING_SECTIONS = ("bending_safety_destruction", "shear_safety_destruction", "bending_durability",
                    "bending_restorability_eq", "shear_restorability_eq", "bending_rebar_amount")
# The force table asks for the footing's sections (the stand-in derives them from the rows, as the real runner does).
FOOTING_WDJ = json.dumps({"pickup_filename": "", "crack": [{"vis_u": False}],
                          "force": [{"index": 1, "Md0_Md": -100.0, "Md5_Md": 799.16, "Vd5_Vd": 500.0,
                                     "Md8_Md": -100.0},
                                    {"index": 2, "Md7_Md": -900.0, "Vd7_Vd": 600.0}]}).encode("utf-8")


def completed(document: bytes, pik_name: str, pik: bytes) -> bytes:
    """The WDJ the stand-in returns (its docstring), written out without the implementation."""
    value = json.loads(document)
    value["pickup_filename"] = pik_name
    value["pickup_data"] = {"fake": hashlib.sha256(pik).hexdigest()}
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def texts(pdf: bytes) -> list[str]:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return [page.get_text().strip() for page in document]


def test_the_environment_comes_before_the_env_file(tmp_path: Path):
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\nSTRUCTURAL_MCP_FEMPYTHON_RUNNER=x\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env) == runner
    assert runner_path({RUNNER_KEY: ""}, env) == other
    assert runner_path({}, env) == other


def test_the_headless_runner_reads_only_the_environment(tmp_path: Path):
    """Decision 61: without dotenv a runner set only in the .env file is not set."""
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env, dotenv=False) == runner
    with pytest.raises(RunnerError, match=f"環境変数 {RUNNER_KEY} に WebDanforCS.Headless.exe の絶対パスを設定してください"):
        runner_path({}, env, dotenv=False)


@pytest.mark.parametrize("setting,message", [(None, "Capacita の runner が設定されていません"), ("", "設定されていません"),
                                             ("runner.exe", "絶対パス"), ("missing", "ありません")])
def test_a_runner_that_is_not_set_up_is_an_error(tmp_path: Path, setting, message):
    env = tmp_path / ".env"
    if setting is not None:
        value = str(tmp_path / "missing.exe") if setting == "missing" else setting
        env.write_text(f"{RUNNER_KEY}={value}\n", encoding="utf-8")
    with pytest.raises(RunnerError, match=message):
        runner_path({}, env)


def test_the_process_environment_is_used_by_default(monkeypatch: pytest.MonkeyPatch, fake_capacita_runner: Path):
    monkeypatch.setenv(RUNNER_KEY, str(fake_capacita_runner))
    assert runner_path() == fake_capacita_runner


def test_the_stand_in_checks_the_given_wdj_with_the_given_pik(fake_capacita_runner: Path):
    checked = check_column(WDJ, "線路方向.pik", PIK, fake_capacita_runner, SECTIONS)
    assert checked.engine_version == "fake-1"
    assert checked.wdj == completed(WDJ, "線路方向.pik", PIK)
    assert [section.id for section in checked.sections] == list(SECTIONS)
    assert [(section.first, section.last) for section in checked.sections][:2] == [(1, 2), (3, 3)]
    pages = texts(checked.pdf)
    assert len(pages) == 10
    digest = hashlib.sha256(WDJ).hexdigest()[:16]
    assert pages[0] == f"FAKE CAPACITA section_forces 1/2 {digest}"
    assert checked.section("shear_restorability") == (9, 9)


def test_a_section_capacita_skipped_for_zero_forces_is_missing_with_its_code(fake_capacita_runner: Path,
                                                                           monkeypatch: pytest.MonkeyPatch):
    """WD-1919 (耐久性せん断) and WD-1914 (使用性曲げ): RcDan CheckValidation, as Example2 across the track."""
    monkeypatch.setenv("FAKE_CAPACITA", "skip")
    checked = check_column(WDJ, "線路直角方向.pik", PIK, fake_capacita_runner, SECTIONS)
    assert checked.skipped == ("shear_durability", "bending_serviceability")
    assert [section.id for section in checked.sections] == [name for name in SECTIONS if name not in checked.skipped]
    assert checked.section("shear_durability") is None and checked.section("bending_restorability") == (6, 6)
    with pytest.raises(KeyError):
        checked.section("torsion_durability")
    monkeypatch.setenv("FAKE_CAPACITA", "skipnocode")
    with pytest.raises(RunnerError, match="計算書の節が違います"):
        check_column(WDJ, "線路直角方向.pik", PIK, fake_capacita_runner, SECTIONS)


def test_the_report_takes_the_pages_of_each_returned_section_by_its_id(fake_capacita_runner: Path,
                                                                       monkeypatch: pytest.MonkeyPatch):
    """Each section's page range of the report, cut as it is (assembly.page_range); a skipped section has none."""
    monkeypatch.setenv("FAKE_CAPACITA", "skip")
    checked = check_column(WDJ, "線路直角方向.pik", PIK, fake_capacita_runner, SECTIONS)
    report = texts(checked.pdf)
    assert list(checked.pages) == [section.id for section in checked.sections]
    assert {section: texts(content) for section, content in checked.pages.items()} == {
        section.id: report[section.first - 1:section.last] for section in checked.sections}
    assert len(texts(checked.pages["section_forces"])) == 2 and "shear_durability" not in checked.pages


def test_the_codes_of_the_skipped_checks_are_capacitas():
    """RcDan ErrorMessage_1000_1999 (ZeroForce_RailR5_*): the R5 messages of every body (decision 73)."""
    assert capacita.SKIPPED == {"bending_serviceability": "WD-1914", "bending_safety_destruction": "WD-1915",
                                "bending_safety_fatigue": "WD-1916", "bending_restorability": "WD-1917",
                                "bending_restorability_eq": "WD-1918", "shear_durability": "WD-1919",
                                "shear_safety_destruction": "WD-1920", "shear_restorability": "WD-1921",
                                "shear_restorability_eq": "WD-1922", "torsion_durability": "WD-1923",
                                "torsion_safety_destruction": "WD-1924", "torsion_restorability": "WD-1925",
                                "torsion_restorability_eq": "WD-1926"}


def test_the_sections_follow_the_checks_asked_for(fake_capacita_runner: Path):
    without = json.dumps({"crack": [{"vis_u": False}]}).encode("utf-8")
    expected = tuple(name for name in SECTIONS if name != "bending_serviceability")
    assert [section.id for section in check_column(without, "a.pik", PIK, fake_capacita_runner, expected).sections] \
        == list(expected)
    with pytest.raises(RunnerError, match="計算書の節が違います"):
        check_column(without, "a.pik", PIK, fake_capacita_runner, SECTIONS)


@pytest.mark.parametrize("mode,message", [
    ("fail", "calculation_failed: RcDanが計算を完了できませんでした。"), ("pickup", "pickup_import_failed"),
    ("exit", "JSON ではありません"), ("text", "JSON ではありません"), ("list", "オブジェクトではありません"),
    ("protocol", "やり取りの版が違います"), ("engine", "やり取りの版が違います"), ("version", "engineVersion"),
    ("artifacts", "成果物が計算結果・計算書・WDJ の3つではありません"),
    ("missing", "成果物 model.wdj がありません"), ("extra", "出力先のファイルが成果物の一覧と一致しません"),
    ("sha", r"model\.wdj が runner の応答の SHA256・バイト数と一致しません"),
    ("sections", "計算書の節（reportSections）がありません"), ("order", "計算書の節が違います"),
    ("gap", "計算書の節のページが PDF の"),
    ("hole", "計算書の節のページが PDF の"), ("broken", "計算書の PDF を読めません"),
])
def test_a_runner_that_does_not_check_the_column_is_an_error(fake_capacita_runner: Path,
                                                             monkeypatch: pytest.MonkeyPatch, mode, message):
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(RunnerError, match=f"線路方向.pik で柱の断面照査ができません: .*{message}"):
        check_column(WDJ, "線路方向.pik", PIK, fake_capacita_runner, SECTIONS)


def test_a_runner_that_cannot_start_is_an_error(tmp_path: Path):
    runner = tmp_path / "runner.exe"
    runner.write_bytes(b"not a program")
    with pytest.raises(RunnerError, match="runner を起動できません"):
        check_column(WDJ, "線路方向.pik", PIK, runner, SECTIONS)


def test_a_runner_that_does_not_finish_is_an_error(fake_capacita_runner: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(capacita.subprocess, "run", _timeout)
    with pytest.raises(RunnerError, match="秒で終わりませんでした"):
        check_column(WDJ, "線路方向.pik", PIK, fake_capacita_runner, SECTIONS, timeout=1)


def _timeout(*args, **kwargs):
    raise capacita.subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))


def test_the_stand_in_checks_a_footing_wdj_without_a_pickup(fake_capacita_runner: Path):
    """Decision 60: run-rc without --pickup (the WDJ holds the forces); result.json and report.pdf come back, with the
    six sections of the footing check in order (the real runner's page counts: 1, 2, 2, 1, 2, 3)."""
    checked = check_section(FOOTING_WDJ, "線路方向フーチング.wdj", fake_capacita_runner, FOOTING_SECTIONS)
    assert checked.engine_version == "fake-1"
    assert [section.id for section in checked.sections] == list(FOOTING_SECTIONS)
    assert [(section.first, section.last) for section in checked.sections] == [(1, 1), (2, 3), (4, 5), (6, 6), (7, 8),
                                                                                (9, 11)]
    assert checked.skipped == ()
    pages = texts(checked.pdf)
    digest = hashlib.sha256(FOOTING_WDJ).hexdigest()[:16]
    assert pages[0] == f"FAKE CAPACITA bending_safety_destruction 1/1 {digest}"
    assert pages[7] == f"FAKE CAPACITA shear_restorability_eq 2/2 {digest}"
    assert checked.section("shear_restorability_eq") == (7, 8)
    assert {section: len(texts(content)) for section, content in checked.pages.items()} == {
        "bending_safety_destruction": 1, "shear_safety_destruction": 2, "bending_durability": 2,
        "bending_restorability_eq": 1, "shear_restorability_eq": 2, "bending_rebar_amount": 3}
    with pytest.raises(RunnerError, match="計算書の節が違います"):
        check_section(FOOTING_WDJ, "線路方向フーチング.wdj", fake_capacita_runner, FOOTING_SECTIONS[:4])


@pytest.mark.parametrize("mode,message", [
    ("fail", "calculation_failed: RcDanが計算を完了できませんでした。"),
    ("exit", "JSON ではありません"), ("text", "JSON ではありません"), ("list", "オブジェクトではありません"),
    ("protocol", "やり取りの版が違います"), ("engine", "やり取りの版が違います"), ("version", "engineVersion"),
    ("artifacts", "成果物が計算結果・計算書の2つではありません"),
    ("extra", "出力先のファイルが成果物の一覧と一致しません"),
    ("sections", "計算書の節（reportSections）がありません"), ("order", "計算書の節が違います"),
    ("gap", "計算書の節のページが PDF の"), ("hole", "計算書の節のページが PDF の"), ("broken", "計算書の PDF を読めません"),
])
def test_a_runner_that_does_not_check_the_footing_is_an_error(fake_capacita_runner: Path,
                                                              monkeypatch: pytest.MonkeyPatch, mode, message):
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(RunnerError, match=f"線路方向フーチング.wdj で断面照査ができません: .*{message}"):
        check_section(FOOTING_WDJ, "線路方向フーチング.wdj", fake_capacita_runner, FOOTING_SECTIONS)


def _footing_wdj() -> bytes:
    """The 線路方向 footing WDJ of current.json made sandy with the sample's bars, the sample's reactions and the
    stand-in's step table (as tests/calc/footing_support.py builds it)."""
    from copy import deepcopy

    from webpier.calc import foundation_check as fc
    from webpier.calc import footing
    from webpier.calc.footing_check import calculate_footing_check
    from webpier.calc.foundation import calculate_foundation
    from webpier.calc.longitudinal import calculate_longitudinal
    from webpier.calc.reaction import calculate_reaction
    from webpier.export.capacita.footing_wdj import build_footing_wdj, write_footing_wdj
    from webpier.inputs import parse_input

    root = Path(__file__).parents[2]
    data = json.loads((root / "tests" / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
    data["地盤データ"]["層"][1]["土質区分"] = "砂質土"
    data["地盤データ"]["層"][0]["単位体積重量"]["水中"] = 9.0

    def bars(diameter=None, pitch=None, cover_mode="自動", center=None):
        return {"diameter_mm": diameter, "pitch_mm": pitch, "cover_mode": cover_mode, "center_mm": center,
                "inner_layers": []}

    def stirrup():
        return {"diameter_mm": 16, "pitch_mm": 250, "distribution_mode": "密度", "width_pitch_mm": None,
                "density_per_m": 2}

    data["鉄筋"]["フーチング"] = {
        "materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
        "pure_cover_mm": None,
        "faces": {"上": {"outer_direction": "線路", "線路": bars(), "直角": bars()},
                  "下": {"outer_direction": "線路", "線路": bars(25, 125, "指定", 100),
                         "直角": bars(29, 125, "指定", 127)}},
        "stirrups": {"線路": stirrup(), "直角": stirrup()}}
    pier = parse_input(deepcopy(data))
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    basis = footing.prepare(pier, foundation, calculate_longitudinal(pier, foundation, reaction), footing.LONGITUDINAL)
    actions = {"safety_moment": (21870.77, 495.01, 5460.42), "safety_shear": (22585.12, 473.43, 4767.98),
               "short_term": (19505.93, 300.0, 3327.13), "long_term": (18049.95, 240.0, 3056.25)}
    reactions = {}
    for number, (key, spec) in enumerate(zip(actions, footing.COLUMNS), 11):
        vd, hd, md = actions[key]
        extreme = fc.SupportReaction(number, hd, -vd, md)
        reactions[(basis.pickups[key], spec.focus.value)] = (extreme, extreme)
    steps = tuple(footing.FoundationStep(0, "Case1", 7, number, v, h, m, 3236.74, 3296.9, rvd, 54120.2, 0.081)
                  for number, v, h, m, rvd in ((1, 16825.97, 0.0, 580.25, 543358.71),
                                               (2, 16825.97, -5747.86, 52784.78, 22069.94),
                                               (3, 16825.97, -5901.07, 54168.43, 16655.87),
                                               (4, 16825.97, -5949.26, 54514.06, 16655.87)))
    check = calculate_footing_check(pier, footing.complete(basis, reactions, steps))
    return write_footing_wdj(build_footing_wdj(check))


def test_the_real_runner_checks_the_footing_of_the_sample_bars(real_capacita_runner: Path):
    """The WDJ of calc.footing_check / export.capacita.footing_wdj on the real runner (2026-10-21: six sections)."""
    wdj = _footing_wdj()
    checked = check_section(wdj, "線路方向フーチング.wdj", real_capacita_runner, FOOTING_SECTIONS)
    assert [section.id for section in checked.sections] == list(FOOTING_SECTIONS)
    assert checked.skipped == ()
    first = texts(checked.pdf)[0]
    assert "フーチング" in first and "線路方向" in first and "下側" in first and "D25-8" in first


def test_the_real_runner_checks_the_example2_column(real_capacita_runner: Path):
    """The real Capacita on the WDJ of the Example2 input and the sample PIK of 08_線路 (FEMPython's layout: member 3
    is the column, its JTAN the column bottom); skipped without a runner set up in .env."""
    checked = _real(real_capacita_runner, "08_線路", "線路方向.pik", transverse=False)
    assert [section.id for section in checked.sections] == list(SECTIONS) and checked.skipped == ()
    assert len(texts(checked.pdf)) == checked.sections[-1].last
    completed_document = json.loads(checked.wdj.decode("utf-8"))
    assert completed_document["pickup_filename"] == "線路方向.pik" and completed_document["pickup_data"]


def test_the_real_runner_skips_the_zero_force_checks_across_the_track(real_capacita_runner: Path):
    """Across the track the permanent actions are symmetric: the real Capacita skips the serviceability and the
    shear durability checks with WD-1914 and WD-1919 (column_section_check_09.json, skipped_by_capacita)."""
    checked = _real(real_capacita_runner, "09_直角", "線路直角方向.pik", transverse=True)
    sample = json.loads((Path(__file__).parents[1] / "fixtures" / "example2" / "column_section_check_09.json")
                        .read_text(encoding="utf-8"))
    assert sorted(checked.skipped) == sorted(sample["acceptance"]["skipped_by_capacita"])
    assert [section.id for section in checked.sections] == [name for name in SECTIONS if name not in checked.skipped]


def _real(runner: Path, sample: str, pik_name: str, *, transverse: bool) -> capacita.ColumnCheckPages:
    from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check
    from webpier.calc.foundation import calculate_foundation
    from webpier.calc.longitudinal import calculate_longitudinal
    from webpier.calc.reaction import calculate_reaction
    from webpier.calc.transverse import calculate_transverse
    from webpier.export.capacita import build_wdj, point_index, write_wdj
    from webpier.inputs import parse_input

    root = Path(__file__).parents[2]
    pier = parse_input(json.loads((root / "tests" / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8")))
    reaction, foundation = calculate_reaction(pier), calculate_foundation(pier)
    check = (calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE) if transverse
             else calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL))
    pik = (root / ".claude" / "docs" / "Example橋脚2" / sample / "frameWebForJS.pik").read_bytes()
    return check_column(write_wdj(build_wdj(check, point_index(pik, check.member))), pik_name, pik, runner,
                        check.sections)
