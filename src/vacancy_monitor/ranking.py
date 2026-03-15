from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from vacancy_monitor.config import CandidateProfile, vacancy_is_ignored
from vacancy_monitor.models import ApplicationStatus, RankedVacancy, Vacancy, VacancyAnalysis, VacancyTrack
from vacancy_monitor.scoring import analyze_vacancy


def build_ranked_vacancies(
    vacancies: list[Vacancy],
    *,
    profile: CandidateProfile,
    statuses: dict[str, ApplicationStatus],
) -> list[RankedVacancy]:
    ranked: list[RankedVacancy] = []
    for vacancy in vacancies:
        if vacancy_is_ignored(profile, vacancy):
            continue
        analysis = analyze_vacancy(vacancy, profile)
        if analysis.track not in {VacancyTrack.RUBY, VacancyTrack.MIXED, VacancyTrack.AI}:
            continue
        ranked_item = RankedVacancy(
            vacancy=_enrich_vacancy(vacancy, analysis, profile),
            analysis=analysis,
            application_status=statuses.get(vacancy.external_id, ApplicationStatus.NEW),
        )
        if not should_keep_ranked_vacancy(ranked_item):
            continue
        ranked.append(ranked_item)

    ranked.sort(
        key=lambda item: (
            item.analysis.priority_bucket,
            -float(item.vacancy.priority_score or 0.0),
            -item.analysis.score,
            item.vacancy.title.lower(),
        )
    )
    return ranked


def should_keep_ranked_vacancy(item: RankedVacancy) -> bool:
    analysis = item.analysis
    title = item.vacancy.title.lower()
    red_flags = set(analysis.red_flags)

    hard_skip_red_flags = {
        "hard-excluded-ml-research",
        "automation-only",
        "architect-heavy",
        "frontend-heavy",
        "product-heavy",
        "org-leadership-heavy",
        "data-science-heavy",
        "qa-heavy",
        "legacy-stack-heavy",
        "education-heavy",
        "evangelist-heavy",
        "strong-python-background-required",
    }
    if red_flags & hard_skip_red_flags:
        return False

    if analysis.track == VacancyTrack.AI:
        title_exclusions = [
            "python",
            "analyst",
            "аналитик",
            "rpa",
            "no-code",
            "no code",
            "no - code",
            "low-code",
            "low code",
            "low - code",
            "automation",
            "автоматизац",
            "automation specialist",
            "automation lead",
            "руководитель",
            "tech lead",
            "lead ",
            "fullstack",
            "full stack",
        ]
        if any(term in title for term in title_exclusions):
            return False

        backend_terms = set(analysis.matched_keywords.get("backend", []))
        backend_focused_title_terms = [
            "backend",
            "back-end",
            "platform",
            "integration",
            "integrations",
            "api",
            "бэкенд",
            "интеграц",
            "llm integration",
            "ai backend",
            "genai engineer",
            "llm engineer",
            "rag engineer",
        ]
        if backend_terms:
            return True
        if any(term in title for term in backend_focused_title_terms):
            return True
        return False

    return True


def _enrich_vacancy(vacancy: Vacancy, analysis: VacancyAnalysis, profile: CandidateProfile) -> Vacancy:
    priority_score = calculate_priority_score(vacancy, analysis, profile)
    return replace(
        vacancy,
        track=analysis.track,
        deterministic_score=analysis.score,
        priority_score=priority_score,
        final_recommendation=analysis.action.value,
        fit_summary=analysis.summary_ru,
    )


def calculate_priority_score(vacancy: Vacancy, analysis: VacancyAnalysis, profile: CandidateProfile) -> float:
    return (
        analysis.score * _track_weight(analysis.track, profile)
        + _freshness_bonus(vacancy)
        + _compensation_bonus(vacancy, profile)
        + _seniority_bonus(vacancy)
    )


def _track_weight(track: VacancyTrack, profile: CandidateProfile) -> float:
    if track == profile.ranking.primary_track:
        return profile.ranking.primary_track_weight
    if track == VacancyTrack.MIXED:
        return profile.ranking.mixed_track_weight
    return profile.ranking.secondary_track_weight


def _freshness_bonus(vacancy: Vacancy) -> float:
    if not vacancy.published_at:
        return 0.0
    try:
        published = datetime.fromisoformat(vacancy.published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - published).days, 0)
    if age_days <= 1:
        return 6.0
    if age_days <= 3:
        return 4.0
    if age_days <= 7:
        return 2.0
    return 0.0


def _compensation_bonus(vacancy: Vacancy, profile: CandidateProfile) -> float:
    top = vacancy.salary_to or vacancy.salary_from
    if top is None:
        return 0.0
    if top >= profile.salary.target:
        return 6.0
    if top >= profile.salary.minimum:
        return 3.0
    return -2.0


def _seniority_bonus(vacancy: Vacancy) -> float:
    if vacancy.seniority.value in {"senior", "lead"}:
        return 4.0
    if vacancy.seniority.value == "middle":
        return 1.0
    return -2.0
