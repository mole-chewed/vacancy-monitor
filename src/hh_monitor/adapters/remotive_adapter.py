from __future__ import annotations

from typing import Any

from hh_monitor.adapters.base import BaseAdapter
from hh_monitor.models import NormalizedVacancy, SearchQuery
from hh_monitor.normalization import vacancy_from_remotive_payload
from hh_monitor.sources.remotive_api import RemotiveClient


class RemotiveAdapter(BaseAdapter):
    source_name = "remotive"

    def __init__(self, client: RemotiveClient) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raw_jobs = self.client.search_jobs(query.text)
        return [self.normalize({**item, "_query_name": query.name}) for item in raw_jobs]

    def fetch_details(self, external_id: str) -> dict[str, Any]:
        return self.client.get_job(external_id)

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        source_query = raw_item.get("_query_name") if isinstance(raw_item, dict) else None
        payload = dict(raw_details or raw_item)
        if source_query:
            payload["_query_name"] = source_query
        return vacancy_from_remotive_payload(payload, source=f"{self.source_name}_api:{source_query or 'search'}")
