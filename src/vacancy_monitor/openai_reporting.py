from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from vacancy_monitor.config import CandidateProfile
from vacancy_monitor.models import MatchLabel, RankedVacancy, RecommendedAction, WorkFormat

try:  # pragma: no cover - exercised indirectly in environments with the SDK installed
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover - SDK is optional in tests
    OpenAI = None  # type: ignore[assignment]


class OpenAIReportingUnavailableError(RuntimeError):
    """Raised when OpenAI reporting cannot be used in the current environment."""


class OpenAIReportGenerationError(RuntimeError):
    """Raised when OpenAI returns an unusable report response."""


ClientFactory = Callable[[str], Any]
LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_OUTPUT_TOKENS = 12000
DEFAULT_CV_CHAR_LIMIT = 6000
DEFAULT_COMPACT_TEXT_LIMIT = 140


def generate_openai_application_report(
    *,
    api_key: str | None,
    model: str,
    profile: CandidateProfile,
    cv_text: str,
    ranked: list[RankedVacancy],
    top_apply: int = 20,
    top_maybe: int = 20,
    top_skip: int = 12,
    client_factory: ClientFactory | None = None,
) -> str:
    if not api_key:
        raise OpenAIReportingUnavailableError("OPENAI_API_KEY is not configured.")
    if OpenAI is None and client_factory is None:
        raise OpenAIReportingUnavailableError(
            "openai package is not installed. Add it to the environment before running the report command."
        )

    ranked = [item for item in ranked if item.analysis.action != RecommendedAction.SKIP]
    if not ranked:
        raise OpenAIReportGenerationError("No non-skip vacancies remain after deterministic filtering.")
    client = client_factory(api_key) if client_factory is not None else OpenAI(api_key=api_key, max_retries=0)
    compact_limit, detailed_limit = _select_evidence_limits(
        ranked_count=len(ranked),
        top_apply=top_apply,
        top_maybe=top_maybe,
        top_skip=top_skip,
    )
    request_input = _report_user_prompt(
        profile,
        cv_text,
        ranked,
        compact_limit=compact_limit,
        detailed_limit=detailed_limit,
        cv_char_limit=DEFAULT_CV_CHAR_LIMIT,
        compact_text_limit=DEFAULT_COMPACT_TEXT_LIMIT,
    )
    LOGGER.info(
        "OpenAI report payload prepared with compact_limit=%s detailed_limit=%s input_chars=%s",
        compact_limit,
        detailed_limit,
        len(request_input),
    )
    try:
        response = client.responses.create(
            model=model,
            instructions=_report_system_prompt(
                top_apply=top_apply,
                top_maybe=top_maybe,
                top_skip=top_skip,
            ),
            input=request_input,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # pragma: no cover - depends on external API and network
        raise OpenAIReportGenerationError(f"OpenAI report request failed: {exc}") from exc

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise OpenAIReportGenerationError("OpenAI response did not include report text.")
    return output_text.strip() + "\n"


def build_report_evidence(
    profile: CandidateProfile,
    cv_text: str,
    ranked: list[RankedVacancy],
    *,
    compact_limit: int | None = None,
    detailed_limit: int = 60,
    cv_char_limit: int = DEFAULT_CV_CHAR_LIMIT,
    compact_text_limit: int = DEFAULT_COMPACT_TEXT_LIMIT,
) -> dict[str, object]:
    compact_ranked = ranked if compact_limit is None else ranked[:compact_limit]
    detailed_ranked = ranked[:detailed_limit]
    return {
        "candidate_profile": {
            "name": profile.name,
            "summary": profile.summary,
            "genai_transition_context": (
                "Candidate is new to GenAI professionally and is trying to land a first realistic GenAI role. "
                "Prioritize transition-friendly AI backend/system/platform roles over perfect-keyword matching."
            ),
            "preferred_language": profile.preferred_language,
            "preferences": {
                "remote_only": profile.preferences.remote_only,
                "remote_preferred": profile.preferences.remote_preferred,
                "accept_russia": profile.preferences.accept_russia,
                "accept_moscow_hybrid": profile.preferences.accept_moscow_hybrid,
                "full_time_preferred": profile.preferences.full_time_preferred,
                "long_term_contract_ok": profile.preferences.long_term_contract_ok,
            },
            "salary": {
                "currency": profile.salary.currency,
                "minimum": profile.salary.minimum,
                "target": profile.salary.target,
                "stretch": profile.salary.stretch,
            },
        },
        "candidate_cv_text": _truncate_text(cv_text, cv_char_limit),
        "report_policy": {
            "remote_only_already_enforced": True,
            "deterministic_score_is_advisory_only": True,
            "ruby_roles_must_rank_above_ai_roles_when_relevance_is_realistic": True,
            "already_applied_vacancies_already_excluded": True,
            "vacancies_are_pre_filtered_to_ruby_ai_or_mixed_tracks_only": True,
            "candidate_is_strongest_in_ruby_on_rails_backend_and_genai_is_secondary_transition_track": True,
            "vacancies_compact_count": len(compact_ranked),
            "vacancies_detailed_count": len(detailed_ranked),
            "vacancies_may_be_truncated_for_payload_budget": True,
        },
        "vacancies_compact": [
            _serialize_ranked_vacancy_compact(item, compact_text_limit=compact_text_limit) for item in compact_ranked
        ],
        "vacancies_detailed": [_serialize_ranked_vacancy_detailed(item) for item in detailed_ranked],
    }


def _report_system_prompt(*, top_apply: int, top_maybe: int, top_skip: int) -> str:
    return (
        "Ты опытный карьерный ассистент для senior backend engineer. "
        "Основной приоритет кандидата сейчас: Ruby on Rails / Ruby backend roles. "
        "AI-track остается важным вторичным направлением, но уже не главным. "
        "Кандидат новый в GenAI с точки зрения коммерческого опыта и ищет реалистичные AI transition roles только после сильных Ruby backend вариантов. "
        "Твоя задача: проанализировать все переданные вакансии и выдать итоговый markdown-отчет на русском языке. "
        "Все вакансии уже отфильтрованы по remote-only и исключают уже обработанные отклики. "
        "В отчете нужно рассматривать только вакансии, которые реально совпадают с профилем кандидата: в первую очередь Ruby on Rails backend, затем mixed backend+AI roles, затем backend-heavy AI transition roles. "
        "Предпочтительные семейства ролей: Ruby Backend Engineer, Senior Rails Developer, Backend Engineer (AI features), AI Product Engineer, GenAI Engineer, LLM Integration Engineer, AI Backend Engineer. "
        "Детерминированные score/label/action используй только как подсказку, а не как обязательную истину. "
        "Ты можешь менять приоритет и рекомендации, если это лучше соответствует профилю кандидата. "
        "Не выдумывай факты, опирайся только на переданные данные. "
        "В первую очередь цени сильные Ruby/Rails backend roles. После них цени realistic AI transition roles: GenAI, AI backend, AI systems, AI platform, LLM integrations, RAG, automation, agent/tool workflows. "
        "Понижай product-heavy, research-heavy, frontend-heavy, onsite-only, deep Python-only mismatch, 1C/Bitrix и data-science-heavy роли. "
        f"Сформируй sections markdown: 1) короткие выводы, 2) `Откликнуться сейчас` (до {top_apply} вакансий), "
        f"3) `Проверить вручную` (до {top_maybe}), 4) `Пропустить` (до {top_skip}, только если есть действительно пограничные случаи), "
        "5) `Что можно упустить`, где перечислишь пограничные возможности или пробелы данных. "
        "Сосредоточь отчет на вакансиях, которые стоит реально рассматривать; не засоряй отчет очевидными skip-ролями. "
        "Для каждой вакансии в списках указывай vacancy id, ссылку на вакансию, итоговое решение (apply/maybe/skip), краткое объяснение fit, риски и почему она стоит именно на этом месте. "
        "Используй `vacancies_compact` для полного охвата всех вакансий, а `vacancies_detailed` как основной источник полных описаний и деталей для лучших кандидатов."
    )


def _report_user_prompt(
    profile: CandidateProfile,
    cv_text: str,
    ranked: list[RankedVacancy],
    *,
    compact_limit: int | None,
    detailed_limit: int,
    cv_char_limit: int,
    compact_text_limit: int,
) -> str:
    evidence = build_report_evidence(
        profile,
        cv_text,
        ranked,
        compact_limit=compact_limit,
        detailed_limit=detailed_limit,
        cv_char_limit=cv_char_limit,
        compact_text_limit=compact_text_limit,
    )
    return (
        "Ниже структурированные данные по вакансиям и кандидату. "
        "Проанализируй весь массив и сгенерируй итоговый отчет.\n\n"
        f"{json.dumps(evidence, ensure_ascii=False, indent=2)}"
    )


def _serialize_ranked_vacancy_compact(item: RankedVacancy, *, compact_text_limit: int) -> dict[str, object]:
    vacancy = item.vacancy
    analysis = item.analysis
    return {
        "vacancy_id": vacancy.external_id,
        "title": vacancy.title,
        "company": vacancy.company,
        "url": vacancy.url,
        "location": vacancy.location,
        "work_format": vacancy.work_format.value,
        "is_remote": vacancy.work_format == WorkFormat.REMOTE,
        "salary": vacancy.salary.display(),
        "track": analysis.track.value,
        "deterministic_label": _label_name(analysis.label),
        "deterministic_score": analysis.score,
        "deterministic_action": analysis.action.value,
        "summary_ru": analysis.summary_ru,
        "reasons": analysis.reasons,
        "concerns": analysis.concerns,
        "red_flags": analysis.red_flags,
        "expected_salary": analysis.expected_salary,
        "matched_keywords": analysis.matched_keywords,
        "summary_text": _truncate_text(_combined_vacancy_text(vacancy), compact_text_limit),
    }


def _serialize_ranked_vacancy_detailed(item: RankedVacancy) -> dict[str, object]:
    vacancy = item.vacancy
    analysis = item.analysis
    return {
        "vacancy_id": vacancy.external_id,
        "title": vacancy.title,
        "company": vacancy.company,
        "url": vacancy.url,
        "location": vacancy.location,
        "work_format": vacancy.work_format.value,
        "is_remote": vacancy.work_format == WorkFormat.REMOTE,
        "salary": vacancy.salary.display(),
        "track": analysis.track.value,
        "deterministic_label": _label_name(analysis.label),
        "deterministic_score": analysis.score,
        "deterministic_action": analysis.action.value,
        "summary_ru": analysis.summary_ru,
        "reasons": analysis.reasons,
        "concerns": analysis.concerns,
        "red_flags": analysis.red_flags,
        "expected_salary": analysis.expected_salary,
        "matched_keywords": analysis.matched_keywords,
        "employment_type": vacancy.employment_type,
        "experience_level": vacancy.experience_level,
        "description": vacancy.description,
        "requirements": vacancy.requirements,
    }


def _label_name(label: MatchLabel) -> str:
    return label.value


def _combined_vacancy_text(vacancy: Any) -> str:
    parts = [vacancy.description.strip(), vacancy.requirements.strip()]
    return "\n\n".join(part for part in parts if part).strip()


def _truncate_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 3, 0)].rstrip() + "..."


def _select_evidence_limits(*, ranked_count: int, top_apply: int, top_maybe: int, top_skip: int) -> tuple[int, int]:
    requested = max(top_apply + top_maybe + top_skip, 1)
    detailed_limit = min(ranked_count, max(requested + 5, 12))
    compact_limit = min(ranked_count, max(requested * 3, 40))
    return compact_limit, detailed_limit
