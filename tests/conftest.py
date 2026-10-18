"""Settings shared by every test: deterministic hypothesis runs (decision 15) and the stand-in runners.

The property tests run in the one full-suite gate (.claude/check.ps1), so they must give the same examples on every
run and stay fast: examples are derived from the test itself (derandomize), nothing is stored between runs, and
there is no per-example deadline because a calculation's time depends on the machine.

A generation with 0610 or 0620 has the FEMPython runner draw the load diagrams (decision 44). Every test uses the
stand-in tests/fixtures/fempython/fake_runner.py instead, through STRUCTURAL_MCP_FEMPYTHON_RUNNER (which child
processes inherit, and which comes before the .env file); ``real_fempython_runner`` is the runner the user set up,
for the one test that calls it. A generation with 0711 has the JRSNAP runner analyze the NDU (decision 47); every
test uses tests/fixtures/jrsnap/fake_runner.py the same way, through STRUCTURAL_MCP_JRSNAP_RUNNER.
"""

import os
from pathlib import Path
import sys

from hypothesis import HealthCheck, settings
import pytest

from webpier.pipeline import fempython, jrsnap

settings.register_profile(
    "webpier", derandomize=True, database=None, max_examples=100, deadline=None, print_blob=True,
    suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("webpier")

FAKE_RUNNER = Path(__file__).parent / "fixtures" / "fempython" / "fake_runner.py"
FAKE_JRSNAP_RUNNER = Path(__file__).parent / "fixtures" / "jrsnap" / "fake_runner.py"
_USER_RUNNER = os.environ.get(fempython.RUNNER_KEY, "")
_USER_JRSNAP_RUNNER = os.environ.get(jrsnap.RUNNER_KEY, "")


def _shim(directory: Path, script: Path, key: str, user: str):
    """A stand-in runner as a command the pipeline can start like the real executable, set in *key*."""
    shim = directory / "fake_runner.cmd"
    shim.write_text(f'@"{sys.executable}" "{script}" %*\r\n@exit /b %errorlevel%\r\n', encoding="ascii")
    os.environ[key] = str(shim)
    try:
        yield shim
    finally:
        if user:
            os.environ[key] = user
        else:
            del os.environ[key]


@pytest.fixture(scope="session", autouse=True)
def fake_fempython_runner(tmp_path_factory: pytest.TempPathFactory):
    yield from _shim(tmp_path_factory.mktemp("fempython"), FAKE_RUNNER, fempython.RUNNER_KEY, _USER_RUNNER)


@pytest.fixture(scope="session", autouse=True)
def fake_jrsnap_runner(tmp_path_factory: pytest.TempPathFactory):
    yield from _shim(tmp_path_factory.mktemp("jrsnap"), FAKE_JRSNAP_RUNNER, jrsnap.RUNNER_KEY, _USER_JRSNAP_RUNNER)


@pytest.fixture
def real_fempython_runner() -> Path:
    """The runner the user set up (environment, else .env); the test is skipped without one."""
    try:
        return fempython.runner_path({fempython.RUNNER_KEY: _USER_RUNNER})
    except fempython.RunnerError as exc:
        pytest.skip(f"本物の FEMPython runner がありません: {exc}")
