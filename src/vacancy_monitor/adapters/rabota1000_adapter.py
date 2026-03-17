from __future__ import annotations

from typing import Any

from vacancy_monitor.adapters.base import AdapterCapabilities, BaseAdapter
from vacancy_monitor.models import NormalizedVacancy, SearchQuery
from vacancy_monitor.normalization import vacancy_from_rabota1000_payload
from vacancy_monitor.sources.rabota1000_api import Rabota1000Client


class Rabota1000Adapter(BaseAdapter):
    source_name = "rabota1000"
    capabilities = AdapterCapabilities(
        supports_detail_hydration=False,
        supports_pagination=True,
        supports_remote_filtering=True,
    )

    def __init__(self, client: Rabota1000Client) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raw_jobs = self.client.search_jobs(query)
        query_job_type = self.client.resolve_job_type(query)
        return [
            self.normalize(
                {
                    **item,
                    "_query_name": query.name,
                    "_query_job_type": query_job_type,
                }
            )
            for item in raw_jobs
        ]

    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.get_job(external_id, raw_item=raw_item)

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        source_query = raw_item.get("_query_name") if isinstance(raw_item, dict) else None
        payload = dict(raw_item)
        if raw_details:
            payload.update(raw_details)
        if source_query:
            payload["_query_name"] = source_query
        return vacancy_from_rabota1000_payload(payload, source=f"{self.source_name}_html:{source_query or 'search'}")
