"""Run with: uv run --project . --locked python ./run_design.py (the same as python -m webpier)."""

from webpier.pipeline.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
