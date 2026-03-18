from __future__ import annotations

import re
from html import unescape
from typing import Any

from vacancy_monitor.classifiers.remote_classifier import classify_remote_type
from vacancy_monitor.classifiers.seniority_classifier import classify_seniority
from vacancy_monitor.models import NormalizedVacancy, SalaryRange, VacancyTrack, WorkFormat

WHITESPACE_RE = re.compile(r"\s+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
LEGAL_SUFFIX_RE = re.compile(
    r"\b(ооо|оао|ао|зао|пао|ип|inc\.?|llc|ltd\.?|corp\.?|corporation|company|co\.?|gmbh|ag|s\.?a\.?|plc)\b",
    re.IGNORECASE,
)
NON_ALNUM_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    no_html = HTML_TAG_RE.sub(" ", unescape(value))
    return WHITESPACE_RE.sub(" ", no_html).strip()


def normalize_for_match(value: str | None) -> str:
    return normalize_text(value).lower()


def normalize_company_key(raw: str) -> str:
    """Normalize company name for cross-provider deduplication."""
    lowered = normalize_for_match(raw)
    stripped = LEGAL_SUFFIX_RE.sub("", lowered)
    cleaned = NON_ALNUM_RE.sub(" ", stripped)
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_title_key(raw: str) -> str:
    """Normalize job title for cross-provider deduplication."""
    lowered = normalize_for_match(raw)
    return WHITESPACE_RE.sub(" ", lowered).strip()


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


def vacancy_from_remoteok_payload(payload: dict[str, Any], source: str = "remoteok_api") -> NormalizedVacancy:
    title = normalize_text(payload.get("position") or payload.get("title"))
    company = normalize_text(payload.get("company"))
    location = normalize_text(payload.get("location") or payload.get("candidate_required_location") or "Remote")
    tags = [normalize_text(tag) for tag in (payload.get("tags") or []) if normalize_text(str(tag))]
    description = normalize_text(payload.get("description"))
    requirements = " ".join(tags)
    job_id = payload.get("id") or payload.get("slug") or payload.get("url") or title
    published_at = normalize_text(payload.get("date") or payload.get("iso_date")) or None
    url = payload.get("url") or payload.get("apply_url")
    if isinstance(url, str) and url.startswith("/"):
        url = f"https://remoteok.com{url}"

    salary_from = payload.get("salary_min")
    salary_to = payload.get("salary_max")
    salary_currency = None
    if salary_from is None and payload.get("salary"):
        salary_text = str(payload["salary"])
        salary_currency = "USD" if "$" in salary_text else None
    combined_text = " ".join(
        part
        for part in [
            title,
            company,
            location,
            description,
            requirements,
            " ".join(tags),
        ]
        if part
    )

    return NormalizedVacancy(
        external_id=f"remoteok:{job_id}",
        source=source,
        title=title or "Unknown title",
        company=company or "Unknown company",
        url=url,
        location=location or "Remote",
        remote_type=detect_work_format("remote", location, description, requirements),
        employment_type=normalize_text(payload.get("employment_type") or "Unknown"),
        salary_from=int(salary_from) if isinstance(salary_from, int) else None,
        salary_to=int(salary_to) if isinstance(salary_to, int) else None,
        salary_currency=salary_currency,
        salary_gross=None,
        published_at=published_at,
        description_raw=description,
        requirements=requirements,
        skills_raw=tags,
        language_requirements=[],
        seniority=classify_seniority(title, requirements),
        track=VacancyTrack.OTHER,
        normalized_text=normalize_for_match(combined_text),
        source_metadata=payload,
    )


def vacancy_from_weworkremotely_payload(payload: dict[str, Any], source: str = "weworkremotely_html") -> NormalizedVacancy:
    title = normalize_text(payload.get("title"))
    company = normalize_text(payload.get("company"))
    location = normalize_text(payload.get("location") or "Remote")
    categories = [normalize_text(item) for item in (payload.get("categories") or []) if normalize_text(str(item))]
    description = normalize_text(payload.get("description") or payload.get("requirements"))
    requirements = " ".join(categories) or description
    published_at = normalize_text(payload.get("listed_at")) or None
    job_id = payload.get("id") or payload.get("url") or title
    combined_text = " ".join(
        part for part in [title, company, location, description, requirements, " ".join(categories)] if part
    )

    return NormalizedVacancy(
        external_id=f"weworkremotely:{job_id}",
        source=source,
        title=title or "Unknown title",
        company=company or "Unknown company",
        url=payload.get("url"),
        location=location or "Remote",
        remote_type=detect_work_format("remote", location, requirements),
        employment_type="Full-Time" if any("full-time" in item.lower() for item in categories) else "Unknown",
        salary_from=None,
        salary_to=None,
        salary_currency=None,
        salary_gross=None,
        published_at=published_at,
        description_raw=description or requirements,
        requirements=requirements,
        skills_raw=categories,
        language_requirements=[],
        seniority=classify_seniority(title, f"{description} {requirements}".strip()),
        track=VacancyTrack.OTHER,
        normalized_text=normalize_for_match(combined_text),
        source_metadata=payload,
    )


def vacancy_from_remotive_payload(payload: dict[str, Any], source: str = "remotive_api") -> NormalizedVacancy:
    title = normalize_text(payload.get("title"))
    company = normalize_text(payload.get("company_name"))
    location = normalize_text(payload.get("candidate_required_location") or "Remote")
    tags = [normalize_text(str(tag)) for tag in (payload.get("tags") or []) if normalize_text(str(tag))]
    description = normalize_text(payload.get("description"))
    requirements = " ".join(tags)
    published_at = normalize_text(payload.get("publication_date")) or None
    salary_text = normalize_text(payload.get("salary"))
    salary_currency = "USD" if "$" in salary_text else None
    combined_text = " ".join(part for part in [title, company, location, description, requirements, " ".join(tags)] if part)

    return NormalizedVacancy(
        external_id=f"remotive:{payload.get('id')}",
        source=source,
        title=title or "Unknown title",
        company=company or "Unknown company",
        url=payload.get("url"),
        location=location or "Remote",
        remote_type=detect_work_format("remote", location, description, requirements),
        employment_type=normalize_text(payload.get("job_type") or "Unknown"),
        salary_from=None,
        salary_to=None,
        salary_currency=salary_currency,
        salary_gross=None,
        published_at=published_at,
        description_raw=description,
        requirements=requirements,
        skills_raw=tags,
        language_requirements=[],
        seniority=classify_seniority(title, requirements),
        track=VacancyTrack.OTHER,
        normalized_text=normalize_for_match(combined_text),
        source_metadata=payload,
    )


def vacancy_from_rabota1000_payload(payload: dict[str, Any], source: str = "rabota1000_html") -> NormalizedVacancy:
    title = normalize_text(payload.get("title"))
    company = normalize_text(payload.get("company"))
    location = normalize_text(payload.get("location"))
    description = normalize_text(payload.get("snippet"))
    salary_text = normalize_text(payload.get("salary_text"))
    source_site = normalize_text(payload.get("source_site"))
    query_job_type = normalize_text(payload.get("_query_job_type"))
    salary_from, salary_to, salary_currency = _parse_rabota1000_salary(salary_text)
    employment_type = _rabota1000_job_type_label(query_job_type) or "Unknown"
    remote_type = (
        WorkFormat.REMOTE
        if query_job_type == "6"
        else detect_work_format(employment_type, location, description, source_site)
    )
    combined_text = " ".join(
        part
        for part in [title, company, location, description, salary_text, source_site, employment_type]
        if part
    )

    return NormalizedVacancy(
        external_id=f"rabota1000:{payload.get('id') or title}",
        source=source,
        title=title or "Unknown title",
        company=company or "Unknown company",
        url=payload.get("url"),
        location=location or "Unknown location",
        remote_type=remote_type,
        employment_type=employment_type,
        salary_from=salary_from,
        salary_to=salary_to,
        salary_currency=salary_currency,
        salary_gross=None,
        published_at=normalize_text(payload.get("listed_at")) or None,
        description_raw=description or title,
        requirements=description,
        skills_raw=[],
        language_requirements=[],
        seniority=classify_seniority(title, description),
        track=VacancyTrack.OTHER,
        normalized_text=normalize_for_match(combined_text),
        source_metadata=payload,
    )


def vacancy_from_habr_payload(payload: dict[str, Any], source: str = "habr_html") -> NormalizedVacancy:
    title = normalize_text(payload.get("title"))
    company_data = payload.get("company") or {}
    company = normalize_text(company_data.get("title") if isinstance(company_data, dict) else str(company_data))
    salary = payload.get("salary") or {}
    if not isinstance(salary, dict):
        salary = {}
    skills = [
        normalize_text(skill.get("title") if isinstance(skill, dict) else str(skill))
        for skill in (payload.get("skills") or [])
        if normalize_text(skill.get("title") if isinstance(skill, dict) else str(skill))
    ]
    divisions = [
        normalize_text(division.get("title") if isinstance(division, dict) else str(division))
        for division in (payload.get("divisions") or [])
        if normalize_text(division.get("title") if isinstance(division, dict) else str(division))
    ]
    locations = [
        normalize_text(location.get("title") if isinstance(location, dict) else str(location))
        for location in (payload.get("locations") or [])
        if normalize_text(location.get("title") if isinstance(location, dict) else str(location))
    ]
    remote = bool(payload.get("remoteWork"))
    location = "Remote" if remote and not locations else ", ".join(locations) if locations else normalize_text(
        payload.get("location") or payload.get("humanCityNames") or payload.get("shortGeo")
    )
    description = normalize_text(payload.get("description") or payload.get("bannerDescription"))
    employment = normalize_text(payload.get("employmentType") or payload.get("employment"))
    qualification = normalize_text(payload.get("qualification"))
    published = payload.get("publishedDate") or {}
    published_at = normalize_text(published.get("date") if isinstance(published, dict) else str(published)) or None
    requirements = " ".join(part for part in [" ".join(divisions), " ".join(skills)] if part).strip()
    combined_text = " ".join(
        part
        for part in [title, company, location, description, requirements, " ".join(skills), " ".join(divisions), qualification]
        if part
    )

    return NormalizedVacancy(
        external_id=f"habr:{payload.get('id')}",
        source=source,
        title=title or "Unknown title",
        company=company or "Unknown company",
        url=payload.get("url"),
        location=location or "Remote",
        remote_type=detect_work_format("remote" if remote else "", location, description, requirements),
        employment_type=employment or "Unknown",
        salary_from=salary.get("from") if isinstance(salary.get("from"), int) else None,
        salary_to=salary.get("to") if isinstance(salary.get("to"), int) else None,
        salary_currency=normalize_text(str(salary.get("currency") or "")).upper() or None,
        salary_gross=None,
        published_at=published_at,
        description_raw=description,
        requirements=requirements or description,
        skills_raw=skills + [item for item in divisions if item not in skills],
        language_requirements=[],
        seniority=classify_seniority(title, f"{qualification} {description}".strip()),
        track=VacancyTrack.OTHER,
        normalized_text=normalize_for_match(combined_text),
        source_metadata=payload,
    )


def _parse_rabota1000_salary(value: str) -> tuple[int | None, int | None, str | None]:
    normalized = normalize_text(value).replace("\u202f", " ").replace("\xa0", " ")
    if not normalized or normalized.lower() == "договорная":
        return None, None, None

    currency = None
    lowered = normalized.lower()
    if "руб" in lowered or "₽" in normalized:
        currency = "RUR"
    elif "$" in normalized:
        currency = "USD"
    elif "€" in normalized:
        currency = "EUR"

    numbers = [int(match.replace(" ", "")) for match in re.findall(r"\d[\d ]*", normalized)]
    if not numbers:
        return None, None, currency
    if "от" in lowered:
        return numbers[0], numbers[1] if len(numbers) > 1 else None, currency
    if "до" in lowered:
        return (numbers[0], numbers[1], currency) if len(numbers) > 1 else (None, numbers[0], currency)
    if len(numbers) >= 2:
        return numbers[0], numbers[1], currency
    return numbers[0], None, currency


def _rabota1000_job_type_label(value: str) -> str | None:
    if not value:
        return None
    mapping = {
        "1": "Полная занятость",
        "6": "Удаленная работа",
    }
    return mapping.get(value) or value
