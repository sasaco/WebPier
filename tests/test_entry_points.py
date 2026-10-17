"""The wrapper scripts at the repository root run the same code as ``python -m``."""

import runpy
from pathlib import Path

import webpier.gui.app
import webpier.pipeline.cli

ROOT = Path(__file__).parents[1]


def test_run_design_runs_the_pipeline_cli():
    assert runpy.run_path(str(ROOT / "run_design.py"))["main"] is webpier.pipeline.cli.main


def test_edit_input_launches_the_editor():
    assert runpy.run_path(str(ROOT / "edit_input.py"))["main"] is webpier.gui.app.main
