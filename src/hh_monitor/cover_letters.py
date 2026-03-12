from __future__ import annotations

import re

from hh_monitor.config import CandidateProfile
from hh_monitor.models import Vacancy, VacancyAnalysis, VacancyTrack
from hh_monitor.summaries import format_reasons_ru


def build_cover_letter_ru(profile: CandidateProfile, vacancy: Vacancy, analysis: VacancyAnalysis) -> str:
    focus = _focus_terms(analysis)
    intro = f"Здравствуйте! Меня заинтересовала позиция {vacancy.title} в {vacancy.company}."
    backend_background = (
        "У меня 13+ лет опыта в backend-разработке: архитектура сервисов, API, интеграции, "
        "PostgreSQL, Redis, background jobs, Docker, AWS и production-системы."
    )

    if analysis.track == VacancyTrack.AI:
        transition = (
            "Сейчас я целенаправленно двигаюсь в AI-track через роли, где особенно важны "
            "LLM-интеграции, RAG, automation, vector storage и надежный backend вокруг этих сценариев."
        )
    elif analysis.track == VacancyTrack.RUBY:
        transition = (
            "У меня сильный production-бэкграунд именно в Ruby on Rails, поэтому могу быстро входить "
            "в задачи по backend delivery, reliability и развитию продукта."
        )
    else:
        transition = (
            "Для меня особенно интересны роли с сильным пересечением по backend-архитектуре, "
            "интеграциям и automation, где можно быстро приносить практическую пользу."
        )

    fit = f"По этой вакансии вижу хорошее совпадение: {format_reasons_ru(analysis.reasons)}."
    if focus:
        fit += f" Отдельно отмечу пересечение по темам: {focus}."

    closing = (
        "Если вам близок кандидат с сильной backend-базой, опытом сложных интеграций и практическим интересом "
        "к AI-системам, буду рад обсудить, где смогу быть наиболее полезен вашей команде."
    )

    return "\n\n".join([intro, backend_background, transition, fit, closing]).strip() + "\n"


def build_cover_letter_filename(vacancy: Vacancy) -> str:
    slug = _slugify(vacancy.company)[:40]
    return f"{vacancy.external_id}_{slug or 'company'}.md"


def _focus_terms(analysis: VacancyAnalysis) -> str:
    ordered_groups = ("ai", "automation", "backend", "ruby")
    terms: list[str] = []
    for group in ordered_groups:
        for term in analysis.matched_keywords.get(group, []):
            if term not in terms:
                terms.append(term)
    return ", ".join(terms[:6])


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
