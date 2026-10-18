"""Settings shared by every test: deterministic hypothesis runs (decision 15) and the stand-in FEMPython runner.

The property tests run in the one full-suite gate (.claude/check.ps1), so they must give the same examples on every
run and stay fast: examples are derived from the test itself (derandomize), nothing is stored between runs, and
there is no per-example deadline because a calculation's time depends on the machine.

A generation with 0610 or 0620 has the FEMPython runner draw the load diagrams (decision 44). Every test uses the
stand-in tests/fixtures/fempython/fake_runner.py instead, through STRUCTURAL_MCP_FEMPYTHON_RUNNER (which child
processes inherit, and which comes before the .env file); ``real_fempython_runner`` is the runner the user set up,
for the one test that calls it.
"""

import os
from pathlib import Path
import sys

from hypothesis import HealthCheck, settings
import pytest

from webpier.pipeline import fempython

settings.register_profile(
    "webpier", derandomize=True, database=None, max_examples=100, deadline=None, print_blob=True,
    suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("webpier")

FAKE_RUNNER = Path(__file__).parent / "fixtures" / "fempython" / "fake_runner.py"
_USER_RUNNER = os.environ.get(fempython.RUNNER_KEY, "")


@pytest.fixture(scope="session", autouse=True)
def fake_fempython_runner(tmp_path_factory: pytest.TempPathFactory):
    """The stand-in runner, as a command the pipeline can start like the real executable."""
    shim = tmp_path_factory.mktemp("fempython") / "fake_runner.cmd"
    shim.write_text(f'@"{sys.executable}" "{FAKE_RUNNER}" %*\r\n@exit /b %errorlevel%\r\n', encoding="ascii")
    os.environ[fempython.RUNNER_KEY] = str(shim)
    try:
        yield shim
    finally:
        if _USER_RUNNER:
            os.environ[fempython.RUNNER_KEY] = _USER_RUNNER
        else:
            del os.environ[fempython.RUNNER_KEY]


@pytest.fixture
def real_fempython_runner() -> Path:
    """The runner the user set up (environment, else .env); the test is skipped without one."""
    try:
        return fempython.runner_path({fempython.RUNNER_KEY: _USER_RUNNER})
    except fempython.RunnerError as exc:
        pytest.skip(f"本物の FEMPython runner がありません: {exc}")
