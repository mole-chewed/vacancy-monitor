from __future__ import annotations

import logging

from hh_monitor.adapters.base import BaseAdapter
from hh_monitor.adapters.hh_adapter import HHAdapter
from hh_monitor.adapters.jobspresso_adapter import JobspressoAdapter
from hh_monitor.adapters.linkedin_adapter import LinkedInAdapter
from hh_monitor.adapters.remotive_adapter import RemotiveAdapter
from hh_monitor.adapters.remoteok_adapter import RemoteOkAdapter
from hh_monitor.adapters.weworkremotely_adapter import WeWorkRemotelyAdapter
from hh_monitor.config import CandidateProfile, source_family, vacancy_is_ignored
from hh_monitor.models import ApplicationStatus, RankedVacancy, SearchQuery
from hh_monitor.ranking import build_ranked_vacancies
from hh_monitor.sources.hh_api import HeadHunterApiError, HeadHunterClient
from hh_monitor.sources.jobspresso_api import JobspressoApiError, JobspressoClient
from hh_monitor.sources.remotive_api import RemotiveApiError, RemotiveClient
from hh_monitor.sources.remoteok_api import RemoteOkApiError, RemoteOkClient
from hh_monitor.sources.weworkremotely_api import WeWorkRemotelyClient
from hh_monitor.storage import Storage


LOGGER = logging.getLogger(__name__)


def build_adapter_registry(settings) -> dict[str, BaseAdapter]:
    return {
        "hh": HHAdapter(
            HeadHunterClient(
                base_url=settings.hh_api_base_url,
                user_agent=settings.hh_user_agent,
                api_token=settings.hh_api_token,
            )
        ),
        "jobspresso": JobspressoAdapter(
            JobspressoClient(
                base_url=getattr(settings, "jobspresso_base_url", "https://jobspresso.co"),
                user_agent=getattr(settings, "jobspresso_user_agent", settings.hh_user_agent),
            )
        ),
        "remoteok": RemoteOkAdapter(
            RemoteOkClient(
                base_url=getattr(settings, "remoteok_api_base_url", "https://remoteok.com"),
                user_agent=getattr(settings, "remoteok_user_agent", settings.hh_user_agent),
            )
        ),
        "remotive": RemotiveAdapter(
            RemotiveClient(
                base_url=getattr(settings, "remotive_api_base_url", "https://remotive.com"),
                user_agent=getattr(settings, "remotive_user_agent", settings.hh_user_agent),
            )
        ),
        "weworkremotely": WeWorkRemotelyAdapter(
            WeWorkRemotelyClient(
                base_url=getattr(settings, "weworkremotely_base_url", "https://weworkremotely.com"),
                user_agent=getattr(settings, "weworkremotely_user_agent", settings.hh_user_agent),
            )
        ),
        "linkedin": LinkedInAdapter(),
    }
def fetch_search_queries(
    adapters: dict[str, BaseAdapter],
    queries: list[SearchQuery],
    *,
    profile: CandidateProfile,
    storage: Storage | None = None,
) -> tuple[int, list, list[tuple[SearchQuery, int, int]]]:
    total_saved = 0
    collected = []
    details: list[tuple[SearchQuery, int, int]] = []
    for query in queries:
        adapter = adapters.get(query.source)
        if adapter is None:
            raise RuntimeError(f"Source adapter is not configured: {query.source}")
        vacancies = [vacancy for vacancy in adapter.search(query) if not vacancy_is_ignored(profile, vacancy)]
        collected.extend(vacancies)
        saved = storage.upsert_vacancies(vacancies) if storage is not None else len(vacancies)
        total_saved += saved
        details.append((query, len(vacancies), saved))
    return total_saved, collected, details


def hydrate_ranked_vacancies(
    ranked: list[RankedVacancy],
    *,
    adapters: dict[str, BaseAdapter],
    storage: Storage,
    profile: CandidateProfile,
    excluded: set[ApplicationStatus],
    limit: int,
) -> list[RankedVacancy]:
    if limit <= 0 or not ranked:
        return ranked

    refreshed = []
    for item in ranked[:limit]:
        family = source_family(item.vacancy.source)
        adapter = adapters.get(family)
        if adapter is None:
            continue
        try:
            payload = adapter.fetch_details(item.vacancy.external_id)
        except (
            HeadHunterApiError,
            JobspressoApiError,
            RemoteOkApiError,
            RemotiveApiError,
            NotImplementedError,
            RuntimeError,
        ) as exc:
            LOGGER.warning("Failed to hydrate vacancy %s via adapter %s: %s", item.vacancy.external_id, family, exc)
            continue
        refreshed.append(adapter.normalize(item.vacancy.source_metadata, payload))

    if refreshed:
        storage.upsert_vacancies(refreshed)

    statuses = storage.get_application_statuses()
    vacancies = storage.list_vacancies(exclude_statuses=excluded)
    if profile.preferences.remote_only:
        vacancies = [vacancy for vacancy in vacancies if vacancy.work_format.value == "remote"]
    return build_ranked_vacancies(vacancies, profile=profile, statuses=statuses)
