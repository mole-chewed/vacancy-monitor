from __future__ import annotations

from vacancy_monitor.models import RankedVacancy, utc_now_iso


def serialize_ranked_for_agent(ranked: list[RankedVacancy], profile_name: str) -> dict:
    return {
        "generated_at": utc_now_iso(),
        "profile": profile_name,
        "total": len(ranked),
        "vacancies": [_serialize_vacancy(item) for item in ranked],
    }


def _serialize_vacancy(item: RankedVacancy) -> dict:
    vacancy = item.vacancy
    analysis = item.analysis
    return {
        "external_id": vacancy.external_id,
        "title": vacancy.title,
        "company": vacancy.company,
        "url": vacancy.url,
        "source": vacancy.source,
        "score": analysis.score,
        "label": analysis.label.value,
        "action": analysis.action.value,
        "reasons": analysis.reasons,
        "concerns": analysis.concerns,
        "summary_ru": analysis.summary_ru,
        "salary": vacancy.salary.display(),
        "work_format": vacancy.work_format.value,
        "location": vacancy.location,
        "seniority": vacancy.seniority.value,
        "skills": vacancy.skills_raw,
        "apply_command": f"PYTHONPATH=src python3 -m vacancy_monitor apply-hh --vacancy-id {vacancy.external_id}",
    }
