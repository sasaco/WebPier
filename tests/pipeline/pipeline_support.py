"""A small stage registry with fast fake calculations and reports, for the generation tests.

A → B → C, where B writes a FrameWeb-like file and C an opt-in JRSNAP-like file. Every call is logged so the
tests can tell what was calculated and rendered, and in which order.
"""

from __future__ import annotations

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
        def render(results, pier, path):
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
                  (Export("jrsnap", "model.ndu", recorder.export("C", b"NDU C\r\n"), opt_in=True,
                          metadata={"target_version": "5.2-L03", "analysis_run": False}),)),
    ))


def copy_input(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    shutil.copyfile(CURRENT, path)
    return path


def tree(root: Path) -> dict[str, bytes]:
    """Every file under *root* by relative path, including leftovers of a staging directory."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}
