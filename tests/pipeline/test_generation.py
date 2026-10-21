"""One generation: read the input once, calculate the stages its 出力項目 choose (decision 72), render, and publish all
files or none."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from gridlayoutpdf import FontError, LayoutError

from pipeline_support import LONGITUDINAL, Recorder, choose, copy_input, fake_registry, tree
from webpier.core.errors import InputError
from webpier.core.integrity import canonical_sha256, load_json, sha256
from webpier.pipeline import generate, publication
from webpier.pipeline.generate import GenerationError, GenerationOptions, prepare
from webpier.pipeline.runtime import RuntimeIdentityError

IDENTITY = {Path("C:/webpier/core/printed.py"): "1" * 64, Path("C:/fonts/msmincho.ttc"): "2" * 64}
OUTPUTS = {"A": ["A_基礎.pdf", "A_基礎.json"], "B": ["B_荷重.pdf", "B_荷重.json"], "C": ["C_地震.pdf", "C_地震.json"]}


class Env:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.recorder = Recorder()
        self.registry = fake_registry(self.recorder)
        self.input = copy_input(root / "pre")
        self.identities = [IDENTITY]  # the last one repeats
        self.identity_calls = 0
        monkeypatch.setattr(generate, "dependency_hashes", self._identity)

    def _identity(self):
        self.identity_calls += 1
        return dict(self.identities[min(self.identity_calls, len(self.identities)) - 1])

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def post(self) -> Path:
        return self.root / "post"

    def options(self, **changes) -> GenerationOptions:
        return GenerationOptions(self.input, self.output, self.post, **changes)

    def generate(self, **changes):
        return generate.generate(self.options(**changes), registry=self.registry)

    def choose(self, *items: str) -> None:
        """Have the input choose only the 出力項目 *items* (decision 72)."""
        choose(self.input, *items)

    def files(self) -> dict[str, bytes]:
        return {**{f"output/{k}": v for k, v in tree(self.output).items()},
                **{f"post/{k}": v for k, v in tree(self.post).items()}}

    def write_old(self, *names: str) -> dict[str, bytes]:
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old " + name.encode())
        return self.files()


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def test_the_chosen_items_publish_every_report_and_every_export_with_its_sidecar(env):
    generation = env.generate()
    assert generation.stages == ("A", "B", "C")
    assert sorted(env.files()) == sorted(
        [f"output/{name}" for names in OUTPUTS.values() for name in names]
        + ["post/frame.json", "post/frame.json.provenance.json", "post/model.ndu", "post/model.ndu.provenance.json"])
    assert env.files()["output/B_荷重.pdf"] == b"%PDF B ('A',)"
    assert env.files()["post/frame.json"] == b'{"B": 1}\n'
    assert env.files()["post/model.ndu"] == b"NDU C\r\n"
    assert [artifact.role for artifact in generation.artifacts] == [
        "A.pdf", "A.json", "B.pdf", "B.json", "C.pdf", "C.json", "B.frameweb", "C.jrsnap",
        "B.frameweb.provenance", "C.jrsnap.provenance"]


def test_no_export_is_written_only_on_request(env):
    """Decision 42: the options name no export kinds; every export of a selected stage is written."""
    with pytest.raises(TypeError):
        env.options(opt_in=frozenset({"jrsnap"}))


@pytest.mark.parametrize("name,value", [("stage", "A"), ("frame_analysis", True), ("nonlinear_analysis", True)])
def test_no_option_chooses_stages(env, name, value):
    """Decision 72 (ADR-0011): the input's 出力項目 alone choose the stages."""
    with pytest.raises(TypeError):
        env.options(**{name: value})


def test_only_the_stages_of_the_chosen_items_are_calculated_and_published(env):
    """Decision 72: an item is chosen with every item it uses, so its stages are all the generation calculates."""
    env.choose("ground_model")
    generation = env.generate()
    assert generation.stages == ("A",) and set(generation.results) == {"A"}
    assert (env.recorder.actions("calculate"), env.recorder.actions("export"), env.recorder.actions("render")) == (
        ["A"], [], ["A"])
    assert sorted(env.files()) == ["output/A_基礎.json", "output/A_基礎.pdf"]
    env.choose(*LONGITUDINAL)
    generation = env.generate(overwrite=True)
    assert generation.stages == ("A", "B")
    assert sorted(env.files()) == ["output/A_基礎.json", "output/A_基礎.pdf", "output/B_荷重.json",
                                   "output/B_荷重.pdf", "post/frame.json", "post/frame.json.provenance.json"]


def test_every_calculation_and_export_succeeds_before_any_report_is_rendered(env):
    env.generate()
    actions = [name for name, _, _ in env.recorder.log]
    assert actions == ["calculate"] * 3 + ["export"] * 2 + ["render"] * 3


def test_each_step_receives_only_the_declared_results(env):
    env.generate()
    assert env.recorder.log == [
        ("calculate", "A", ()), ("calculate", "B", ("A",)), ("calculate", "C", ("B",)),
        ("export", "B", ("A", "B")), ("export", "C", ("B", "C")),
        ("render", "A", ("A",)), ("render", "B", ("A", "B")), ("render", "C", ("B", "C"))]


def test_a_calculation_error_stops_before_rendering_and_writes_nothing(env):
    def fail():
        raise InputError("下部構造.寸法.B1: 正の数値が必要です")
    env.recorder.hooks["calculate", "B"] = fail
    with pytest.raises(InputError, match="B1"):
        env.generate()
    assert env.recorder.actions("render") == []
    assert not env.output.exists() and not env.post.exists()


def test_an_export_input_error_stops_before_rendering_and_writes_nothing(env):
    """A blank JRSNAP setting is an input error of the export; no report is rendered for nothing."""
    def fail():
        raise InputError("jrsnap_longitudinal.analysis_steps: 値が必要です")
    env.recorder.hooks["export", "C"] = fail
    with pytest.raises(InputError, match="analysis_steps"):
        env.generate()
    assert env.recorder.actions("render") == []
    assert not env.output.exists() and not env.post.exists()


def test_the_result_json_binds_the_input_bytes_and_the_implementation(env):
    env.choose(*LONGITUDINAL)
    env.generate()
    document = load_json(env.files()["output/B_荷重.json"])
    assert document == {
        "schema_version": 1, "stage": "B",
        "input": {"file": "input.json", "sha256": sha256(env.input.read_bytes())},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in IDENTITY.items()}),
        "result": {"stage": "B", "read": ["A"], "width": 1.5}}


def test_the_sidecar_lists_the_whole_generation_with_relative_names(env):
    env.generate()
    files = env.files()
    sidecar = load_json(files["post/model.ndu.provenance.json"])
    artifacts = [("A.pdf", "output", "A_基礎.pdf"), ("A.json", "output", "A_基礎.json"),
                 ("B.pdf", "output", "B_荷重.pdf"), ("B.json", "output", "B_荷重.json"),
                 ("C.pdf", "output", "C_地震.pdf"), ("C.json", "output", "C_地震.json"),
                 ("B.frameweb", "post", "frame.json"), ("C.jrsnap", "post", "model.ndu")]
    assert sidecar == {
        "schema_version": 1, "stage": "C", "export": "jrsnap", "file": "model.ndu",
        "sha256": sha256(b"NDU C\r\n"), "metadata": {"target_version": "5.2-L03", "analysis_run": False},
        "input": {"file": "input.json", "sha256": sha256(env.input.read_bytes())},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in IDENTITY.items()}),
        "selected_stages": ["A", "B", "C"],
        "artifacts": [{"role": role, "directory": directory, "file": name,
                       "sha256": sha256(files[f"{directory}/{name}"])} for role, directory, name in artifacts]}
    other = load_json(files["post/frame.json.provenance.json"])
    assert other["artifacts"] == sidecar["artifacts"] and other["export"] == "frameweb"


@pytest.mark.parametrize("items,message", [
    (("longitudinal",), "outputs.longitudinal: outputs.ground_model・outputs.reactions も true が必要です"),
    (("ground_model", "longitudinal_seismic"), "outputs.longitudinal_seismic: outputs.longitudinal も true が必要です"),
    ((), r"outputs: 出力項目が選ばれていません"),
])
def test_an_invalid_choice_of_items_is_rejected_before_anything_is_calculated(env, items, message):
    """Decision 72: an item needs every item it uses, and at least one item is chosen."""
    env.choose(*items)
    with pytest.raises(InputError, match=message):
        env.generate()
    assert env.recorder.log == [] and env.files() == {}


@pytest.mark.parametrize("text,message", [
    ('{"schema_version": 1, "schema_version": 1}', "キーが重複しています: schema_version"),
    ('{"schema_version": NaN}', "有限でない数値があります: NaN"),
    ('{"schema_version": Infinity}', "有限でない数値があります: Infinity"),
    ('{"schema_version": 1e999}', "有限でない数値があります"),
])
def test_the_input_is_always_strict_json(env, text, message):
    env.input.write_text(text, encoding="utf-8")
    with pytest.raises(InputError, match=message):
        env.generate()
    assert env.recorder.log == [] and env.files() == {}


def test_the_input_is_read_once_for_every_stage(env, monkeypatch):
    reads = []
    original = Path.read_bytes

    def counting(self):
        reads.append(self)
        return original(self)
    monkeypatch.setattr(Path, "read_bytes", counting)
    env.generate()
    assert reads.count(env.input) == 1


def test_an_input_changed_during_generation_is_not_published(env):
    old = env.write_old("output/A_基礎.pdf")
    env.recorder.hooks["render", "B"] = lambda: env.input.write_bytes(env.input.read_bytes() + b" ")
    with pytest.raises(GenerationError, match="生成中に入力ファイルが変更されました"):
        env.generate(overwrite=True)
    assert env.files() == old


def test_an_implementation_changed_during_generation_is_not_published(env):
    env.identities = [IDENTITY, {**IDENTITY, Path("C:/webpier/core/printed.py"): "3" * 64}]
    with pytest.raises(GenerationError, match="生成中にプログラム・描画依存が変更されました"):
        env.generate()
    assert env.files() == {}


def test_an_implementation_changed_during_publication_restores_the_old_files(env):
    old = env.write_old("output/A_基礎.pdf", "post/frame.json")
    env.identities = [IDENTITY, IDENTITY, {Path("C:/webpier/new.py"): "4" * 64}]
    with pytest.raises(GenerationError, match="生成中にプログラム・描画依存が変更されました"):
        env.generate(overwrite=True)
    assert env.identity_calls == 3
    assert env.files() == old


@pytest.mark.parametrize("error", [RuntimeIdentityError("描画依存にリンクがあります"), FontError("font missing")])
def test_an_implementation_that_cannot_be_identified_stops_the_generation(env, monkeypatch, error):
    def fail():
        raise error
    monkeypatch.setattr(generate, "dependency_hashes", fail)
    with pytest.raises(GenerationError, match="プログラム・描画依存を確認できません"):
        env.generate()
    assert env.recorder.log == []


def test_a_render_failure_publishes_nothing(env):
    old = env.write_old("output/A_基礎.pdf", "output/C_地震.pdf")

    def fail():
        raise RuntimeError("renderer bug")
    env.recorder.hooks["render", "C"] = fail
    with pytest.raises(RuntimeError, match="renderer bug"):
        env.generate(overwrite=True)
    assert env.files() == old


def test_a_layout_error_is_reported_with_its_stage(env):
    def fail():
        raise LayoutError("table does not fit")
    env.recorder.hooks["render", "B"] = fail
    with pytest.raises(GenerationError, match="Bの帳票を作成できません: table does not fit"):
        env.generate()
    assert env.files() == {}


def test_a_publication_failure_restores_every_old_file(env, monkeypatch):
    old = env.write_old("output/A_基礎.pdf", "output/B_荷重.json", "post/frame.json")
    original = os.replace

    def locked(source, destination):
        if Path(destination).name == "frame.json.provenance.json":
            raise PermissionError("locked")
        return original(source, destination)
    monkeypatch.setattr(publication.os, "replace", locked)
    with pytest.raises(PermissionError, match="locked"):
        env.generate(overwrite=True)
    assert env.files() == old


def test_existing_outputs_need_overwrite_and_are_checked_before_calculating(env):
    old = env.write_old("post/frame.json")
    with pytest.raises(FileExistsError, match="--overwrite"):
        env.generate()
    assert env.recorder.log == [] and env.files() == old
    env.generate(overwrite=True)
    assert env.files()["post/frame.json"] == b'{"B": 1}\n'


def test_outputs_of_the_items_not_chosen_are_left_alone(env):
    """Decision 72: a generation never touches the files of the items it does not choose."""
    old = env.write_old("output/C_地震.pdf", "post/model.ndu")
    env.choose(*LONGITUDINAL)
    env.generate()
    files = env.files()
    assert files["output/C_地震.pdf"] == old["output/C_地震.pdf"]
    assert files["post/model.ndu"] == old["post/model.ndu"]
    assert "post/model.ndu.provenance.json" not in files


def test_the_input_cannot_be_an_output(env):
    env.input.rename(env.input.parent / "A_基礎.json")
    options = generate.GenerationOptions(env.input.parent / "A_基礎.json", env.input.parent, env.post)
    with pytest.raises(OSError, match="入力ファイルと出力ファイルを同じパスにはできません"):
        generate.generate(options, registry=env.registry)


def test_a_directory_is_never_overwritten(env):
    (env.output / "A_基礎.pdf").mkdir(parents=True)
    with pytest.raises(OSError, match="通常ファイル以外は上書きできません"):
        env.generate(overwrite=True)


def test_an_output_written_by_someone_else_during_generation_is_not_replaced(env):
    env.write_old("output/A_基礎.pdf")
    env.recorder.hooks["render", "C"] = lambda: (env.output / "A_基礎.pdf").write_bytes(b"theirs")
    with pytest.raises(GenerationError, match="生成中に出力先が変更されました"):
        env.generate(overwrite=True)
    assert env.files()["output/A_基礎.pdf"] == b"theirs"


def test_an_output_written_just_before_publication_is_restored(env, monkeypatch):
    env.write_old("output/A_基礎.pdf")
    original = generate.publish_outputs

    def racing(pairs, staging, overwrite, *, final_validator, folders):
        (env.output / "A_基礎.pdf").write_bytes(b"theirs")
        (env.output / "C_地震.pdf").write_bytes(b"new file of theirs")
        return original(pairs, staging, overwrite, final_validator=final_validator, folders=folders)
    monkeypatch.setattr(generate, "publish_outputs", racing)
    with pytest.raises(GenerationError, match="公開の直前に出力先が変更されました"):
        env.generate(overwrite=True)
    assert env.files() == {"output/A_基礎.pdf": b"theirs", "output/C_地震.pdf": b"new file of theirs"}


def test_a_published_file_changed_before_commit_is_rolled_back(env, monkeypatch):
    original = generate.publish_outputs

    def tampering(pairs, staging, overwrite, *, final_validator, folders):
        def validator():
            (env.post / "frame.json").write_bytes(b"changed")
            final_validator()
        return original(pairs, staging, overwrite, final_validator=validator, folders=folders)
    monkeypatch.setattr(generate, "publish_outputs", tampering)
    with pytest.raises(GenerationError, match="公開した成果物が一致しません: B.frameweb"):
        env.generate()
    assert env.files() == {}


def test_a_prepared_generation_publishes_only_once_and_only_while_held(env):
    env.choose("ground_model")
    with prepare(env.options(), registry=env.registry) as candidate:
        assert candidate.staged("A.pdf").read_bytes() == b"%PDF A ()"
        candidate.publish()
        assert candidate.published
        with pytest.raises(GenerationError, match="既に公開を試みました"):
            candidate.publish()
    with pytest.raises(GenerationError, match="保持期間が終わっています"):
        candidate.publish()


def test_a_prepared_generation_that_is_not_published_leaves_nothing(env):
    with prepare(env.options(), registry=env.registry) as candidate:
        assert not candidate.published
    assert env.files() == {}


def test_held_staged_files_must_not_change(env):
    env.choose("ground_model")
    with prepare(env.options(), registry=env.registry) as candidate:
        candidate.staged("A.pdf").write_bytes(b"edited")
        with pytest.raises(GenerationError, match="一時領域の成果物が変更されています: A.pdf"):
            candidate.publish()
    assert env.files() == {}


def test_no_extra_file_may_appear_in_staging(env):
    env.choose("ground_model")
    with prepare(env.options(), registry=env.registry) as candidate:
        (candidate.staged("A.pdf").parent / "extra.txt").write_bytes(b"x")
        with pytest.raises(GenerationError, match="一時領域のファイル集合が変更されています"):
            candidate.verify()


def test_the_same_input_gives_the_same_bytes_twice(env, tmp_path):
    env.generate()
    first = env.files()
    for path in [*env.output.iterdir(), *env.post.iterdir()]:
        path.unlink()
    env.generate()
    assert env.files() == first
