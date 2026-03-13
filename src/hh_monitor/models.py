from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VacancyTrack(str, Enum):
    RUBY = "ruby"
    AI = "ai"
    MIXED = "mixed"
    OTHER = "other"


class WorkFormat(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class SeniorityLevel(str, Enum):
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
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
class NormalizedVacancy:
    external_id: str
    source: str
    title: str
    company: str
    url: str | None
    location: str
    remote_type: WorkFormat
    employment_type: str
    salary_from: int | None
    salary_to: int | None
    salary_currency: str | None
    salary_gross: bool | None
    published_at: str | None
    description_raw: str
    requirements: str
    skills_raw: list[str]
    language_requirements: list[str]
    seniority: SeniorityLevel
    track: VacancyTrack
    normalized_text: str
    source_metadata: dict[str, Any]
    deterministic_score: int | None = None
    priority_score: float | None = None
    llm_score: float | None = None
    final_recommendation: str | None = None
    fit_summary: str | None = None
    missing_skills: list[str] = field(default_factory=list)
    cv_focus_points: list[str] = field(default_factory=list)
    interview_topics: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["remote_type"] = self.remote_type.value
        data["seniority"] = self.seniority.value
        data["track"] = self.track.value
        return data

    @property
    def salary(self) -> SalaryRange:
        return SalaryRange(
            amount_from=self.salary_from,
            amount_to=self.salary_to,
            currency=self.salary_currency,
            gross=self.salary_gross,
        )

    @property
    def work_format(self) -> WorkFormat:
        return self.remote_type

    @property
    def experience_level(self) -> str:
        return self.seniority.value

    @property
    def description(self) -> str:
        return self.description_raw

    @property
    def key_skills(self) -> list[str]:
        return self.skills_raw

    @property
    def raw_data(self) -> dict[str, Any]:
        return self.source_metadata


Vacancy = NormalizedVacancy


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
    source: str
    name: str
    text: str
    priority: int = 100
    area: int | None = None
    per_page: int = 20
    pages: int = 1
    fetch_all: bool = False
    only_with_salary: bool = False
    detailed: bool = False
    source_url: str | None = None
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
