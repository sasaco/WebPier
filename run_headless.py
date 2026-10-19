"""The headless runner structural-mcp starts (decision 61): .venv\\Scripts\\python.exe -X utf8 ./run_headless.py <command>."""

from webpier.pipeline.headless import main

if __name__ == "__main__":
    raise SystemExit(main())
