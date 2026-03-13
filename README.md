# hh.ru Vacancy Monitor MVP

Python CLI application for importing hh.ru vacancies, classifying them into AI / Ruby / Other tracks, scoring them with AI-first priority, excluding already-applied roles, and saving results locally in SQLite.

## Why this shape

- Deterministic first: explicit rules drive track classification and ranking.
- SQLite first: local, simple, and enough for an MVP with application history.
- CLI first: easier to iterate on ingestion, scoring, and manual review.
- Extensible: optional LLM summary can be added later without replacing core logic.

## Architecture

Core modules:

- `config.py`: loads TOML profile config and environment variables
- `models.py`: typed domain models and enums
- `keywords.py`: Russian and English keyword dictionaries
- `normalization.py`: salary, work format, seniority, skills, and text normalization
- `classifier.py`: AI / Ruby / Other track decision
- `scoring.py`: fit scoring with AI-first ranking bands
- `storage.py`: SQLite schema, persistence, application history, ranking runs
- `sources/hh_api.py`: hh.ru search ingestion
- `sources/json_import.py`: local JSON / JSONL ingestion
- `cli.py`: user-facing commands

Public API boundary today:

- supported: public hh.ru vacancy search and vacancy details
- not yet supported: account-specific data sync
- supported fallback: import applied-history from saved hh.ru UI HTML or exported JSON
- future fallback: add optional browser automation only for gaps that require live session control

## Proposed folder structure

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── config/
│   └── profile.example.toml
├── data/
│   └── sample_vacancies.json
├── src/
│   └── hh_monitor/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── keywords.py
│       ├── normalization.py
│       ├── classifier.py
│       ├── scoring.py
│       ├── storage.py
│       ├── summaries.py
│       └── sources/
│           ├── __init__.py
│           ├── hh_api.py
│           └── json_import.py
└── tests/
    ├── test_classifier.py
    ├── test_scoring.py
    └── test_storage.py
```

## MVP commands

```bash
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db init-db
PYTHONPATH=src python -m hh_monitor.cli list-searches
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db fetch-hh-profile
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db fetch-hh --text "GenAI backend"
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db import-ui-history --input data/sample_hh_responses.html
PYTHONPATH=src python -m hh_monitor.cli export-ui-history --url "https://hh.ru/applicant/negotiations" --output data/hh_responses_live.html --import-status applied
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db export-my-applications --output data/hh_applied_history.html --import-status applied
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db import-json --input data/sample_vacancies.json
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db rank --top 20
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db report --output data/application_report.md
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db mark --vacancy-id genai-backend-001 --status applied
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db history
```

## End-to-End Workflow

Run the application in this order when you want fresh data and a new report:

1. Initialize the database once:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db init-db
```

2. Inspect the profile-driven hh.ru public API searches:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli list-searches
```

3. Optionally add vacancy ids you never want to see again to `config/ignored_vacancy_ids.txt`:

```text
# one hh.ru vacancy id per line
131083362
130438587
```

4. Pull fresh vacancies from hh.ru public API using the configured profile searches:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db fetch-hh-profile
```

This now fetches all hh.ru result pages for the configured profile searches, not just the first 40 vacancies per direction.
The shipped profile uses `fetch_all = true`, `per_page = 100`, and avoids per-vacancy detail requests on the broad search stage to reduce captcha/rate-limit issues.
After that, the `report` command performs a second-stage hydration for the top shortlist and fetches full vacancy details only for those likely finalists.

5. Refresh your already-applied vacancies from hh.ru UI so they are excluded from ranking:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db export-my-applications \
  --output data/hh_applied_history.html \
  --storage-state data/hh_storage_state.json \
  --login-wait-seconds 0 \
  --import-status applied
```

6. Generate the final OpenAI report from the local DB, your profile config, and your CV PDF:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db report \
  --cv-path data/Alexander_Kharitonov_CV_ENG_2026.pdf \
  --hydrate-top 20 \
  --top-apply 5 \
  --top-maybe 5 \
  --top-skip 2 \
  --output data/application_report.md
```

Notes about this flow:

- `fetch-hh-profile` pulls vacancies from hh.ru public API using the search groups in `config/profile.toml`
- vacancy ids listed in `config/ignored_vacancy_ids.txt` are skipped during import and excluded from ranking/report even if they already exist in SQLite
- the broad hh.ru profile searches now exhaust all result pages instead of stopping at `pages = 2`
- `export-my-applications` updates local application history from the hh.ru UI and excludes those vacancies from later ranking
- `report` does not pull fresh hh.ru data itself; it works from the local SQLite DB and sends prepared evidence to OpenAI
- the report now uses only remote vacancies and only AI/Ruby-track vacancies before sending them to OpenAI
- ML research, model-training, computer-vision, diffusion, architect, Python-title-heavy, and automation-only roles are deterministically excluded before report generation

For package imports without installation:

```bash
PYTHONPATH=src python -m hh_monitor.cli --help
```

## Configuration

Copy `config/profile.example.toml` to `config/profile.toml` and adjust:

- target role preferences
- remote / location preferences
- keyword weights
- salary expectations
- hh.ru public API search groups under `[search.*]`
- local ignored vacancy ids file under `[files].ignored_vacancy_ids_path`

Environment variables live in `.env`.

The example profile already defines:

- `ai_primary`
- `ai_transition`
- `ruby_primary`
- `hh.applicant_history_url`
- `files.ignored_vacancy_ids_path`

Those are fetched in priority order via `fetch-hh-profile`.

The repository includes:

- [profile.example.toml](/Users/sashah/p/hh-positions-validation/config/profile.example.toml)
- [ignored_vacancy_ids.example.txt](/Users/sashah/p/hh-positions-validation/config/ignored_vacancy_ids.example.txt)

Your local editable ignore file is:

- `config/ignored_vacancy_ids.txt`
- one vacancy id per line
- `#` comments are allowed

## UI Fallback

For account-only data such as your applied-history:

1. Open the hh.ru responses/history page in the browser
2. Save the page as HTML, or export the relevant XHR payload as JSON
3. Import it with:

```bash
PYTHONPATH=src python -m hh_monitor.cli --db-path data/hh_monitor.db import-ui-history --input path/to/file.html
```

Current UI fallback behavior:

- extracts vacancy ids and titles from saved hh.ru HTML links
- accepts JSON exports that contain vacancy ids or vacancy URLs
- creates placeholder vacancies when the vacancy is not yet in local storage
- marks imported items as `applied` by default

## Playwright Export

Optional browser automation path for exporting hh.ru history pages directly:

1. Install dependencies:

```bash
pip install -r requirements.txt
python3 -m playwright install chromium
```

2. Run a headed export and allow time for manual login:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db export-my-applications \
  --output data/hh_responses_live.html \
  --login-wait-seconds 120 \
  --save-storage-state data/hh_storage_state.json \
  --import-status applied
```

3. Reuse the saved session later:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db export-my-applications \
  --output data/hh_responses_live.html \
  --storage-state data/hh_storage_state.json \
  --headless \
  --import-status applied
```

Notes:

- default URL comes from `[hh].applicant_history_url` in your profile and currently points to `https://simferopol.hh.ru/applicant/negotiations`
- `export-ui-history` still exists if you want to pass a different page URL explicitly
- `--import-status` immediately syncs the exported HTML into SQLite
- `export-my-applications` replaces stale negotiations rows by default; pass `--no-sync-missing` if you want append/update behavior only
- `--user-data-dir` can be used instead of storage-state if you prefer a persistent browser profile
- the exporter saves an HTML file and a sidecar metadata JSON file

## Application Report

Generate a markdown report via OpenAI after the deterministic pipeline prepares ranked evidence:

```bash
PYTHONPATH=src python3 -m hh_monitor.cli --db-path data/hh_monitor.db report \
  --cv-path data/Alexander_Kharitonov_CV_ENG_2026.pdf \
  --hydrate-top 20 \
  --top-apply 5 \
  --top-maybe 5 \
  --top-skip 2 \
  --output data/application_report.md
```

The report includes:

- OpenAI analysis over all prepared remote-only vacancies
- your CV text extracted from the provided PDF
- full vacancy descriptions and requirements pushed into the OpenAI prompt
- apply-now vacancies in priority order
- manual-review vacancies that may still be worth checking
- skipped vacancies as a low-attention log
- vacancy links, not just ids
- salary expectations and risks

Requirements:

- `OPENAI_API_KEY` must be set
- `OPENAI_REPORT_MODEL` controls which model is used and defaults to `gpt-5`
- deterministic score/label are sent as advisory evidence, but the final report text and prioritization come from OpenAI
- the report is built from remote-only vacancies and only `ai` / `ruby` tracks
- before sending evidence to OpenAI, the app refreshes the top `--hydrate-top` vacancies through the hh.ru detail endpoint for better descriptions and requirements
- the OpenAI request now sends a bounded payload in a single request: a compact shortlist plus a detailed shortlist sized from `--top-apply`, `--top-maybe`, and `--top-skip`

Option meanings:

- `--hydrate-top 20` fetches full hh.ru vacancy details only for the top 20 ranked vacancies before sending the shortlist to OpenAI
- `--top-apply 5` includes up to 5 vacancies whose deterministic action is `apply`
- `--top-maybe 5` includes up to 5 vacancies whose deterministic action is `maybe`
- `--top-skip 2` includes up to 2 vacancies whose deterministic action is `skip`

Recommended interpretation:

- `--hydrate-top` controls detail enrichment from hh.ru
- `--top-apply`, `--top-maybe`, and `--top-skip` control how many vacancies from each decision bucket are included in the final OpenAI report
- for larger reports, increase these numbers gradually; with the current dataset this conservative set is the safest default

## Ranking design

Two-layer decision:

1. Track classification: `ai`, `ruby`, `other`
2. Fit scoring inside the track

Final rank order:

1. Strong AI Match
2. AI Transition Match
3. Moderate AI Match
4. Strong Ruby Match
5. Moderate Ruby Match
6. Possible Match
7. Skip

Additional deterministic exclusions:

- ML research / model training / deep learning roles
- computer vision / diffusion / ComfyUI / image-video pipeline roles
- architect-heavy roles
- Python-title-heavy roles that are not realistic transition matches
- automation-only / no-code / low-code roles without enough backend depth

Current duplicate handling:

- upsert by `external_id`
- repeated imports update the stored vacancy instead of duplicating it
- TODO: add fuzzy duplicate detection for re-posted vacancies with new ids

## Tests

```bash
python3 -m unittest discover -s tests -q
```

Current verification:

- deterministic ranking tests
- SQLite persistence tests
- hh.ru API client request/response parsing with mocked HTTP responses
- UI history HTML/JSON parsing tests
- CLI exporter error-path test

Additional manual verification completed:

- live hh.ru public API fetch and local storage of 10 vacancies
- mixed AI and Ruby ranking on real hh.ru data
- UI history import into SQLite from sample saved HTML

## Future LLM TODOs

- Generate Russian explanations from deterministic evidence
- Resolve ambiguous AI-vs-product roles with a secondary opinion layer
- Learn from manual outcomes (`applied`, `interview`, `rejected`) without replacing rule-based ranking
