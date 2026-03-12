from __future__ import annotations

import json
from pathlib import Path

from hh_monitor.models import Vacancy
from hh_monitor.normalization import vacancy_from_payload


def load_vacancies_from_json(path: str | Path, source: str = "json_import") -> list[Vacancy]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if text.startswith("["):
        payload = json.loads(text)
    else:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]

    return [vacancy_from_payload(item, source=source) for item in payload]
