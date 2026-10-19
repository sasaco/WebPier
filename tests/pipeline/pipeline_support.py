"""A small stage registry with fast fake calculations and reports, for the generation tests.

A → B → C, where B writes a FrameWeb-like file and C a JRSNAP-like file. Every call is logged so the
tests can tell what was calculated and rendered, and in which order.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from webpier.core.printed import LENGTH, Printed
from webpier.pipeline.stages import Export, Registry, StageSpec

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = FIXTURES / "inputs" / "current.json"


@dataclass(frozen=True)
class FakeResult:
    stage: str
    read: tuple[str, ...]
    width: Printed


class Recorder:
    def __init__(self) -> None:
        self.log: list[tuple[str, str, tuple[str, ...]]] = []
        self.hooks: dict[tuple[str, str], object] = {}  # (action, stage) -> callable run inside that step

    def _hook(self, action: str, stage: str) -> None:
        hook = self.hooks.get((action, stage))
        if hook is not None:
            hook()

    def calculate(self, stage: str):
        def calculate(pier, results):
            self.log.append(("calculate", stage, tuple(results)))
            self._hook("calculate", stage)
            return FakeResult(stage, tuple(results), LENGTH(1.5))
        return calculate

    def render(self, stage: str):
        def render(results, pier, path, pages):
            self.log.append(("render", stage, tuple(results)))
            self._hook("render", stage)
            Path(path).write_bytes(f"%PDF {stage} {results[stage].read}".encode())
            return path
        return render

    def export(self, stage: str, content: bytes):
        def build(results, pier):
            self.log.append(("export", stage, tuple(results)))
            self._hook("export", stage)
            return content
        return build

    def actions(self, action: str) -> list[str]:
        return [stage for name, stage, _ in self.log if name == action]


def fake_registry(recorder: Recorder) -> Registry:
    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), recorder.render("B"),
                  (Export("frameweb", "frame.json", recorder.export("B", b'{"B": 1}\n')),)),
        StageSpec("C", "C_地震", ("B",), recorder.calculate("C"), recorder.render("C"),
                  (Export("jrsnap", "model.ndu", recorder.export("C", b"NDU C\r\n"),
                          metadata={"target_version": "5.2-L03", "analysis_run": False}),)),
    ))


def fake_fempython():
    """The stand-in FEMPython runner as a module: what it writes is its own (tests/fixtures/fempython/fake_runner.py)."""
    spec = importlib.util.spec_from_file_location("fake_fempython_runner", FIXTURES / "fempython" / "fake_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_reactions(frameweb: bytes) -> bytes:
    """The reaction pickup CSV the stand-in returns for the FrameWeb file *frameweb* (decision 54)."""
    return fake_fempython().reactions(json.loads(frameweb))


def copy_input(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    shutil.copyfile(CURRENT, path)
    return path


def tree(root: Path) -> dict[str, bytes]:
    """Every file under *root* by relative path, including leftovers of a staging directory."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


# The sample's footing bars (12_フーチング.pdf 255・258) with the footing concrete's Dmax 25: 0800 needs 鉄筋.フーチング
# (decision 60); current.json itself keeps them blank.
_FOOTING_ROW = {"diameter_mm": None, "material": None, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": None,
                "direction": "線路", "face": "上", "pitch_mm": None, "layers": 1, "stack_order": 1}
_FOOTING_STIRRUP = {"type": "内側", "direction": "線路", "diameter_mm": 16, "material": None, "sets": None,
                    "pitch_mm": 250, "start_mm": None, "end_mm": None, "legs_mode": "指定", "effective_legs": None,
                    "distribution_mode": "密度", "width_pitch_mm": None, "density_per_m": 2}
SAMPLE_FOOTING = {
    "materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
    "pure_cover_mm": None,
    "main_rows": [_FOOTING_ROW,
                  {**_FOOTING_ROW, "face": "下", "diameter_mm": 25, "pitch_mm": 125, "cover_mode": "指定", "center_mm": 100},
                  {**_FOOTING_ROW, "direction": "直角", "stack_order": 2},
                  {**_FOOTING_ROW, "direction": "直角", "face": "下", "diameter_mm": 29, "pitch_mm": 125,
                   "cover_mode": "指定", "center_mm": 127, "stack_order": 2}],
    "side_rows": [], "band_rows": [_FOOTING_STIRRUP, {**_FOOTING_STIRRUP, "direction": "直角"}],
    "manual_positions": [], "position_mode": "基本"}


def footing_document() -> dict:
    """current.json with the sample's footing bars."""
    data = json.loads(CURRENT.read_text(encoding="utf-8"))
    data["鉄筋"]["フーチング"] = SAMPLE_FOOTING
    return data


def footing_input(directory: Path) -> Path:
    """current.json with the sample's footing bars, written as a generation's input."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(footing_document(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
