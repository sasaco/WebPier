"""The command line: options from the registry, and an exit code for every error the user can fix."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pipeline_support import CURRENT, Recorder, copy_input, fake_registry
from webpier.core.errors import InputError
from webpier.pipeline import cli, generate
from webpier.pipeline.generate import GenerationError
from webpier.pipeline.publication import RecoveryError
from webpier.pipeline.stages import (FRAME_ANALYSIS, NONLINEAR_ANALYSIS, STAGES, FrameAnalysis, NonlinearAnalysis,
                                     Registry, StageSpec)

ROOT = Path(__file__).parents[2]


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "0" * 64})
    return fake_registry(Recorder())


def run(tmp_path, registry, *arguments):
    source = copy_input(tmp_path / "pre")
    return cli.main(["--input", str(source), "--output-dir", str(tmp_path / "output"), *arguments],
                    registry=registry)


def test_all_is_the_default_and_every_published_file_is_listed(tmp_path, registry, capsys):
    assert run(tmp_path, registry) == 0
    printed = capsys.readouterr().out.splitlines()
    output, post = (tmp_path / "output").resolve(), (tmp_path / "post").resolve()
    assert printed == [
        f"A 計算書: {output / 'A_基礎.pdf'}", f"A 計算結果: {output / 'A_基礎.json'}",
        f"B 計算書: {output / 'B_荷重.pdf'}", f"B 計算結果: {output / 'B_荷重.json'}",
        f"C 計算書: {output / 'C_地震.pdf'}", f"C 計算結果: {output / 'C_地震.json'}",
        f"B frameweb入力: {post / 'frame.json'}", f"C jrsnap入力: {post / 'model.ndu'}",
        f"B frameweb付帯JSON: {post / 'frame.json.provenance.json'}",
        f"C jrsnap付帯JSON: {post / 'model.ndu.provenance.json'}"]


def test_post_is_a_sibling_of_the_output_directory_unless_given(tmp_path, registry):
    assert run(tmp_path, registry, "--stage", "B", "--post-dir", str(tmp_path / "elsewhere")) == 0
    assert (tmp_path / "elsewhere" / "frame.json").is_file() and not (tmp_path / "post").exists()


def test_jrsnap_is_written_without_a_flag(tmp_path, registry):
    assert run(tmp_path, registry, "--stage", "C") == 0
    assert (tmp_path / "post" / "model.ndu").read_bytes() == b"NDU C\r\n"


def test_there_is_no_jrsnap_flag(capsys):
    """Decision 42: the NDU is an ordinary export, so --jrsnap is an unknown argument."""
    with pytest.raises(SystemExit) as exit_info:
        cli.parser(STAGES).parse_args(["--jrsnap"])
    assert exit_info.value.code == 2
    assert "unrecognized arguments: --jrsnap" in capsys.readouterr().err


def analyzing(recorder: Recorder) -> Registry:
    """The fake registry with D, an opt-in stage that analyzes B's FrameWeb file (decision 46)."""
    stages = fake_registry(recorder).stages
    return Registry((*stages, StageSpec("D", "D_照査", ("B",), opt_in=FRAME_ANALYSIS, frame_analysis=FrameAnalysis(
        "B", "frameweb", (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))))))


def test_frame_analysis_adds_the_opt_in_stages_to_all(tmp_path, registry, capsys):
    stages = analyzing(Recorder())
    assert run(tmp_path, stages) == 0
    assert "D " not in capsys.readouterr().out
    assert run(tmp_path / "again", stages, "--frame-analysis") == 0
    printed = capsys.readouterr().out.splitlines()
    post = (tmp_path / "again" / "post").resolve()
    assert [line for line in printed if line.startswith("D ")] == [
        f"D pik解析結果: {post / 'frame.pik'}", f"D displacement解析結果: {post / 'frame_変位量.csv'}",
        f"D reaction解析結果: {post / 'frame_反力.csv'}", f"D pik付帯JSON: {post / 'frame.pik.provenance.json'}",
        f"D displacement付帯JSON: {post / 'frame_変位量.csv.provenance.json'}",
        f"D reaction付帯JSON: {post / 'frame_反力.csv.provenance.json'}"]
    assert f"B frameweb入力: {post / 'frame.json'}" in printed


def test_frame_analysis_with_one_stage_is_exit_code_2(tmp_path, registry, capsys):
    assert run(tmp_path, analyzing(Recorder()), "--stage", "B", "--frame-analysis") == 2
    assert "--frame-analysis は --stage all と使います（選択式の段階 D は --stage で直接選べます）" in capsys.readouterr().err
    assert not (tmp_path / "output").exists()


def test_the_analysis_options_name_their_opt_in_stages(capsys):
    with pytest.raises(SystemExit):
        cli.parser(STAGES).parse_args(["--help"])
    help_text = capsys.readouterr().out
    assert "0611・0612・0621・0622" in help_text and "（0711・0721）" in help_text
    arguments = cli.parser(STAGES).parse_args([])
    assert (arguments.frame_analysis, arguments.nonlinear_analysis) == (False, False)


def solving(recorder: Recorder) -> Registry:
    """The fake registry with E, an opt-in stage that has JRSNAP analyze C's NDU (decision 47)."""
    stages = fake_registry(recorder).stages
    return Registry((*stages, StageSpec("E", "E_解析", ("C",), opt_in=NONLINEAR_ANALYSIS,
                                        nonlinear_analysis=NonlinearAnalysis("C", "jrsnap", "jrsnap", "model_JRSNAP"))))


def test_nonlinear_analysis_adds_its_opt_in_stages_to_all(tmp_path, registry, capsys, monkeypatch):
    stages = solving(Recorder())
    assert run(tmp_path, stages) == 0
    assert "E " not in capsys.readouterr().out
    assert run(tmp_path / "again", stages, "--nonlinear-analysis") == 0
    post = (tmp_path / "again" / "post").resolve()
    assert [line for line in capsys.readouterr().out.splitlines() if line.startswith("E ")] == [
        f"E jrsnap解析結果: {post / 'model_JRSNAP'}", f"E jrsnap付帯JSON: {post / 'model_JRSNAP.provenance.json'}"]
    assert run(tmp_path / "one", stages, "--stage", "C", "--nonlinear-analysis") == 2
    assert "--nonlinear-analysis は --stage all と使います（選択式の段階 E は" in capsys.readouterr().err


def test_the_stage_choices_come_from_the_registry(capsys):
    plain = Registry((StageSpec("A", "A_x", (), lambda p, r: 0, lambda r, p, path, pages: path),))
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--stage", "B"], registry=plain)
    assert exit_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_default_paths_are_the_project_input_and_output():
    arguments = cli.parser(Registry((StageSpec("A", "A_x", (), lambda p, r: 0, lambda r, p, path, pages: path),))
                           ).parse_args([])
    assert (arguments.input, arguments.output_dir, arguments.post_dir, arguments.stage, arguments.overwrite) == (
        ROOT / "pre" / "input.json", ROOT / "output", None, "all", False)
    assert cli.post_dir(ROOT / "output", None) == (ROOT / "post").resolve()


def test_an_input_error_is_a_message_and_exit_code_2(tmp_path, registry, capsys):
    source = copy_input(tmp_path / "pre")
    source.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    assert cli.main(["--input", str(source), "--output-dir", str(tmp_path / "output")], registry=registry) == 2
    assert capsys.readouterr().err == "エラー: JSONのキーが重複しています: a\n"


def test_existing_outputs_without_overwrite_are_exit_code_2(tmp_path, registry, capsys):
    assert run(tmp_path, registry, "--stage", "A") == 0
    assert run(tmp_path, registry, "--stage", "A") == 2
    assert "--overwrite" in capsys.readouterr().err


@pytest.mark.parametrize("error,code", [
    (InputError("bad"), 2), (GenerationError("changed"), 2), (PermissionError("locked"), 2),
    (RecoveryError("backups kept at X"), 3)])
def test_errors_the_user_can_act_on_are_messages(tmp_path, registry, monkeypatch, capsys, error, code):
    def fail(options, *, registry):
        raise error
    monkeypatch.setattr(cli, "generate", fail)
    assert run(tmp_path, registry) == code
    message = capsys.readouterr().err
    assert message.startswith("復旧が必要です: " if code == 3 else "エラー: ") and str(error) in message


def test_anything_else_is_a_bug_with_a_traceback(tmp_path, registry, monkeypatch):
    def fail(options, *, registry):
        raise KeyError("bug")
    monkeypatch.setattr(cli, "generate", fail)
    with pytest.raises(KeyError):
        run(tmp_path, registry)


def test_python_m_webpier_runs_the_real_pipeline(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "webpier", "--input", str(CURRENT), "--output-dir",
         str(tmp_path / "output"), "--stage", "0500"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    assert sorted(path.name for path in (tmp_path / "output").iterdir()) == ["0500_直接基礎.json", "0500_直接基礎.pdf"]
    assert "0500 計算書" in completed.stdout
