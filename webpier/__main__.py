"""Run with: uv run --project . --locked python -m webpier [--stage all] [--overwrite]"""

from webpier.pipeline.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
