"""The headless runner (decision 61): one protocol v1 envelope on stdout for each command, the generation the CLI
makes under output/ and post/, the runners of the environment only, the error codes, and the contract and the input
schema derived from the registry and the field table."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline_support import CURRENT, Recorder, copy_input, fake_registry, tree
from webpier.core.errors import InputError
from webpier.core.integrity import sha256
from webpier.inputs.fields import FIELDS
from webpier.inputs.parse import TOP_KEYS
from webpier.pipeline import fempython, generate, headless, jrsnap
from webpier.pipeline.fempython import RunnerError
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.publication import RecoveryError
from webpier.pipeline.stages import STAGES

ROOT = Path(__file__).parents[2]
ENVELOPE_KEYS = ["protocolVersion", "engine", "engineVersion", "readiness", "ok", "executionStatus",
                 "engineeringStatus", "summary", "messages", "artifacts", "errors"]


def call(capsys, *arguments, registry=STAGES) -> tuple[int, dict]:
    code = headless.main([str(argument) for argument in arguments], registry=registry)
    out = capsys.readouterr().out
    envelope = json.loads(out)  # the whole of stdout is one JSON document
    assert list(envelope) == ENVELOPE_KEYS
    assert (envelope["protocolVersion"], envelope["engine"], envelope["readiness"]) == (1, "webpier", "experimental")
    assert envelope["ok"] == (code == 0) and envelope["executionStatus"] == ("success" if code == 0 else "failed")
    return code, envelope


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "0" * 64})
    recorder = Recorder()
    return recorder, fake_registry(recorder)


def test_run_publishes_the_generation_under_output_and_post(tmp_path: Path, capsys, fake):
    source = copy_input(tmp_path / "pre")
    code, envelope = call(capsys, "run", "--input", source, "--output-dir", tmp_path / "out", "--stage", "B",
                          registry=fake[1])
    assert code == 0 and envelope["errors"] == [] and envelope["messages"] == []
    files = tree(tmp_path / "out")
    assert [(item["kind"], item["relativePath"], item["mediaType"]) for item in envelope["artifacts"]] == [
        ("B-pdf", "output/B_荷重.pdf", "application/pdf"), ("B-json", "output/B_荷重.json", "application/json"),
        ("B-frameweb", "post/frame.json", "application/json"),
        ("B-frameweb-provenance", "post/frame.json.provenance.json", "application/json")]
    assert sorted(files) == sorted(item["relativePath"] for item in envelope["artifacts"])
    for item in envelope["artifacts"]:
        data = files[item["relativePath"]]
        assert (item["bytes"], item["sha256"]) == (len(data), sha256(data))
    summary = envelope["summary"]
    assert summary["command"] == "run" and (summary["stage"], summary["frameAnalysis"]) == ("B", False)
    assert summary["stages"] == [{"id": "B", "stem": "B_荷重", "hasReport": True, "engineeringStatus": "not_evaluated"}]
    assert envelope["engineeringStatus"] == summary["engineeringStatus"] == "not_evaluated"
    assert summary["runners"] == []
    assert summary["input"] == {"file": "input.json", "sha256": sha256(source.read_bytes())}
    assert summary["implementationSha256"] == json.loads(files["output/B_荷重.json"])["implementation_sha256"]


def test_what_a_library_prints_goes_to_stderr(tmp_path: Path, capsys, fake):
    recorder, registry = fake
    recorder.hooks[("render", "A")] = lambda: print("a library prints")
    code = headless.main(["run", "--input", str(copy_input(tmp_path / "pre")), "--output-dir", str(tmp_path / "out"),
                          "--stage", "A"], registry=registry)
    captured = capsys.readouterr()
    assert code == 0 and json.loads(captured.out)["ok"] and "a library prints" in captured.err


def test_run_gives_the_bytes_of_the_cli(tmp_path: Path, capsys):
    """The same generation as python -m webpier: the real 0500 report and result, byte for byte."""
    source = copy_input(tmp_path / "pre")
    assert call(capsys, "run", "--input", source, "--output-dir", tmp_path / "out", "--stage", "0500")[0] == 0
    generate.generate(GenerationOptions(source, tmp_path / "cli" / "output", tmp_path / "cli" / "post", stage="0500"))
    assert tree(tmp_path / "out") == tree(tmp_path / "cli")


@pytest.mark.parametrize("arguments,message", [
    ([], "the following arguments are required: command"), (["draw"], "invalid choice"),
    (["run", "--input", "x.json"], "--output-dir"), (["validate", "--output-dir", "x"], "--input"),
    (["validate", "--input", "x.json", "--frame-analysis", "yes"], "true か false が必要です"),
    (["run", "--input", "x.json", "--output-dir", "x", "--stage", "9999"], "invalid choice")])
def test_a_wrong_command_line_is_an_invalid_argument(capsys, arguments, message):
    code, envelope = call(capsys, *arguments)
    assert code == 2 and envelope["errors"][0]["code"] == "INVALID_ARGUMENT"
    assert message in envelope["errors"][0]["message"] and envelope["summary"] is None


def test_the_output_folder_must_be_empty(tmp_path: Path, capsys, fake):
    source = copy_input(tmp_path / "pre")
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "old.txt").write_text("old", encoding="utf-8")
    (tmp_path / "file").write_text("", encoding="utf-8")
    for folder in ("used", "file"):
        code, envelope = call(capsys, "run", "--input", source, "--output-dir", tmp_path / folder, registry=fake[1])
        assert code == 2 and envelope["errors"][0]["code"] == "INVALID_ARGUMENT"
        assert "空のフォルダー" in envelope["errors"][0]["message"]


def test_an_input_error_names_the_input_path(tmp_path: Path, capsys, fake):
    data = json.loads(CURRENT.read_text(encoding="utf-8"))
    data["下部構造"]["寸法"]["側面"]["B1"] = -1
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for command in ("run", "validate"):
        code, envelope = call(capsys, command, "--input", source, "--output-dir", tmp_path / command, registry=fake[1])
        assert code == 2 and envelope["artifacts"] == []
        (error,), (message,) = envelope["errors"], envelope["messages"]
        assert (error["category"], error["code"], error["path"]) == ("input", "INPUT_ERROR", "下部構造.寸法.側面.B1")
        assert (message["level"], message["code"], message["path"]) == ("error", "INPUT_ERROR", "下部構造.寸法.側面.B1")
        assert message["text"] == error["message"]
        assert envelope["summary"]["command"] == command
    assert not (tmp_path / "run").exists()


def test_a_switch_with_one_stage_is_an_input_error_without_a_path(tmp_path: Path, capsys, fake):
    code, envelope = call(capsys, "run", "--input", copy_input(tmp_path / "pre"), "--output-dir", tmp_path / "out",
                          "--stage", "B", "--frame-analysis", "true", registry=fake[1])
    assert code == 2 and envelope["errors"][0]["code"] == "INPUT_ERROR" and "path" not in envelope["errors"][0]
    assert envelope["messages"][0]["path"] is None


@pytest.mark.parametrize("message,path", [
    ("上部工反力.起点側.B支点[0].支承位置: はりの張出しにあります", "上部工反力.起点側.B支点[0].支承位置"),
    ("入力項目がありません: 鉄筋.柱.main_rows[2].layer", "鉄筋.柱.main_rows[2].layer"),
    ("入力項目がありません: jrsnap_transverse", "jrsnap_transverse"),
    ("柱の断面照査.ε'csd: 値が必要です", "柱の断面照査.ε'csd"),
    ("FrameWeb入力: 全体: 不正です", None), ("0600 本体: 面積が0です", None), ("計算段階が不正です: 9", None),
    (": 空", None)])
def test_the_input_path_of_an_error_message(message, path):
    assert headless.input_path(message) == path


def test_a_runner_set_only_in_the_env_file_is_unavailable(tmp_path: Path, capsys, monkeypatch, fake_fempython_runner):
    """Decision 61: the headless runner reads no .env file, and names every missing runner."""
    env = tmp_path / ".env"
    env.write_text(f"{fempython.RUNNER_KEY}='{fake_fempython_runner}'\n{jrsnap.RUNNER_KEY}='{fake_fempython_runner}'\n",
                   encoding="utf-8")
    for module in (fempython, jrsnap):
        monkeypatch.setattr(module, "ENV_FILE", env)
        monkeypatch.delenv(module.RUNNER_KEY)
    source = copy_input(tmp_path / "pre")
    code, envelope = call(capsys, "run", "--input", source, "--output-dir", tmp_path / "out")
    assert code == 2 and not (tmp_path / "out").exists()
    (error,) = envelope["errors"]
    assert (error["category"], error["code"]) == ("engine_unavailable", "RUNNER_UNAVAILABLE")
    assert "fempython（STRUCTURAL_MCP_FEMPYTHON_RUNNER）・jrsnap（STRUCTURAL_MCP_JRSNAP_RUNNER）" in error["message"]
    assert envelope["summary"]["missingRunners"] == [
        {"engine": "fempython", "environmentVariable": "STRUCTURAL_MCP_FEMPYTHON_RUNNER"},
        {"engine": "jrsnap", "environmentVariable": "STRUCTURAL_MCP_JRSNAP_RUNNER"}]
    code, envelope = call(capsys, "validate", "--input", source, "--stage", "all")
    assert code == 0 and envelope["summary"]["requiredRunners"] == [
        {"engine": "fempython", "environmentVariable": "STRUCTURAL_MCP_FEMPYTHON_RUNNER", "available": False},
        {"engine": "jrsnap", "environmentVariable": "STRUCTURAL_MCP_JRSNAP_RUNNER", "available": False}]


def failing(exc: BaseException):
    def generate_(options, *, registry):
        raise exc
    return generate_


def caused(exc: Exception, cause: Exception) -> Exception:
    exc.__cause__ = cause
    return exc


@pytest.mark.parametrize("exc,code,category,exit_code", [
    (caused(GenerationError("runner が失敗しました"), RunnerError("x")), "ENGINE_FAILED", "execution", 2),
    (GenerationError("帳票を作成できません"), "GENERATION_FAILED", "execution", 2),
    (InputError("下部構造.寸法.高さ.H4: 長い必要があります"), "INPUT_ERROR", "input", 2),
    (PermissionError("読取専用です"), "IO_ERROR", "file_system", 2),
    (RecoveryError("退避を戻せません"), "RECOVERY_REQUIRED", "file_system", 3)])
def test_a_failed_generation_is_reported_by_its_kind(tmp_path: Path, capsys, monkeypatch, fake, exc, code, category,
                                                     exit_code):
    monkeypatch.setattr(headless, "generate", failing(exc))
    result, envelope = call(capsys, "run", "--input", copy_input(tmp_path / "pre"), "--output-dir", tmp_path / "out",
                            registry=fake[1])
    assert result == exit_code and envelope["artifacts"] == []
    assert (envelope["errors"][0]["code"], envelope["errors"][0]["category"]) == (code, category)
    assert envelope["errors"][0]["message"] == str(exc)


def test_validate_checks_the_input_without_writing_or_calling_a_runner(tmp_path: Path, capsys, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("validate staged a generation")
    for name in ("prepare", "_runner_paths", "_draw_figures"):
        monkeypatch.setattr(generate, name, never)
    source = copy_input(tmp_path / "pre")
    before = sorted(path.name for path in tmp_path.rglob("*"))
    code, envelope = call(capsys, "validate", "--input", source, "--stage", "0710")
    assert code == 0 and envelope["artifacts"] == [] and envelope["engineeringStatus"] == "not_evaluated"
    assert sorted(path.name for path in tmp_path.rglob("*")) == before
    assert envelope["summary"] == {
        "command": "validate", "stage": "0710", "frameAnalysis": False, "nonlinearAnalysis": False,
        "stages": ["0710"], "requiredRunners": [
            {"engine": "jrsnap", "environmentVariable": "STRUCTURAL_MCP_JRSNAP_RUNNER", "available": True}]}


def test_validate_checks_what_an_export_reads(tmp_path: Path, capsys):
    """The Aggre-SE project's input (耐震設計条件) is checked before any analysis (decision 49), and so by validate."""
    data = json.loads(CURRENT.read_text(encoding="utf-8"))
    data["耐震設計条件"]["地域別"] = None
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert call(capsys, "validate", "--input", source, "--stage", "0710")[0] == 0
    code, envelope = call(capsys, "validate", "--input", source, "--stage", "0711")
    assert code == 2 and envelope["errors"][0]["path"] == "耐震設計条件.地域別"


def test_validate_reports_a_missing_input_file(tmp_path: Path, capsys):
    code, envelope = call(capsys, "validate", "--input", tmp_path / "missing.json")
    assert code == 2 and envelope["errors"][0]["code"] == "IO_ERROR"


def test_a_frame_analysis_reports_its_runner_and_the_foundation_check(tmp_path: Path, capsys):
    code, envelope = call(capsys, "run", "--input", copy_input(tmp_path / "pre"), "--output-dir", tmp_path / "out",
                          "--stage", "0612")
    assert code == 0
    summary = envelope["summary"]
    status = json.loads((tmp_path / "out" / "output" / "0612_線路方向基礎.json").read_text(encoding="utf-8"))
    assert summary["stages"] == [{"id": "0612", "stem": "0612_線路方向基礎", "hasReport": True,
                                  "engineeringStatus": status["result"]["engineering_status"]}]
    assert envelope["engineeringStatus"] == status["result"]["engineering_status"] in ("ok", "not_ok")
    (runner,) = summary["runners"]
    assert runner["engine"] == "fempython" and runner["engineVersions"] and all(runner["engineVersions"])
    assert [item["relativePath"] for item in envelope["artifacts"]] == [
        f"{artifact.directory}/{artifact.path.name}" for artifact in planned(GenerationOptions(
            Path("input.json"), Path("output"), Path("post"), stage="0612"))]
    assert {item["mediaType"] for item in envelope["artifacts"] if item["relativePath"].endswith(".csv")} == {
        "text/csv; charset=utf-8"}


def test_a_jrsnap_folder_is_listed_file_by_file(tmp_path: Path, capsys):
    code, envelope = call(capsys, "run", "--input", copy_input(tmp_path / "pre"), "--output-dir", tmp_path / "out",
                          "--stage", "0711")
    assert code == 0
    folder = tmp_path / "out" / "post" / "線路方向_JRSNAP"
    listed = [item for item in envelope["artifacts"] if item["kind"] == "0711-jrsnap"]
    assert [item["relativePath"] for item in listed] == [
        f"post/線路方向_JRSNAP/{path.name}" for path in sorted(folder.iterdir())]
    assert {item["mediaType"] for item in listed} == {"application/octet-stream"}
    kinds = {item["kind"]: item["mediaType"] for item in envelope["artifacts"]}
    assert kinds["0711-aggrese"] == "application/xml"
    assert kinds["0711-xlsx"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert [runner["engine"] for runner in envelope["summary"]["runners"]] == ["jrsnap", "aggrese"]
    assert all(runner["engineVersions"] for runner in envelope["summary"]["runners"])
    assert envelope["engineeringStatus"] == "not_evaluated"


def test_text_is_marked_utf_8_or_shift_jis():
    assert headless._media_type(Path("a.ndu"), "線路".encode("cp932"), False) == "text/plain; charset=shift_jis"
    assert headless._media_type(Path("a.pik"), "線路".encode("utf-8"), False) == "text/plain; charset=utf-8"
    assert headless._media_type(Path("a.CSV"), b"x", True) == "application/octet-stream"
    assert headless._media_type(Path("a.LOG"), b"x", False) == "application/octet-stream"


@pytest.mark.parametrize("statuses,whole", [([], "not_evaluated"), (["not_evaluated"], "not_evaluated"),
                                            (["not_evaluated", "ok"], "ok"), (["ok", "not_ok", "ok"], "not_ok")])
def test_the_whole_engineering_status(statuses, whole):
    assert headless.engineering_status(statuses) == whole


def test_the_contract_is_the_registry(capsys):
    code, envelope = call(capsys, "contract")
    contract = envelope["summary"]
    assert code == 0 and contract["command"] == "contract"
    assert [stage["id"] for stage in contract["stages"]] == list(STAGES.ids)
    assert contract["stages"][2] == {"id": "0610", "stem": "0610_線路方向荷重", "dependsOn": ["0500", "0600"],
                                     "optIn": [], "hasReport": True}
    assert contract["switches"] == [{"name": "frame_analysis", "flag": "--frame-analysis",
                                     "stages": ["0611", "0612", "0621", "0622", "0800", "0810", "0820"]},
                                    {"name": "nonlinear_analysis", "flag": "--nonlinear-analysis",
                                     "stages": ["0711", "0721", "0800", "0810", "0820", "0900", "0910"]}]
    assert [runner["engine"] for runner in contract["runners"]] == ["fempython", "jrsnap", "webdan2", "aggrese"]
    selections = {(item["stage"], item["frameAnalysis"], item["nonlinearAnalysis"]): item
                  for item in contract["selections"]}
    assert len(selections) == 4 + len(STAGES.ids)
    assert selections[("all", False, False)]["runners"] == ["fempython", "jrsnap"]
    assert selections[("0500", False, False)] == {
        "stage": "0500", "frameAnalysis": False, "nonlinearAnalysis": False, "stages": ["0500"], "runners": [],
        "files": [{"role": "0500.pdf", "path": "output/0500_直接基礎.pdf", "folder": False},
                  {"role": "0500.json", "path": "output/0500_直接基礎.json", "folder": False}]}
    assert selections[("0800", False, False)]["stages"] == ["0612", "0622", "0711", "0721", "0800"]
    assert selections[("0800", False, False)]["runners"] == ["fempython", "jrsnap", "aggrese"]
    folder = [item for item in selections[("all", True, True)]["files"] if item["folder"]]
    assert [item["path"] for item in folder] == ["post/線路方向_JRSNAP", "post/線路直角方向_JRSNAP"]


def conforms(value, schema: dict, path: str = "") -> list[str]:
    """The places where *value* breaks *schema*, for the keywords the input schema uses."""
    if "const" in schema:
        return [] if value == schema["const"] else [path]
    if "enum" in schema:
        return [] if value in schema["enum"] else [path]
    kinds = schema.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    names = {"object": dict, "array": list, "string": str, "null": type(None)}
    if kinds and not any(isinstance(value, names[kind]) if kind in names else
                         isinstance(value, (int, float)) and not isinstance(value, bool)
                         and (kind == "number" or float(value).is_integer()) for kind in kinds):
        return [path]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        broken = [f"{path}.{key}" for key in value if key not in properties and schema.get("additionalProperties") is False]
        return broken + [place for key, item in value.items() if key in properties
                         for place in conforms(item, properties[key], f"{path}.{key}")]
    if isinstance(value, list):
        return [place for index, item in enumerate(value) for place in conforms(item, schema["items"], f"{path}[{index}]")]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        low, high, above = schema.get("minimum"), schema.get("maximum"), schema.get("exclusiveMinimum")
        if (low is not None and value < low) or (high is not None and value > high) or (above is not None and value <= above):
            return [path]
    return []


@pytest.fixture(scope="module")
def schema() -> dict:
    return headless.input_schema()


@pytest.mark.parametrize("document", [CURRENT, ROOT / "pre" / "input.json"])
def test_the_inputs_conform_to_the_schema(schema, document):
    assert conforms(json.loads(document.read_text(encoding="utf-8")), schema) == []


def test_the_schema_has_every_field_and_the_top_keys(schema):
    assert list(schema["properties"]) == ["schema_version", "出典", *(key for key in TOP_KEYS if key not in (
        "schema_version", "出典"))]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for pattern in FIELDS:
        node = schema
        for part in headless._parts(pattern):
            name = part.removesuffix("[*]")
            node = node["properties"][name]
            if part.endswith("[*]"):
                node = node["items"]
        assert "properties" not in node, pattern


def test_the_schema_leaves(schema):
    properties = schema["properties"]
    side = properties["下部構造"]["properties"]["寸法"]["properties"]["側面"]["properties"]
    assert side["B1"] == {"type": "number", "x-webpier-unit": "m", "x-webpier-digits": 3, "exclusiveMinimum": 0}
    assert side["B2"]["minimum"] == 0
    position = properties["上部工反力"]["properties"]["起点側"]["properties"]["B支点"]["items"]["properties"]["支承位置"]
    assert "minimum" not in position and "exclusiveMinimum" not in position
    train = properties["上部構造"]["properties"]["列車"]["properties"]
    assert train["編成数"] == {"type": "integer", "minimum": 1, "maximum": 200}
    assert None not in train["車両名"]["enum"] and "1両の長さ" in train
    seismic = properties["耐震設計条件"]["properties"]["地域別"]["enum"]
    assert seismic[-1] is None
    shares = properties["上部工反力"]["properties"]["終点側"]["properties"]["C支点"]["items"]["properties"]["列車分担"]
    assert shares["properties"]["L3"] == {"type": "null", "description": "3線以上は未対応です"}
    assert properties["下部構造"]["properties"]["杭種"]["x-webpier-reserved"] is True
    angle = properties["地盤データ"]["properties"]["層"]["items"]["properties"]["内部摩擦角_φd"]
    assert angle["type"] == ["number", "null"] and angle["x-webpier-limit"] == "90度未満が必要です"
    repetitions = properties["片持ち梁の照査"]["properties"]["疲労"]["properties"]["等価繰返し回数"]["properties"]
    assert list(repetitions["A列車"]["properties"]) == ["k=0.06", "k=0.12"]
    assert properties["鉄筋"]["properties"]["version"] == {"const": 2}
    assert properties["schema_version"] == {"const": 2}
    for side, slots in (("起点側", "B支点"), ("終点側", "C支点")):  # an empty bearing slot is null
        array = properties["上部工反力"]["properties"][side]["properties"][slots]
        assert (array["items"]["type"], array["minItems"], array["maxItems"]) == (["object", "null"], 10, 10)
    assert properties["地盤データ"]["properties"]["層"]["items"]["type"] == "object"
    column = properties["鉄筋"]["properties"]["柱"]["properties"]
    assert column["side_rows"] == column["band_rows"] == {"type": "array", "maxItems": 0}
    assert column["manual_basis"]["type"] == ["object", "null"]
    assert column["column_hoops"]["type"] == "object"


def test_the_schema_command(capsys, schema):
    code, envelope = call(capsys, "schema")
    assert code == 0 and envelope["summary"] == {"command": "schema", "schema": schema}


def test_run_headless_py_in_a_minimal_environment(tmp_path: Path):
    """structural-mcp starts the script with the venv's python, a minimal environment and an unrelated folder."""
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "TEMP", "TMP") if key in os.environ}
    done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "run_headless.py"), "contract"], cwd=tmp_path,
                          env=environment, capture_output=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    envelope = json.loads(done.stdout.decode("utf-8"))
    assert envelope["ok"] and envelope["engineVersion"] == headless.engine_version()
