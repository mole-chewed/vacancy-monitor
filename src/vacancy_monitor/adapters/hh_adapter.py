from __future__ import annotations

from typing import Any

from vacancy_monitor.adapters.base import BaseAdapter
from vacancy_monitor.models import NormalizedVacancy, SearchQuery
from vacancy_monitor.normalization import vacancy_from_payload
from vacancy_monitor.sources.hh_api import HeadHunterClient


class HHAdapter(BaseAdapter):
    source_name = "hh"
    supports_detail_hydration = True

    def __init__(self, client: HeadHunterClient) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        return self.client.search_vacancies_by_query(query)

    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.get_vacancy(external_id)

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        payload = raw_details or raw_item
        return vacancy_from_payload(payload, source=f"{self.source_name}_api")
