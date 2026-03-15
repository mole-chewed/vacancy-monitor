from __future__ import annotations

from typing import Any

from vacancy_monitor.adapters.base import AdapterCapabilities, BaseAdapter
from vacancy_monitor.models import NormalizedVacancy, SearchQuery
from vacancy_monitor.normalization import vacancy_from_habr_payload
from vacancy_monitor.sources.habr_api import HabrCareerClient


class HabrCareerAdapter(BaseAdapter):
    source_name = "habr"
    capabilities = AdapterCapabilities(
        supports_detail_hydration=True,
        supports_pagination=True,
        supports_remote_filtering=False,
    )

    def __init__(self, client: HabrCareerClient) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        return [
            self.normalize({**item, "_query_name": query.name})
            for item in self.client.search_jobs(query)
        ]

    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.get_job(external_id, raw_item=raw_item)

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        query_name = raw_item.get("_query_name")
        payload = dict(raw_item)
        if raw_details:
            payload.update(raw_details)
        if query_name:
            payload["_query_name"] = query_name
        return vacancy_from_habr_payload(
            payload,
            source=f"{self.source_name}_html:{query_name or 'search'}",
        )
