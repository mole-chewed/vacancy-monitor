from __future__ import annotations

from hh_monitor.models import SeniorityLevel


def _normalize_for_match(value: str | None) -> str:
    return (value or "").strip().lower()


def classify_seniority(title: str | None, experience_text: str | None) -> SeniorityLevel:
    text = " ".join(part for part in [_normalize_for_match(title), _normalize_for_match(experience_text)] if part)
    if any(term in text for term in ["lead", "team lead", "tech lead", "руководитель", "ведущий"]):
        return SeniorityLevel.LEAD
    if any(term in text for term in ["senior", "старший", "более 6", "6+ years", "5+ years"]):
        return SeniorityLevel.SENIOR
    if any(term in text for term in ["middle", "mid", "3-6 years", "1-3 года", "3-6 лет"]):
        return SeniorityLevel.MIDDLE
    if any(term in text for term in ["junior", "стажер", "intern", "trainee", "jun+"]):
        return SeniorityLevel.JUNIOR
    return SeniorityLevel.UNKNOWN
