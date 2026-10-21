"""A small registry whose CLI runs in-process, so the editor's calculation is tested against real publications."""

from __future__ import annotations

import contextlib
import io
import subprocess
import time
from pathlib import Path

import pymupdf

from webpier.pipeline import cli
from webpier.pipeline.stages import Export, FrameAnalysis, NonlinearAnalysis, Registry, StageSpec


def pdf_bytes(pages: int = 2, text: str = "WebPier") -> bytes:
    document = pymupdf.open()
    try:
        for page in range(pages):
            document.new_page(width=420, height=595).insert_text((72, 72), f"{text} {page + 1}")
        return document.tobytes()
    finally:
        document.close()


def write_pdf(path: Path, pages: int = 2) -> Path:
    path.write_bytes(pdf_bytes(pages, path.stem))
    return path


def _render(stage: str, pages: int):
    def render(results, pier, path, drawn):
        Path(path).write_bytes(pdf_bytes(pages, stage))
    return render


def registry() -> Registry:
    """0500 → 0610 (FrameWeb) → 0611 (frame analysis) and 0710 (JRSNAP) → 0711 (static nonlinear analysis); the stems
    and 出力項目 of the real registry (decision 72), so current.json chooses 0500, 0610 and 0710."""
    return Registry((
        StageSpec("0500", "0500_直接基礎", (), lambda pier, results: {"stage": "0500"}, _render("0500", 1)),
        StageSpec("0610", "0610_線路方向荷重", ("0500",), lambda pier, results: {"stage": "0610"}, _render("0610", 2),
                  (Export("frameweb", "線路方向.json", lambda results, pier: b'{"frame": 1}\n'),)),
        StageSpec("0611", "0611_線路方向照査", ("0610",), frame_analysis=FrameAnalysis(
            "0610", "frameweb", (("pik", "線路方向.pik"), ("displacement", "線路方向_ピックアップ変位量.csv"),
                                 ("reaction", "線路方向_ピックアップ反力.csv")))),
        StageSpec("0710", "0710_線路方向荷重", ("0610",), lambda pier, results: {"stage": "0710"}, _render("0710", 3),
                  (Export("jrsnap", "線路方向.ndu", lambda results, pier: b"NDU\r\n",
                          metadata={"analysis_run": False}),)),
        StageSpec("0711", "0711_線路方向非線形解析", ("0710",),
                  nonlinear_analysis=NonlinearAnalysis("0710", "jrsnap", "jrsnap", "線路方向_JRSNAP")),
    ), outputs={"ground_model": ("0500",), "longitudinal": ("0610",), "longitudinal_frame_analysis": ("0611",),
                "longitudinal_seismic": ("0710",), "longitudinal_nonlinear_analysis": ("0711",)})


class InProcessRunner:
    """Stands in for subprocess.run: runs ``python -m webpier`` arguments through cli.main with *registry*."""

    def __init__(self, stages: Registry, *, before=None, after=None) -> None:
        self.registry = stages
        self.commands: list[list[str]] = []
        self.before = before  # called with the command before the CLI runs
        self.after = after  # and after it

    def __call__(self, command, *, stdout, stderr, **kwargs):
        self.commands.append(command)
        if self.before is not None:
            self.before(command)
        assert command[1:3] == ["-m", "webpier"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(command[3:], registry=self.registry)
        if self.after is not None:
            self.after(command)
        stdout.write(out.getvalue().encode("utf-8"))
        stderr.write(err.getvalue().encode("utf-8"))
        return subprocess.CompletedProcess(command, code)


def wait(controller, timeout: float = 30):
    deadline = time.monotonic() + timeout
    while (result := controller.poll()) is None:
        assert time.monotonic() < deadline, "the calculation did not finish"
        time.sleep(0.01)
    return result
