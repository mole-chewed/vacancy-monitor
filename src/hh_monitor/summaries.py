from __future__ import annotations

from hh_monitor.config import CandidateProfile
from hh_monitor.models import MatchLabel, Vacancy, VacancyAnalysis, VacancyTrack


LABEL_TITLES_RU = {
    MatchLabel.STRONG_AI: "AI Priority Match",
    MatchLabel.AI_TRANSITION: "AI Transition Match",
    MatchLabel.MODERATE_AI: "Moderate AI Match",
    MatchLabel.STRONG_RUBY: "Strong Ruby Match",
    MatchLabel.MODERATE_RUBY: "Moderate Ruby Match",
    MatchLabel.POSSIBLE: "Possible Match",
    MatchLabel.SKIP: "Skip",
}

REASON_TRANSLATIONS_RU = {
    "clear AI/LLM/RAG signal": "четкий AI/LLM/RAG-фокус",
    "backend and integration experience is directly relevant": "сильное совпадение по backend и интеграциям",
    "automation and orchestration overlap is relevant": "есть прямое пересечение по automation и orchestration",
    "remote format matches preference": "удаленный формат совпадает с предпочтениями",
    "hybrid format is acceptable": "гибридный формат допустим",
    "salary reaches target floor": "зарплата попадает в целевой диапазон",
    "salary floor is acceptable": "нижняя граница зарплаты приемлема",
    "strong Ruby on Rails signal": "сильное совпадение по Ruby on Rails",
    "backend stack is a strong match": "backend-стек хорошо совпадает",
    "general backend overlap exists": "есть общее совпадение по backend-задачам",
}

CONCERN_TRANSLATIONS_RU = {
    "salary is not specified": "зарплата не указана",
    "salary may be below expectation": "зарплата может быть ниже ожиданий",
    "Python requirements may need validation": "нужно отдельно проверить требования по Python",
    "role appears to require strong production Python/FastAPI background": "роль может требовать сильный production-опыт с Python/FastAPI",
    "role looks frontend-heavy": "роль выглядит слишком frontend-heavy",
    "role looks product-heavy rather than engineering-led": "роль смещена в продуктовую сторону, а не в engineering",
    "role looks organization/department-lead heavy rather than hands-on engineering": "роль больше про управление подразделением, чем про hands-on engineering",
    "role leans toward ML research or model training": "роль уходит в ML research или обучение моделей",
    "legacy stack focus like 1C/Bitrix is weakly aligned with the target transition path": "фокус на 1C/Bitrix слабо совпадает с целевым переходом",
    "role looks closer to data science / ML specialist work than backend systems work": "роль ближе к data science, чем к backend systems",
    "role looks QA-focused rather than backend engineering-focused": "роль ближе к QA, чем к backend engineering",
    "role looks educational / mentorship-focused rather than engineering delivery-focused": "роль выглядит скорее образовательной, чем delivery-oriented",
    "role looks evangelism-focused rather than hands-on backend engineering": "роль больше про evangelism, чем про hands-on backend",
    "n8n/LangChain-heavy production requirement may narrow fit": "сильный акцент на n8n/LangChain может сузить fit",
    "on-site requirement reduces fit": "офисный формат снижает совпадение",
}


def build_expected_salary(track: VacancyTrack, label: MatchLabel, vacancy_salary_text: str, profile: CandidateProfile) -> str:
    if vacancy_salary_text != "not specified":
        return vacancy_salary_text
    if track == VacancyTrack.AI and label in {MatchLabel.STRONG_AI, MatchLabel.AI_TRANSITION, MatchLabel.MODERATE_AI}:
        return f"{profile.salary.target}-{profile.salary.stretch} {profile.salary.currency}"
    return f"{profile.salary.minimum}-{profile.salary.target} {profile.salary.currency}"


def translate_reason_ru(reason: str) -> str:
    return REASON_TRANSLATIONS_RU.get(reason, reason)


def translate_concern_ru(concern: str) -> str:
    return CONCERN_TRANSLATIONS_RU.get(concern, concern)


def format_reasons_ru(reasons: list[str], limit: int = 3) -> str:
    if not reasons:
        return "совпадений по ключевым сигналам пока мало"
    return "; ".join(translate_reason_ru(reason) for reason in reasons[:limit])


def format_concerns_ru(concerns: list[str], limit: int = 2) -> str:
    if not concerns:
        return "критичных рисков не видно"
    return "; ".join(translate_concern_ru(concern) for concern in concerns[:limit])


def build_summary_ru(vacancy: Vacancy, analysis: VacancyAnalysis) -> str:
    reasons = format_reasons_ru(analysis.reasons)
    concerns = format_concerns_ru(analysis.concerns)
    return (
        f"{LABEL_TITLES_RU[analysis.label]} | Трек: {analysis.track.value}. "
        f"Почему подходит: {reasons}. "
        f"Риски: {concerns}. "
        f"Рекомендация: {analysis.action.value}."
    )
