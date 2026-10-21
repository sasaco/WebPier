"""Run with: uv run --project . --locked python -m webpier [--overwrite] (the input's outputs choose the reports)"""

from webpier.pipeline.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
