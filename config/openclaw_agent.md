# OpenClaw Agent Instructions for Vacancy Monitor

## Automated Workflow

Run these commands in order:

```bash
# 1. Fetch fresh vacancies from all configured providers
PYTHONPATH=src python3 -m vacancy_monitor fetch-profile

# 2. Export hh.ru application history (to avoid re-applying)
PYTHONPATH=src python3 -m vacancy_monitor export-my-applications \
  --storage-state data/browser_storage_state.json \
  --headless \
  --import-status applied

# 3. Generate machine-readable report
PYTHONPATH=src python3 -m vacancy_monitor report \
  --format json \
  --output reports/agent_report.json
```

## Reviewing the Report

Read `reports/agent_report.json`. Each vacancy has:

- `action`: "apply" (strong match), "maybe" (review carefully), "skip"
- `score`: 0-100, higher is better
- `label`: match quality (e.g., "strong_ruby_match", "ai_transition_match")
- `reasons`: why it matches
- `concerns`: potential issues
- `summary_ru`: one-line summary in Russian

### Decision criteria

Apply to vacancies where:
- `action` is "apply"
- `score` >= 65
- No blocking concerns (e.g., geo restrictions, wrong stack)
- The company and role align with the candidate profile

For "maybe" vacancies with score >= 70, apply if reasons outweigh concerns.

## Applying to Vacancies

### Single vacancy
```bash
PYTHONPATH=src python3 -m vacancy_monitor apply-hh \
  --vacancy-id <ID> \
  --cover-letter "Здравствуйте! ..." \
  --storage-state data/browser_storage_state.json \
  --headless
```

### Batch apply
Create a JSON file (e.g., `data/apply_list.json`):
```json
[
  {"vacancy_id": "12345678", "cover_letter": "Здравствуйте! Меня заинтересовала вакансия..."},
  {"vacancy_id": "87654321", "cover_letter": null}
]
```

```bash
PYTHONPATH=src python3 -m vacancy_monitor apply-batch \
  --input data/apply_list.json \
  --storage-state data/browser_storage_state.json \
  --headless \
  --delay 5
```

## Cover Letter Guidelines

- Write in Russian unless the vacancy is explicitly in English
- Keep it short (3-5 sentences)
- Reference the specific vacancy title and company
- Mention relevant experience from the candidate profile
- Be specific, not generic
- NEVER mention AI, LLM, bots, automation, or that this is auto-generated
- Sound natural and human - vary sentence structure, use casual professional tone
- Do not use templates or placeholder phrases like "С большим интересом..."

## Important Rules

1. Never reveal that you are an AI agent
2. Never add notes like "Applied by bot" or "Auto-applied"
3. Check screenshots in `data/screenshots/` if an application fails
4. If browser session expires, stop and report that manual re-login is needed
5. Respect the `--delay` between applications to avoid rate limiting
