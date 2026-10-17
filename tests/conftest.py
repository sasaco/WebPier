"""Settings shared by every test: deterministic hypothesis runs (decision 15).

The property tests run in the one full-suite gate (.claude/check.ps1), so they must give the same examples on every
run and stay fast: examples are derived from the test itself (derandomize), nothing is stored between runs, and
there is no per-example deadline because a calculation's time depends on the machine.
"""

from hypothesis import HealthCheck, settings

settings.register_profile(
    "webpier", derandomize=True, database=None, max_examples=100, deadline=None, print_blob=True,
    suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("webpier")
