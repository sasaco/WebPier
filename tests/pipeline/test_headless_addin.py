"""``--addin`` end to end (decision 70): every stage with the test load model through the stand-in runners, the add-in's
provenance in the summary, every result JSON and every sidecar, and the errors of an add-in (ADDIN_ERROR) and of its
own input (INPUT_ERROR); an input with the train's values left in it (as P7's) is read without them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline_support import copy_input, footing_input, tree
from test_headless import call
from webpier.loadmodel import CONTRACT_VERSION
from webpier.pipeline import cli, headless
from webpier.pipeline.addin import MANIFEST
from webpier.pipeline.stages import STAGES

MINIMAL = Path(__file__).parents[1] / "fixtures" / "addin" / "minimal"
RECORD = {"name": "minimal", "version": "1.0.0", "contract": CONTRACT_VERSION,
          "provenance": {"source": "tests/fixtures/addin/minimal", "bearings": 6}}


def garbled_input(directory: Path) -> Path:
    """The input (with the sample's footing bars, which 0800 needs) with values the train path rejects left in the load
    model's items."""
    path = footing_input(directory)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["上部構造"]["列車"]["車両名"] = "トラム"
    document["上部構造"]["起点側"]["曲線半径"] = -1
    document["上部工反力"]["起点側"]["B支点"][0]["列車分担"]["L3"] = 1.0
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def generation(tmp_path_factory: pytest.TempPathFactory):
    """One generation of every stage, run as the runner's command without its stdout."""
    root = tmp_path_factory.mktemp("addin")
    arguments = headless.parser().parse_args([
        "run", "--input", str(garbled_input(root / "pre")), "--output-dir", str(root / "out"), "--stage", "all",
        "--frame-analysis", "true", "--nonlinear-analysis", "true", "--addin", str(MINIMAL)])
    code, envelope = headless._run(arguments, STAGES)
    return code, envelope, root / "out"


def test_every_stage_is_generated(generation):
    code, envelope, _ = generation
    assert code == 0, envelope["errors"]
    assert [stage["id"] for stage in envelope["summary"]["stages"]] == [
        "0500", "0600", "0610", "0611", "0612", "0620", "0621", "0622", "0710", "0711", "0720", "0721", "0800", "0810",
        "0820", "0900", "0910"]


def test_the_addin_is_recorded_alike_everywhere(generation):
    _, envelope, out = generation
    assert envelope["summary"]["addin"] == RECORD
    files = tree(out)
    results = [name for name in files if name.startswith("output/") and name.endswith(".json")]
    sidecars = [name for name in files if name.endswith(".provenance.json")]
    assert len(results) == 17 and len(sidecars) > 17  # a result JSON per stage, a sidecar per file under post/
    for name in (*results, *sidecars):
        assert json.loads(files[name])["addin"] == RECORD, name


def test_nothing_of_the_train_is_printed_and_the_load_model_is(generation):
    _, _, out = generation
    result = json.loads((out / "output" / "0610_線路方向荷重.json").read_text(encoding="utf-8"))["result"]
    assert [case["id"] for case in result["basic_cases"]] == ["D1", "D2", "WP_HIGH", "WP_NORMAL", "WP_LOW", "L", "BR",
                                                             "ZERO"]
    frameweb = json.loads((out / "post" / "線路方向.json").read_text(encoding="utf-8"))
    assert frameweb["pickup"]["4"]["name"] == "変動作用"


def test_the_cli_takes_the_addin(tmp_path: Path, capsys):
    source = garbled_input(tmp_path / "pre")
    code = cli.main(["--input", str(source), "--output-dir", str(tmp_path / "output"), "--stage", "0600",
                     "--addin", str(MINIMAL)])
    assert code == 0
    document = json.loads((tmp_path / "output" / "0600_上部工反力.json").read_text(encoding="utf-8"))
    assert document["addin"] == RECORD
    code = cli.main(["--input", str(source), "--output-dir", str(tmp_path / "other"), "--stage", "0600",
                     "--addin", str(tmp_path)])
    assert code == 2 and "アドインの宣言" in capsys.readouterr().err


def addin(folder: Path, *, contract: int = CONTRACT_VERSION, body: str = "") -> Path:
    folder.mkdir(parents=True)
    (folder / MANIFEST).write_text(f'name = "x"\nversion = "1"\ncontract = {contract}\nentry = "model:make"\n',
                                   encoding="utf-8")
    (folder / "model.py").write_text(body or "class M:\n    def calculate(self, context):\n        return None\n"
                                             "def make():\n    return M()\n", encoding="utf-8")
    return folder


@pytest.mark.parametrize("case,code,message", [
    ("version", "ADDIN_ERROR", "アドイン x の約束の版 2 は、この WebPier の約束の版 1 と違います"),
    ("missing", "ADDIN_ERROR", "アドインの宣言"),
    ("import", "ADDIN_ERROR", "アドイン x を読み込めません"),
    ("raises", "ADDIN_ERROR", "アドイン x の calculate が失敗しました: RuntimeError"),
    ("input", "INPUT_ERROR", "input.addin.json:車荷重[1]: 値が必要です"),
])
@pytest.mark.parametrize("command", ["run", "validate"])
def test_the_errors_of_an_add_in(tmp_path: Path, capsys, case, code, message, command):
    folder = tmp_path / "addin"
    if case == "version":
        addin(folder, contract=2)
    elif case == "missing":
        folder.mkdir()
    elif case == "import":
        addin(folder, body="import webpier.nothing\n")
    elif case == "raises":
        addin(folder, body="class M:\n    def calculate(self, context):\n        raise RuntimeError('x')\n"
                           "def make():\n    return M()\n")
    else:
        addin(folder, body="from webpier.loadmodel import LoadModelInputError\n"
                           "class M:\n    def calculate(self, context):\n"
                           "        raise LoadModelInputError('input.addin.json:車荷重[1]', '値が必要です')\n"
                           "def make():\n    return M()\n")
    arguments = [command, "--input", copy_input(tmp_path / "pre"), "--stage", "0610", "--addin", folder]
    if command == "run":
        arguments += ["--output-dir", tmp_path / "out"]
    exit_code, envelope = call(capsys, *arguments)
    assert exit_code == 2
    (error,) = envelope["errors"]
    assert error["code"] == code and message in error["message"]
    assert error["category"] == ("addin" if code == "ADDIN_ERROR" else "input")


def test_validate_contract_and_schema_with_an_add_in(tmp_path: Path, capsys):
    code, envelope = call(capsys, "validate", "--input", garbled_input(tmp_path / "pre"), "--stage", "0720",
                          "--addin", MINIMAL)
    assert code == 0 and envelope["summary"]["stages"][-1] == "0720"
    code, envelope = call(capsys, "contract", "--addin", MINIMAL)
    assert code == 0 and envelope["summary"]["addin"] == {"name": "minimal", "version": "1.0.0",
                                                         "contract": CONTRACT_VERSION}
    code, plain = call(capsys, "contract")
    assert "addin" not in plain["summary"] and plain["summary"]["stages"] == envelope["summary"]["stages"]
    code, envelope = call(capsys, "schema", "--addin", MINIMAL)
    schema = envelope["summary"]["schema"]
    structure = schema["properties"]["上部構造"]["properties"]
    assert structure["列車"]["x-webpier-load-model"] is True
    assert structure["起点側"]["properties"]["曲線半径"]["x-webpier-load-model"] is True
    assert "x-webpier-load-model" not in structure["起点側"]["properties"]["支承位置_f"]
    slot = schema["properties"]["上部工反力"]["properties"]["起点側"]["properties"]["B支点"]["items"]["properties"]
    assert slot["列車分担"]["x-webpier-load-model"] is True and slot["雪荷重_2年確率"]["x-webpier-load-model"] is True
    assert "x-webpier-load-model" not in slot["固定死荷重_D1"]
    code, envelope = call(capsys, "contract", "--addin", tmp_path)
    assert code == 2 and envelope["errors"][0]["code"] == "ADDIN_ERROR"
    code, envelope = call(capsys, "schema", "--addin", tmp_path)
    assert code == 2 and envelope["errors"][0]["code"] == "ADDIN_ERROR"
