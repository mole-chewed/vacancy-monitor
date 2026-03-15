from __future__ import annotations

from typing import Any

from vacancy_monitor.adapters.base import BaseAdapter
from vacancy_monitor.models import NormalizedVacancy, SearchQuery
from vacancy_monitor.normalization import vacancy_from_remoteok_payload
from vacancy_monitor.sources.remoteok_api import RemoteOkClient


class RemoteOkAdapter(BaseAdapter):
    source_name = "remoteok"
    supports_detail_hydration = True

    def __init__(self, client: RemoteOkClient) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raw_jobs = self.client.search_jobs(query.text)
        return [self.normalize({**item, "_query_name": query.name}) for item in raw_jobs]

    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.get_job(external_id)

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        source_query = raw_item.get("_query_name") if isinstance(raw_item, dict) else None
        payload = dict(raw_details or raw_item)
        if source_query:
            payload["_query_name"] = source_query
        return vacancy_from_remoteok_payload(payload, source=f"{self.source_name}_api:{source_query or 'search'}")
