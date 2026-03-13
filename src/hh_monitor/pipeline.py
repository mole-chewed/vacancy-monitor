from __future__ import annotations

import logging
from pathlib import Path

from hh_monitor.adapters.base import BaseAdapter
from hh_monitor.adapters.hh_adapter import HHAdapter
from hh_monitor.config import CandidateProfile, load_settings
from hh_monitor.models import ApplicationStatus, RankedVacancy, SearchQuery
from hh_monitor.normalization import vacancy_from_payload
from hh_monitor.ranking import build_ranked_vacancies
from hh_monitor.sources.hh_api import HeadHunterApiError
from hh_monitor.storage import Storage


LOGGER = logging.getLogger(__name__)


def build_hh_adapter(settings) -> HHAdapter:
    from hh_monitor.sources.hh_api import HeadHunterClient

    client = HeadHunterClient(
        base_url=settings.hh_api_base_url,
        user_agent=settings.hh_user_agent,
        api_token=settings.hh_api_token,
    )
    return HHAdapter(client)


def fetch_search_queries(
    adapter: BaseAdapter,
    queries: list[SearchQuery],
    *,
    profile: CandidateProfile,
    storage: Storage | None = None,
) -> tuple[int, list]:
    total = 0
    collected = []
    ignored = profile.ignored_vacancy_ids
    for query in queries:
        vacancies = [vacancy for vacancy in adapter.search(query) if vacancy.external_id not in ignored]
        collected.extend(vacancies)
        if storage is not None:
            total += storage.upsert_vacancies(vacancies)
        else:
            total += len(vacancies)
    return total, collected


def hydrate_ranked_vacancies(
    ranked: list[RankedVacancy],
    *,
    adapter: BaseAdapter,
    storage: Storage,
    profile: CandidateProfile,
    excluded: set[ApplicationStatus],
    limit: int,
) -> list[RankedVacancy]:
    if limit <= 0 or not ranked:
        return ranked

    refreshed = []
    for item in ranked[:limit]:
        vacancy_id = item.vacancy.external_id
        if not vacancy_id.isdigit():
            continue
        try:
            payload = adapter.fetch_details(vacancy_id)
        except (HeadHunterApiError, NotImplementedError) as exc:
            LOGGER.warning("Failed to hydrate vacancy %s via adapter %s: %s", vacancy_id, adapter.source_name, exc)
            continue
        refreshed.append(vacancy_from_payload(payload, source=item.vacancy.source))

    if refreshed:
        storage.upsert_vacancies(refreshed)

    statuses = storage.get_application_statuses()
    vacancies = storage.list_vacancies(exclude_statuses=excluded)
    if profile.preferences.remote_only:
        vacancies = [vacancy for vacancy in vacancies if vacancy.work_format.value == "remote"]
    return build_ranked_vacancies(vacancies, profile=profile, statuses=statuses)
