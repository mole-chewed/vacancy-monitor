from __future__ import annotations

from html import unescape
import re
from typing import Any

from hh_monitor.classifiers.remote_classifier import classify_remote_type
from hh_monitor.classifiers.seniority_classifier import classify_seniority
from hh_monitor.models import NormalizedVacancy, SalaryRange, VacancyTrack, WorkFormat


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
    return classify_remote_type(*values)


def extract_language_requirements(payload: dict[str, Any]) -> list[str]:
    languages = payload.get("languages") or []
    extracted: list[str] = []
    for item in languages:
        if isinstance(item, dict) and item.get("name"):
            extracted.append(normalize_text(item["name"]))
        elif isinstance(item, str):
            extracted.append(normalize_text(item))
    return [item for item in extracted if item]


def vacancy_from_payload(payload: dict[str, Any], source: str = "json_import") -> NormalizedVacancy:
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
    salary = parse_salary(payload)
    skills = extract_skills(payload)
    language_requirements = extract_language_requirements(payload)
    published_at = normalize_text(payload.get("published_at")) or None
    combined_text = " ".join(
        part
        for part in [
            title,
            description,
            requirements,
            responsibility,
            " ".join(skills),
            company,
            location,
            schedule,
            " ".join(language_requirements),
        ]
        if part
    )

    return NormalizedVacancy(
        external_id=str(payload.get("id") or payload.get("vacancy_id") or title),
        source=source,
        title=title,
        company=company or "Unknown company",
        url=payload.get("alternate_url") or payload.get("url"),
        location=location or "Unknown location",
        remote_type=detect_work_format(schedule, employment, location, description, responsibility),
        employment_type=employment or "Unknown",
        salary_from=salary.amount_from,
        salary_to=salary.amount_to,
        salary_currency=salary.currency,
        salary_gross=salary.gross,
        published_at=published_at,
        description_raw=description,
        requirements=requirements or responsibility,
        skills_raw=skills,
        language_requirements=language_requirements,
        seniority=classify_seniority(title, experience),
        track=VacancyTrack.OTHER,
        normalized_text=normalize_for_match(combined_text),
        source_metadata=payload,
    )
