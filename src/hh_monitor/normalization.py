from __future__ import annotations

from html import unescape
import re
from typing import Any

from hh_monitor.keywords import HYBRID_KEYWORDS, ONSITE_KEYWORDS, REMOTE_KEYWORDS
from hh_monitor.models import SalaryRange, Vacancy, WorkFormat


WHITESPACE_RE = re.compile(r"\s+")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    no_html = HTML_TAG_RE.sub(" ", unescape(value))
    return WHITESPACE_RE.sub(" ", no_html).strip()


def normalize_for_match(value: str | None) -> str:
    return normalize_text(value).lower()


def parse_salary(payload: dict[str, Any]) -> SalaryRange:
    salary = payload.get("salary") or {}
    return SalaryRange(
        amount_from=salary.get("from"),
        amount_to=salary.get("to"),
        currency=salary.get("currency"),
        gross=salary.get("gross"),
    )


def extract_skills(payload: dict[str, Any]) -> list[str]:
    raw_skills = payload.get("key_skills") or []
    skills: list[str] = []
    for item in raw_skills:
        if isinstance(item, dict) and item.get("name"):
            skills.append(str(item["name"]))
        elif isinstance(item, str):
            skills.append(item)
    return skills


def detect_work_format(*values: str) -> WorkFormat:
    text = " ".join(normalize_for_match(value) for value in values if value)
    if any(keyword in text for keyword in REMOTE_KEYWORDS):
        return WorkFormat.REMOTE
    if any(keyword in text for keyword in HYBRID_KEYWORDS):
        return WorkFormat.HYBRID
    if any(keyword in text for keyword in ONSITE_KEYWORDS):
        return WorkFormat.ONSITE
    return WorkFormat.UNKNOWN


def vacancy_from_payload(payload: dict[str, Any], source: str = "json_import") -> Vacancy:
    title = normalize_text(payload.get("name"))
    snippet = payload.get("snippet") or {}
    snippet_requirement = normalize_text(snippet.get("requirement"))
    snippet_responsibility = normalize_text(snippet.get("responsibility"))
    description = normalize_text(payload.get("description")) or " ".join(
        part for part in [snippet_responsibility, snippet_requirement] if part
    ).strip()
    requirements = normalize_text(payload.get("requirements") or snippet.get("requirement"))
    responsibility = snippet_responsibility
    company = normalize_text((payload.get("employer") or {}).get("name"))
    location = normalize_text((payload.get("area") or {}).get("name"))
    schedule = normalize_text((payload.get("schedule") or {}).get("name"))
    employment = normalize_text((payload.get("employment") or {}).get("name"))
    experience = normalize_text((payload.get("experience") or {}).get("name"))
    skills = extract_skills(payload)
    combined_text = " ".join(
        part
        for part in [title, description, requirements, responsibility, " ".join(skills), company, location, schedule]
        if part
    )

    return Vacancy(
        external_id=str(payload.get("id") or payload.get("vacancy_id") or title),
        source=source,
        title=title,
        company=company or "Unknown company",
        url=payload.get("alternate_url") or payload.get("url"),
        salary=parse_salary(payload),
        location=location or "Unknown location",
        work_format=detect_work_format(schedule, employment, location, description, responsibility),
        employment_type=employment or "Unknown",
        experience_level=experience or "Unknown",
        description=description,
        requirements=requirements or responsibility,
        key_skills=skills,
        normalized_text=normalize_for_match(combined_text),
        raw_data=payload,
    )
