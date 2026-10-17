"""Stage selection, provenance and atomic publication of all selected outputs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
from pypdf import PdfReader

from src import cli


PROJECT = Path(__file__).resolve().parents[1]
STEMS = ("0500_直接基礎", "0600_上部工反力", "0610_線路方向荷重", "0620_直角方向荷重", "0710_線路方向荷重", "0720_線路直角方向荷重")
NAMES = tuple(f"{stem}.{suffix}" for stem in STEMS for suffix in ("pdf", "json"))


@pytest.fixture
def data():
    return json.loads((PROJECT / "pre" / "input.json").read_text(encoding="utf-8"))


@pytest.fixture
def quick_reports(monkeypatch):
    # Rendering is replaced here; real runtime identity has dedicated tests.
    source = Path(cli.__file__).resolve()
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {source: cli.file_sha256(source)})
    def write_pdf(result, path):
        Path(path).write_bytes(b"new PDF")

    monkeypatch.setattr("src.report.render_report", write_pdf)
    monkeypatch.setattr("src.reaction_report.render_reaction_report", write_pdf)
    if importlib.util.find_spec("src.longitudinal_report"):
        monkeypatch.setattr("src.longitudinal_report.render_longitudinal_report", write_pdf)
    if importlib.util.find_spec("src.transverse_report"):
        monkeypatch.setattr("src.transverse_report.render_transverse_report", write_pdf)
    monkeypatch.setattr("src.seismic_longitudinal_report.render_seismic_longitudinal_report", write_pdf)
    monkeypatch.setattr("src.seismic_transverse_report.render_seismic_transverse_report", write_pdf)


def write_input(tmp_path, data):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
    return path


def test_all_stages_accept_signed_train_distributions_with_zero_total(tmp_path, data, quick_reports):
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        rows = data["上部工反力"][side][point]["支承"]
        for row in rows:
            row["列車分担"] = dict.fromkeys(("L1", "L2", "L3", "L4"), 0)
        rows[0]["列車分担"].update(L1=-0.25, L2=0.125, L3=-0.5, L4=0.25)
        rows[1]["列車分担"].update(L1=0.25, L2=-0.125, L3=0.5, L4=-0.25)
    path = write_input(tmp_path, data)
    output = tmp_path / "output"
    assert cli.main(["--stage", "all", "--input", str(path), "--output-dir", str(output)]) == 0
    assert {file.name for file in output.iterdir()} == set(NAMES) | {"post"}
    result = json.loads((output / "0600_上部工反力.json").read_text(encoding="utf-8"))
    assert result["dead_loads"]["track_totals"] == {"B": 0, "C": 0}
    assert result["input"]["dead"]["b"][0]["factors"] == [-0.25, 0.125, -0.5, 0.25]
    assert result["dead_loads"]["double_track_factors"]["B"][:2] == [-0.125, 0.125]


def test_default_all_publishes_reports_and_post_with_shared_input_hash(tmp_path, capsys):
    assert cli.main(["--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES) | {"post"}
    for name, required in zip(NAMES[::2], (
        ("地盤のモデル化", "鉛直地盤"), ("上部工反力", "荷重"),
        ("線路方向", "作用"), ("直角方向", "作用"),
        ("線路方向", "地震時"), ("線路直角方向", "地震時"),
    ), strict=True):
        pages = PdfReader(tmp_path / name).pages
        assert len(pages) > 0
        text = "\n".join(page.extract_text() for page in pages)
        assert all(token in text for token in required), name
    foundation = json.loads((tmp_path / NAMES[1]).read_text(encoding="utf-8"))
    reaction = json.loads((tmp_path / NAMES[3]).read_text(encoding="utf-8"))
    longitudinal = json.loads((tmp_path / NAMES[5]).read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256((PROJECT / "pre" / "input.json").read_bytes()).hexdigest()
    assert foundation["provenance"]["input_sha256"] == reaction["provenance"]["input_sha256"] == expected_hash
    assert longitudinal["provenance"]["input_sha256"] == expected_hash
    transverse = json.loads((tmp_path / NAMES[7]).read_text(encoding="utf-8"))
    assert transverse["provenance"]["input_sha256"] == expected_hash
    seismic = json.loads((tmp_path / NAMES[9]).read_text(encoding="utf-8"))
    assert seismic["provenance"]["input_sha256"] == expected_hash
    printed = capsys.readouterr().out
    assert all(stage in printed for stage in ("0500", "0600", "0610", "0620", "0710", "0720"))
    assert "注記" in printed


def test_fixed_baseline_cli_retains_independent_reaction_values(tmp_path, quick_reports):
    # Fixed historical input from fa27cca^; independent numerical expectations.
    source = PROJECT / "tests" / "fixtures" / "baseline_input.json"
    assert cli.main(["--stage", "0600", "--input", str(source), "--output-dir", str(tmp_path)]) == 0
    reaction = json.loads((tmp_path / NAMES[3]).read_text(encoding="utf-8"))
    assert reaction["moving_train"]["reactions"] == [512.2037353515625, 507.7962951660156, 633.1151123046875, 386.8848876953125]
    assert reaction["public_values"]["はり"]["N"] == 616.94


@pytest.mark.parametrize("stage,removed,selected", [("0500", ("上部構造", "上部工反力"), 0), ("0600", (), 1)])
def test_only_selected_stage_is_validated_and_published(tmp_path, data, quick_reports, stage, removed, selected):
    for key in removed:
        del data[key]
    if stage == "0600":
        wet = data["地盤データ"]["層"][0]["単位体積重量"]["湿潤"]
        data["地盤データ"] = {"層": [{"単位体積重量": {"湿潤": wet}}]}
    path = write_input(tmp_path, data)
    output = tmp_path / "output"
    output.mkdir()
    other_names = tuple(name for name in NAMES if name not in NAMES[2 * selected:2 * selected + 2])
    for name in other_names:
        (output / name).write_bytes(b"unselected old output")
    assert cli.main(["--stage", stage, "--input", str(path), "--output-dir", str(output)]) == 0
    for name in other_names:
        assert (output / name).read_bytes() == b"unselected old output"
    for name in NAMES[2 * selected:2 * selected + 2]:
        assert (output / name).is_file()


def test_invalid_0600_prevents_any_render_or_publication(tmp_path, data, monkeypatch):
    del data["上部構造"]
    path = write_input(tmp_path, data)
    output = tmp_path / "output"

    def unexpected_render(*args):
        pytest.fail("All selected stages must validate before rendering")

    monkeypatch.setattr("src.report.render_report", unexpected_render)
    assert cli.main(["--input", str(path), "--output-dir", str(output)]) == 2
    assert not output.exists()


@pytest.mark.parametrize("alias", [False, True])
def test_input_cannot_be_selected_0600_output_even_by_alias(tmp_path, alias, capsys):
    collision = tmp_path / NAMES[3]
    source = (PROJECT / "pre" / "input.json").read_bytes()
    collision.write_bytes(source)
    if alias:
        (tmp_path / "alias").mkdir()
        collision = tmp_path / "alias" / ".." / NAMES[3]
    assert cli.main(["--input", str(collision), "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert collision.read_bytes() == source
    assert "同じパス" in capsys.readouterr().err
    assert not (tmp_path / NAMES[0]).exists()


@pytest.mark.parametrize("existing", [NAMES, (NAMES[0], NAMES[3]), ()], ids=["all-old", "mixed", "all-new"])
def test_failed_last_publication_restores_all_old_bytes_and_removes_new(tmp_path, monkeypatch, quick_reports, existing):
    originals = {name: ("old " + name).encode("utf-8") for name in existing}
    for name, contents in originals.items():
        (tmp_path / name).write_bytes(contents)
    actual_replace = os.replace

    def fail_last_publication(source, destination):
        if Path(source).name == NAMES[-1] and Path(destination) == tmp_path / NAMES[-1]:
            raise PermissionError("last publication locked")
        return actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_last_publication)
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == originals


def test_failed_last_backup_restores_every_earlier_backup(tmp_path, monkeypatch, quick_reports):
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES}
    for name, contents in originals.items():
        (tmp_path / name).write_bytes(contents)
    actual_replace = os.replace

    def fail_last_backup(source, destination):
        if Path(source) == tmp_path / NAMES[-1]:
            raise PermissionError("last backup locked")
        return actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_last_backup)
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == originals


def test_failed_restoration_keeps_backups_and_reports_recovery_path(tmp_path, monkeypatch, quick_reports, capsys):
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES}
    for name, contents in originals.items():
        (tmp_path / name).write_bytes(contents)
    actual_replace = os.replace

    def fail_publish_and_restore(source, destination):
        source, destination = Path(source), Path(destination)
        if source.name == NAMES[-1] and destination == tmp_path / NAMES[-1]:
            raise PermissionError("last publication locked")
        if source.name.endswith(".backup"):
            raise PermissionError("restoration locked")
        return actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_publish_and_restore)
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    recovery, = tmp_path.glob(".webpier-*")
    for name, contents in originals.items():
        assert (recovery / (name + ".backup")).read_bytes() == contents
    error = capsys.readouterr().err
    assert str(recovery.resolve()) in error
    assert "復元" in error


@pytest.mark.parametrize("name", NAMES[2:])
def test_0600_directory_collision_is_preserved_before_other_publication(tmp_path, quick_reports, name):
    collision = tmp_path / name
    collision.mkdir()
    (collision / "keep.txt").write_bytes(b"keep")
    (tmp_path / NAMES[0]).write_bytes(b"old 0500")
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert (collision / "keep.txt").read_bytes() == b"keep"
    assert (tmp_path / NAMES[0]).read_bytes() == b"old 0500"
    assert not list(tmp_path.glob(".webpier-*"))


def test_0600_symlink_output_is_preserved(tmp_path, quick_reports):
    target = tmp_path / "target.txt"
    target.write_bytes(b"keep target")
    link = tmp_path / NAMES[3]
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Platform cannot create symlink: {exc}")
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert link.is_symlink()
    assert target.read_bytes() == b"keep target"
    assert not (tmp_path / NAMES[0]).exists()


@pytest.mark.parametrize("external_edit", [False, True])
def test_input_bytes_are_read_once_for_calculation_and_drift_blocks_publication(
    tmp_path, data, quick_reports, monkeypatch, capsys, external_edit,
):
    path = write_input(tmp_path, data)
    source = path.read_bytes()
    actual_read = Path.read_bytes
    reads = 0

    def read_once(self):
        nonlocal reads
        if self == path:
            reads += 1
            contents = actual_read(self)
            if external_edit:
                self.write_bytes(b"external edit after reading")
            return contents
        return actual_read(self)

    monkeypatch.setattr(Path, "read_bytes", read_once)
    actual_calculate = cli._calculate_stages
    computed = {}

    def calculate(*args):
        assert not computed  # One in-memory calculation chain for all stages.
        computed.update(actual_calculate(*args))
        return computed

    monkeypatch.setattr(cli, "_calculate_stages", calculate)
    output = tmp_path / "output"
    previous = {}
    if external_edit:
        output.mkdir()
        previous = {output / name: ("previous " + name).encode("utf-8") for name in NAMES}
        for target, content in previous.items():
            target.write_bytes(content)
    assert cli.main(["--input", str(path), "--output-dir", str(output), "--overwrite"]) == (2 if external_edit else 0)
    assert reads == 1
    assert set(computed) == {"0500", "0600", "0610", "0620", "0710", "0720"}
    assert all(result["provenance"]["input_sha256"] == hashlib.sha256(source).hexdigest()
               for result in computed.values())
    if external_edit:
        assert "入力が変更" in capsys.readouterr().err
        assert {target: actual_read(target) for target in output.rglob("*") if target.is_file()} == previous
        return
    for name in NAMES[1::2]:
        result = json.loads((output / name).read_text(encoding="utf-8"))
        assert result["provenance"]["input_sha256"] == hashlib.sha256(source).hexdigest()


@pytest.mark.parametrize("invalid", [b"not JSON", b"\xff\xfe"])
def test_bad_json_or_encoding_is_reported_without_output(tmp_path, invalid, capsys):
    path = tmp_path / "bad.json"
    path.write_bytes(invalid)
    output = tmp_path / "output"
    assert cli.main(["--input", str(path), "--output-dir", str(output)]) == 2
    assert "JSON" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("stage", ["0600", "all"])
def test_editor_saved_snow_reaches_cli_json_and_existing_tables(
    tmp_path: Path, data: dict, stage: str,
) -> None:
    from src.editor_model import EditorDocument, parse_field, set_at

    keys = tuple(f"雪荷重_{year}年確率" for year in (2, 10, 30))
    legacy = deepcopy(data)
    for side, point, outer in (("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")):
        side_data = legacy["上部工反力"][side]
        for record in (*side_data[point]["支承"], side_data.get(outer, {}).get("合計", {})):
            for key in keys:
                record.pop(key, None)
    document = EditorDocument.open(write_input(tmp_path, legacy))
    for side, point, ten_year, thirty_year in (("起点側", "B支点", 3, 1), ("終点側", "C支点", 4, 2)):
        for index in range(10):
            prefix = ("上部工反力", side, point, "支承", index)
            set_at(document.data, prefix + ("支承位置",), index)
            for key, value in ((keys[1], ten_year), (keys[2], thirty_year)):
                set_at(document.data, prefix + (key,), parse_field(str(value), "数値", prefix + (key,)))
    edits = (
        (("起点側", "B支点", "支承", 0, keys[0]), 12.5),
        (("起点側", "B支点", "支承", 9, keys[0]), 7.5),
        (("終点側", "C支点", "支承", 0, keys[0]), 3),
        (("起点側", "A支点", "合計", keys[0]), 0),
        (("終点側", "D支点", "合計", keys[0]), -1),
        (("起点側", "A支点", "合計", keys[2]), -3),
        (("終点側", "D支点", "合計", keys[2]), 0),
    )
    for tail, value in edits:
        path = ("上部工反力",) + tail
        set_at(document.data, path, parse_field(str(value), "数値", path))
    saved = document.save(tmp_path / "saved-snow.json").path
    assert EditorDocument.open(saved).data == document.data
    output = tmp_path / "output"
    assert cli.main(["--stage", stage, "--input", str(saved), "--output-dir", str(output)]) == 0
    result = json.loads((output / NAMES[3]).read_text(encoding="utf-8"))
    expected = ((0, 20, 3, -1, 20, 2), (30, 30, 40, 40, 60, 80), (-3, 10, 20, 0, 7, 20))
    for key, values in zip(keys, expected):
        assert tuple(result["snow_loads"]["points"][point][key] for point in "ABCD") == values[:4]
        assert tuple(result["snow_loads"]["girders"][girder][key] for girder in ("AB", "CD")) == values[4:]
    assert result["provenance"]["input_sha256"] == hashlib.sha256(saved.read_bytes()).hexdigest()
    pages = PdfReader(output / NAMES[2]).pages
    # Variable pages: the opening dead/snow tables end at the self-weight section.
    text = "".join("".join(page.extract_text().split()) for page in pages)
    text = text[:text.index("(3)橋脚自重の計算")]
    for year in (2, 10, 30):
        assert text.count(f"雪荷重{year}年確率") == 5
    assert {path.name for path in output.iterdir()} == (set(NAMES) | {"post"} if stage == "all" else set(NAMES[2:4]))


@pytest.mark.parametrize("invalid", ["-", -1, True])
def test_invalid_snow_preserves_all_existing_outputs_before_rendering(
    tmp_path: Path, data: dict, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], invalid: object,
) -> None:
    key = "雪荷重_2年確率"
    data["上部工反力"]["起点側"]["B支点"]["支承"][9][key] = invalid
    source = write_input(tmp_path, data)
    output = tmp_path / "output"
    output.mkdir()
    originals = {name: ("existing " + name).encode("utf-8") for name in NAMES}
    for name, contents in originals.items():
        (output / name).write_bytes(contents)

    def unexpected_render(*args: object) -> None:
        pytest.fail("Invalid snow must be rejected before rendering or publication")

    for module, renderer in (("report", "render_report"), ("reaction_report", "render_reaction_report"),
                             ("longitudinal_report", "render_longitudinal_report"), ("transverse_report", "render_transverse_report")):
        monkeypatch.setattr(f"src.{module}.{renderer}", unexpected_render)
    assert cli.main(["--stage", "all", "--input", str(source), "--output-dir", str(output), "--overwrite"]) == 2
    assert key in capsys.readouterr().err
    assert {path.name: path.read_bytes() for path in output.iterdir()} == originals
