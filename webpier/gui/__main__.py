"""Run with: uv run --project . --locked python -m webpier.gui [--input pre/input.json]"""

from webpier.gui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
