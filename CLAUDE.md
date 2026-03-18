# Vacancy Monitor

Multi-source job vacancy aggregator with deterministic scoring and automated application via Playwright.

## Project structure

- `src/vacancy_monitor/` - main package
- `config/profile.toml` - candidate profile, search queries, scoring weights
- `data/vacancy_monitor.db` - SQLite database (persistent, do NOT delete between runs)
- `data/browser_storage_state.json` - Playwright browser session for hh.ru

## Running

All commands use `PYTHONPATH=src python3 -m vacancy_monitor <command>`.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Lint

```bash
PYTHONPATH=src python3 -m ruff check src/
```

## Key conventions

- Python 3.10+, no ORM (raw sqlite3)
- Frozen dataclasses for all models
- `normalize_for_match()` for text comparison
- `source_family()` extracts provider name from source string
- Reports default to Russian language
