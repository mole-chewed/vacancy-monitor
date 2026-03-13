from __future__ import annotations

from hh_monitor.classifier import classify_vacancy
from hh_monitor.config import CandidateProfile
from hh_monitor.models import MatchLabel, RecommendedAction, Vacancy, VacancyAnalysis, VacancyTrack, WorkFormat
from hh_monitor.summaries import build_expected_salary, build_summary_ru


def _clamp_score(value: int) -> int:
    return max(0, min(100, value))


def _priority_bucket(label: MatchLabel) -> int:
    order = {
        MatchLabel.STRONG_RUBY: 1,
        MatchLabel.MODERATE_RUBY: 2,
        MatchLabel.STRONG_AI: 3,
        MatchLabel.AI_TRANSITION: 4,
        MatchLabel.MODERATE_AI: 5,
        MatchLabel.POSSIBLE: 6,
        MatchLabel.SKIP: 7,
    }
    return order[label]


def _work_format_adjustment(vacancy: Vacancy, profile: CandidateProfile, reasons: list[str], concerns: list[str]) -> int:
    adjustment = 0
    if vacancy.work_format == WorkFormat.REMOTE and profile.preferences.remote_preferred:
        adjustment += profile.weights.remote_bonus
        reasons.append("remote format matches preference")
    elif vacancy.work_format == WorkFormat.HYBRID and profile.preferences.accept_moscow_hybrid:
        adjustment += profile.weights.hybrid_bonus
        reasons.append("hybrid format is acceptable")
    elif vacancy.work_format == WorkFormat.ONSITE:
        adjustment -= profile.weights.onsite_penalty
        concerns.append("on-site requirement reduces fit")
    return adjustment


def _salary_adjustment(vacancy: Vacancy, profile: CandidateProfile, reasons: list[str], concerns: list[str]) -> int:
    salary = vacancy.salary
    if salary.amount_to and salary.amount_to >= profile.salary.minimum:
        reasons.append("salary reaches target floor")
        return 6
    if salary.amount_from and salary.amount_from >= profile.salary.minimum:
        reasons.append("salary floor is acceptable")
        return 4
    if salary.amount_to is None and salary.amount_from is None:
        concerns.append("salary is not specified")
        return 0
    concerns.append("salary may be below expectation")
    return -4


def _label_for_track(
    track: VacancyTrack,
    score: int,
    assessment_product: int,
    assessment_org_leadership: int,
    assessment_research: int,
    assessment_legacy_stack: int,
    assessment_python_strict: int,
    assessment_data_science: int,
    assessment_qa: int,
    assessment_education: int,
    assessment_evangelist: int,
) -> MatchLabel:
    if track == VacancyTrack.AI:
        if (
            score >= 85
            and assessment_product < 5
            and assessment_org_leadership < 3
            and assessment_research < 5
            and assessment_legacy_stack < 3
            and assessment_python_strict < 2
            and assessment_data_science < 3
            and assessment_qa < 3
            and assessment_education < 2
            and assessment_evangelist < 1
        ):
            return MatchLabel.STRONG_AI
        if score >= 68:
            return MatchLabel.AI_TRANSITION
        if score >= 55:
            return MatchLabel.MODERATE_AI
        if score >= 45:
            return MatchLabel.POSSIBLE
        return MatchLabel.SKIP
    if track == VacancyTrack.RUBY:
        if score >= 78:
            return MatchLabel.STRONG_RUBY
        if score >= 62:
            return MatchLabel.MODERATE_RUBY
        if score >= 48:
            return MatchLabel.POSSIBLE
        return MatchLabel.SKIP
    if score >= 55:
        return MatchLabel.POSSIBLE
    return MatchLabel.SKIP


def analyze_vacancy(vacancy: Vacancy, profile: CandidateProfile) -> VacancyAnalysis:
    assessment = classify_vacancy(vacancy)
    reasons: list[str] = []
    concerns: list[str] = []

    if assessment.track == VacancyTrack.AI:
        score = 50 + profile.weights.ai_track_boost
        score += assessment.ai_signal * 3
        score += assessment.backend_signal * 2
        score += assessment.automation_signal * 2
        if assessment.ai_signal >= 8:
            reasons.append("clear AI/LLM/RAG signal")
        if assessment.backend_signal >= 4:
            reasons.append("backend and integration experience is directly relevant")
        if assessment.automation_signal >= 2:
            reasons.append("automation and orchestration overlap is relevant")
    elif assessment.track == VacancyTrack.RUBY:
        score = 48 + profile.weights.ruby_track_boost
        score += assessment.ruby_signal * 3
        score += assessment.backend_signal * 2
        if assessment.ruby_signal >= 5:
            reasons.append("strong Ruby on Rails signal")
        if assessment.backend_signal >= 4:
            reasons.append("backend stack is a strong match")
    else:
        score = 30
        score += assessment.ai_signal * 2
        score += assessment.ruby_signal * 2
        score += assessment.backend_signal
        if assessment.backend_signal >= 4:
            reasons.append("general backend overlap exists")

    score += _work_format_adjustment(vacancy, profile, reasons, concerns)
    score += _salary_adjustment(vacancy, profile, reasons, concerns)

    if assessment.python_strict_signal >= 4:
        score -= profile.weights.python_strong_penalty
        concerns.append("role appears to require strong production Python/FastAPI background")
    elif assessment.python_strict_signal > 0:
        score -= 6
        concerns.append("Python requirements may need validation")

    if assessment.frontend_signal >= 4:
        score -= profile.weights.frontend_penalty
        concerns.append("role looks frontend-heavy")
    if assessment.product_signal >= 3:
        score -= profile.weights.product_penalty
        concerns.append("role looks product-heavy rather than engineering-led")
    if assessment.org_leadership_signal >= 3:
        score -= 18
        concerns.append("role looks organization/department-lead heavy rather than hands-on engineering")
    if assessment.research_signal >= 5:
        score -= profile.weights.ml_research_penalty
        concerns.append("role leans toward ML research or model training")
    if assessment.legacy_stack_signal >= 3:
        score -= 28
        concerns.append("legacy stack focus like 1C/Bitrix is weakly aligned with the target transition path")
    if assessment.data_science_signal >= 3:
        score -= 24
        concerns.append("role looks closer to data science / ML specialist work than backend systems work")
    if assessment.qa_signal >= 3:
        score -= 24
        concerns.append("role looks QA-focused rather than backend engineering-focused")
    if assessment.education_signal >= 2:
        score -= 25
        concerns.append("role looks educational / mentorship-focused rather than engineering delivery-focused")
    if assessment.evangelist_signal >= 1:
        score -= 18
        concerns.append("role looks evangelism-focused rather than hands-on backend engineering")
    if "n8n-production-heavy" in assessment.red_flags:
        score -= profile.weights.n8n_penalty
        concerns.append("n8n/LangChain-heavy production requirement may narrow fit")
    if "automation-only" in assessment.red_flags:
        score -= 30
        concerns.append("role looks automation-only without enough backend engineering depth")
    if "hard-excluded-ml-research" in assessment.red_flags:
        score = 0
        concerns.append("role is centered on ML research, training, computer vision, or diffusion pipelines")

    score = _clamp_score(score)
    label = _label_for_track(
        assessment.track,
        score,
        assessment.product_signal,
        assessment.org_leadership_signal,
        assessment.research_signal,
        assessment.legacy_stack_signal,
        assessment.python_strict_signal,
        assessment.data_science_signal,
        assessment.qa_signal,
        assessment.education_signal,
        assessment.evangelist_signal,
    )

    action = RecommendedAction.MAYBE
    if label in {MatchLabel.STRONG_AI, MatchLabel.AI_TRANSITION, MatchLabel.STRONG_RUBY}:
        action = RecommendedAction.APPLY
    elif label == MatchLabel.SKIP:
        action = RecommendedAction.SKIP

    expected_salary = build_expected_salary(assessment.track, label, vacancy.salary.display(), profile)
    provisional = VacancyAnalysis(
        vacancy_id=vacancy.external_id,
        track=assessment.track,
        score=score,
        priority_bucket=_priority_bucket(label),
        label=label,
        action=action,
        reasons=reasons,
        concerns=concerns,
        matched_keywords=assessment.matched_keywords,
        red_flags=assessment.red_flags,
        expected_salary=expected_salary,
        summary_ru="",
    )

    return VacancyAnalysis(
        vacancy_id=provisional.vacancy_id,
        track=provisional.track,
        score=provisional.score,
        priority_bucket=provisional.priority_bucket,
        label=provisional.label,
        action=provisional.action,
        reasons=provisional.reasons,
        concerns=provisional.concerns,
        matched_keywords=provisional.matched_keywords,
        red_flags=provisional.red_flags,
        expected_salary=provisional.expected_salary,
        summary_ru=build_summary_ru(vacancy, provisional),
        generated_at=provisional.generated_at,
    )
