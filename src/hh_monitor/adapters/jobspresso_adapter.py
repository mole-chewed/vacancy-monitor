from __future__ import annotations

from typing import Any

from hh_monitor.adapters.base import BaseAdapter
from hh_monitor.models import NormalizedVacancy, SearchQuery
from hh_monitor.normalization import vacancy_from_jobspresso_payload
from hh_monitor.sources.jobspresso_api import JobspressoClient


class JobspressoAdapter(BaseAdapter):
    source_name = "jobspresso"

    def __init__(self, client: JobspressoClient) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raw_jobs = self.client.search_jobs(query.text, pages=query.pages)
        return [self.normalize({**item, "_query_name": query.name}) for item in raw_jobs]

    def fetch_details(self, external_id: str) -> dict[str, Any]:
        return self.client.get_job(external_id)

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        source_query = raw_item.get("_query_name") if isinstance(raw_item, dict) else None
        payload = dict(raw_details or raw_item)
        if source_query:
            payload["_query_name"] = source_query
        return vacancy_from_jobspresso_payload(payload, source=f"{self.source_name}_html:{source_query or 'search'}")
