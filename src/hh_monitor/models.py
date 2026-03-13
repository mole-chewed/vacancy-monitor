from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VacancyTrack(str, Enum):
    AI = "ai"
    RUBY = "ruby"
    OTHER = "other"


class WorkFormat(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class MatchLabel(str, Enum):
    STRONG_AI = "strong_ai_match"
    AI_TRANSITION = "ai_transition_match"
    MODERATE_AI = "moderate_ai_match"
    STRONG_RUBY = "strong_ruby_match"
    MODERATE_RUBY = "moderate_ruby_match"
    POSSIBLE = "possible_match"
    SKIP = "skip"


class RecommendedAction(str, Enum):
    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


class ApplicationStatus(str, Enum):
    NEW = "new"
    APPLIED = "applied"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    IGNORE = "ignore"
    SAVED = "saved"


@dataclass(frozen=True)
class SalaryRange:
    amount_from: int | None
    amount_to: int | None
    currency: str | None
    gross: bool | None = None

    def display(self) -> str:
        if self.amount_from is None and self.amount_to is None:
            return "not specified"
        if self.amount_from is not None and self.amount_to is not None:
            return f"{self.amount_from}-{self.amount_to} {self.currency or ''}".strip()
        if self.amount_from is not None:
            return f"from {self.amount_from} {self.currency or ''}".strip()
        return f"up to {self.amount_to} {self.currency or ''}".strip()


@dataclass(frozen=True)
class Vacancy:
    external_id: str
    source: str
    title: str
    company: str
    url: str | None
    salary: SalaryRange
    location: str
    work_format: WorkFormat
    employment_type: str
    experience_level: str
    description: str
    requirements: str
    key_skills: list[str]
    normalized_text: str
    raw_data: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["work_format"] = self.work_format.value
        return data


@dataclass(frozen=True)
class TrackAssessment:
    track: VacancyTrack
    ai_signal: int
    ruby_signal: int
    backend_signal: int
    product_signal: int
    org_leadership_signal: int
    frontend_signal: int
    legacy_stack_signal: int
    research_signal: int
    data_science_signal: int
    qa_signal: int
    education_signal: int
    evangelist_signal: int
    python_strict_signal: int
    automation_signal: int
    matched_keywords: dict[str, list[str]]
    red_flags: list[str]


@dataclass(frozen=True)
class VacancyAnalysis:
    vacancy_id: str
    track: VacancyTrack
    score: int
    priority_bucket: int
    label: MatchLabel
    action: RecommendedAction
    reasons: list[str]
    concerns: list[str]
    matched_keywords: dict[str, list[str]]
    red_flags: list[str]
    expected_salary: str
    summary_ru: str
    generated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["track"] = self.track.value
        data["label"] = self.label.value
        data["action"] = self.action.value
        return data


@dataclass(frozen=True)
class ApplicationRecord:
    vacancy_id: str
    status: ApplicationStatus
    note: str | None
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class RankedVacancy:
    vacancy: Vacancy
    analysis: VacancyAnalysis
    application_status: ApplicationStatus


@dataclass(frozen=True)
class UiApplicationEntry:
    vacancy_id: str
    url: str | None
    title: str
    company: str | None
    status: ApplicationStatus
    note: str | None = None


@dataclass(frozen=True)
class SearchQuery:
    name: str
    text: str
    priority: int = 100
    area: int | None = None
    per_page: int = 20
    pages: int = 1
    fetch_all: bool = False
    only_with_salary: bool = False
    detailed: bool = False
    search_field: str | None = None
    experience: str | None = None
    employment: str | None = None
    schedule: str | None = None
    order_by: str | None = None
    label: str | None = None

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "text": self.text,
            "per_page": self.per_page,
            "page": 0,
        }
        if self.area is not None:
            params["area"] = self.area
        if self.only_with_salary:
            params["only_with_salary"] = True
        if self.search_field:
            params["search_field"] = self.search_field
        if self.experience:
            params["experience"] = self.experience
        if self.employment:
            params["employment"] = self.employment
        if self.schedule:
            params["schedule"] = self.schedule
        if self.order_by:
            params["order_by"] = self.order_by
        return params
