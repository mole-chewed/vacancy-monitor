# Vacancy Monitor

Python CLI for collecting vacancies from several public sources, normalizing them into one schema, ranking them with deterministic rules, and optionally generating a short OpenAI-assisted application report.

## What it does

- imports vacancies from `hh`, `habr`, `rabota1000`, `remotive`, `remoteok`, `weworkremotely`, or local JSON
- stores everything in local SQLite
- ranks vacancies for Ruby-first and AI-transition searches
- excludes vacancies you already marked or imported from hh.ru application history
- can generate a markdown report from the ranked shortlist

The core design is intentionally simple:

- deterministic scoring and filtering first
- optional LLM reporting second
- local SQLite storage instead of external services

## Project layout

```text
.
├── .env.example
├── config/
│   ├── ignored_vacancies.example/
│   └── profile.example.toml
├── data/
│   ├── sample_hh_responses.html
│   └── sample_vacancies.json
├── reports/
├── src/vacancy_monitor/
└── tests/
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
cp config/profile.example.toml config/profile.toml
cp -R config/ignored_vacancies.example config/ignored_vacancies
```

Edit `config/profile.toml` for your own search strategy, report defaults, and hh.ru application history URL.

## Main commands

```bash
PYTHONPATH=src python3 -m vacancy_monitor init-db
PYTHONPATH=src python3 -m vacancy_monitor list-searches
PYTHONPATH=src python3 -m vacancy_monitor fetch-profile
PYTHONPATH=src python3 -m vacancy_monitor fetch-profile --source hh
PYTHONPATH=src python3 -m vacancy_monitor import-json --input data/sample_vacancies.json
PYTHONPATH=src python3 -m vacancy_monitor import-ui-history --input data/sample_hh_responses.html
PYTHONPATH=src python3 -m vacancy_monitor export-my-applications
PYTHONPATH=src python3 -m vacancy_monitor rank --top 20
PYTHONPATH=src python3 -m vacancy_monitor report
PYTHONPATH=src python3 -m vacancy_monitor history
```

Provider-specific ad hoc fetch commands are also available:

- `fetch-hh`
- `fetch-habr`
- `fetch-rabota1000`
- `fetch-remotive`
- `fetch-remoteok`
- `fetch-weworkremotely`

Run `PYTHONPATH=src python3 -m vacancy_monitor --help` for the full CLI.

## Typical workflow

1. Initialize the database: `PYTHONPATH=src python3 -m vacancy_monitor init-db`
2. Review configured searches: `PYTHONPATH=src python3 -m vacancy_monitor list-searches`
3. Fetch vacancies: `PYTHONPATH=src python3 -m vacancy_monitor fetch-profile`
4. Import or export hh.ru application history if you want applied roles excluded
5. Inspect ranking: `PYTHONPATH=src python3 -m vacancy_monitor rank --top 20`
6. Generate the final report: `PYTHONPATH=src python3 -m vacancy_monitor report`

## Daily flow

Use this every day when you want fresh data from all configured providers and an updated final report.

If you already have a valid `data/browser_storage_state.json`, run:

```bash
source .venv/bin/activate

PYTHONPATH=src python3 -m vacancy_monitor fetch-profile

PYTHONPATH=src python3 -m vacancy_monitor export-my-applications \
  --output data/applications_export.html \
  --storage-state data/browser_storage_state.json \
  --headless \
  --import-status applied

PYTHONPATH=src python3 -m vacancy_monitor rank --top 20

PYTHONPATH=src python3 -m vacancy_monitor report
```

If you need to log in again and refresh the saved browser session, use:

```bash
source .venv/bin/activate

PYTHONPATH=src python3 -m vacancy_monitor fetch-profile

PYTHONPATH=src python3 -m vacancy_monitor export-my-applications \
  --output data/applications_export.html \
  --login-wait-seconds 120 \
  --save-storage-state data/browser_storage_state.json \
  --import-status applied

PYTHONPATH=src python3 -m vacancy_monitor rank --top 20

PYTHONPATH=src python3 -m vacancy_monitor report
```

Notes:

- `fetch-profile` pulls fresh vacancies from all enabled providers in `config/profile.toml`
- `export-my-applications` updates hh.ru application history so already-applied roles are excluded
- `rank --top 20` is optional, but useful as a quick review step before the final report
- `report` reads from the local database and generates the final markdown report

## Configuration

`config/profile.toml` controls:

- candidate summary and language
- remote and location preferences
- salary targets
- ranking weights
- per-source search queries under `[search.*]`
- default paths for report output and hh.ru history export

`.env` controls runtime settings such as:

- `APP_DB_PATH`
- `OPENAI_API_KEY`
- `OPENAI_REPORT_MODEL`
- API base URLs and user-agent overrides

`config/ignored_vacancies/*.txt` lets you suppress vacancy ids by source family.

## Optional features

### OpenAI report

`report` needs `OPENAI_API_KEY` and a CV PDF path. The application first builds a deterministic shortlist, then sends bounded evidence to OpenAI to produce a markdown report.

### Playwright export

`export-ui-history` and `export-my-applications` use Playwright to export the hh.ru applications page.

If you want to use that path:

```bash
pip install -r requirements.txt
python3 -m playwright install chromium
```

Then run:

```bash
PYTHONPATH=src python3 -m vacancy_monitor export-my-applications \
  --output data/applications_export.html \
  --login-wait-seconds 120 \
  --save-storage-state data/browser_storage_state.json \
  --import-status applied
```

## Privacy notes

- `.env`, `config/profile.toml`, `config/ignored_vacancies/`, runtime `data/*`, and generated `reports/*` are git-ignored
- the tracked examples are placeholders and should be safe to publish
- if you use `export-my-applications`, the exported HTML and browser storage state are runtime files and should stay untracked

## Development

```bash
python3 -m unittest discover -s tests -q
ruff check .
mypy
```
