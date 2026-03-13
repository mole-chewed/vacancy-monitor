from __future__ import annotations

from collections import Counter
from datetime import datetime

from hh_monitor.config import CandidateProfile
from hh_monitor.models import MatchLabel, RankedVacancy, RecommendedAction
from hh_monitor.summaries import LABEL_TITLES_RU, format_concerns_ru, format_reasons_ru


def build_application_report_markdown(
    profile: CandidateProfile,
    ranked: list[RankedVacancy],
    top_apply: int = 25,
    top_maybe: int = 25,
    top_skip: int = 10,
) -> str:
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    label_counts = Counter(item.analysis.label for item in ranked)
    track_counts = Counter(item.analysis.track.value for item in ranked)

    apply_now = [item for item in ranked if item.analysis.action == RecommendedAction.APPLY]
    review_later = [item for item in ranked if item.analysis.action == RecommendedAction.MAYBE]
    skip_now = [item for item in ranked if item.analysis.action == RecommendedAction.SKIP]

    lines = [
        "# Отчет по вакансиям hh.ru",
        "",
        f"Сформировано: {generated_at}",
        f"Профиль: {profile.name}",
        f"Контекст: {profile.summary}",
        "",
        "## Сводка",
        f"- Всего вакансий в ранжировании: {len(ranked)}",
        f"- Откликнуться сейчас: {len(apply_now)}",
        f"- Проверить вручную: {len(review_later)}",
        f"- Пропустить: {len(skip_now)}",
        f"- AI track: {track_counts.get('ai', 0)}",
        f"- Ruby track: {track_counts.get('ruby', 0)}",
        f"- Other track: {track_counts.get('other', 0)}",
        "",
        "## Распределение по меткам",
    ]

    for label in (
        MatchLabel.STRONG_AI,
        MatchLabel.AI_TRANSITION,
        MatchLabel.MODERATE_AI,
        MatchLabel.STRONG_RUBY,
        MatchLabel.MODERATE_RUBY,
        MatchLabel.POSSIBLE,
        MatchLabel.SKIP,
    ):
        lines.append(f"- {LABEL_TITLES_RU[label]}: {label_counts.get(label, 0)}")

    lines.extend(["", "## Что делать сначала", "1. Сначала пройти весь блок `Откликнуться сейчас` сверху вниз.", "2. Потом разобрать блок `Проверить вручную`, начиная с AI-track ролей.", "3. Блок `Пропустить` оставить только как журнал, чтобы не тратить внимание.", ""])
    lines.extend(_build_section("Откликнуться сейчас", apply_now, top_apply))
    lines.extend([""])
    lines.extend(_build_section("Проверить вручную", review_later, top_maybe))
    lines.extend([""])
    lines.extend(_build_section("Пропустить", skip_now, top_skip))
    return "\n".join(lines).strip() + "\n"


def _build_section(title: str, items: list[RankedVacancy], limit: int) -> list[str]:
    lines = [f"## {title}"]
    if not items:
        lines.append("_Нет вакансий в этой категории._")
        return lines

    for index, item in enumerate(items[:limit], start=1):
        vacancy = item.vacancy
        analysis = item.analysis
        lines.extend(
            [
                f"### {index}. {vacancy.title} [{vacancy.company}]",
                f"- Vacancy ID: `{vacancy.external_id}`",
                f"- Трек: `{analysis.track.value}` | Метка: `{LABEL_TITLES_RU[analysis.label]}` | Score: `{analysis.score}` | Действие: `{analysis.action.value}`",
                f"- Локация: {vacancy.location} | Формат: {vacancy.work_format.value} | Зарплата: {vacancy.salary.display()} | Ожидание: {analysis.expected_salary}",
                f"- Почему рассматривать: {format_reasons_ru(analysis.reasons)}",
                f"- Риски: {format_concerns_ru(analysis.concerns)}",
                f"- Краткий вывод: {analysis.summary_ru}",
                f"- Ссылка: {vacancy.url or 'нет ссылки'}",
                "",
            ]
        )
    return lines[:-1]
