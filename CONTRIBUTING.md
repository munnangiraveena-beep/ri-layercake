# Contributing

Thanks for helping. Bug reports with a sample input are the most useful thing you can send, especially pastes
that failed to parse (please invent the numbers).

## Setup

```bash
python3.11 -m venv .venv && . .venv/bin/activate
cd python && pip install -e ".[dev]"
pytest && ruff check src tests && mypy src
```

Web app:

```bash
cd python && pip wheel --no-deps -w dist .
cd ../web && npm ci && npm run py && npm run dev
```

## Rules of the road

- The Python package is the only source of numbers and layout. The web app draws what the engine returns.
- Every formula needs a test against a hand-worked example.
- Add a case to `python/tests/corpus/` for every paste format you fix.
- Scene changes update the golden snapshots on purpose: `UPDATE_GOLDEN=1 pytest tests/test_scene.py`, then review
  the diff.
- No network calls from the web app while editing or exporting.
