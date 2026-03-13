from __future__ import annotations

from typing import Any

from hh_monitor.adapters.base import BaseAdapter
from hh_monitor.models import NormalizedVacancy, SearchQuery
from hh_monitor.normalization import vacancy_from_weworkremotely_payload
from hh_monitor.sources.weworkremotely_api import WeWorkRemotelyClient


class WeWorkRemotelyAdapter(BaseAdapter):
    source_name = "weworkremotely"
    supports_detail_hydration = True

    def __init__(self, client: WeWorkRemotelyClient) -> None:
        self.client = client

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        if not query.source_url:
            raise RuntimeError("We Work Remotely queries require source_url in the profile config")
        return [
            self.normalize({**item, "_query_name": query.name})
            for item in self.client.fetch_listing_page(query.source_url)
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
        return vacancy_from_weworkremotely_payload(
            payload,
            source=f"{self.source_name}_html:{query_name or 'search'}",
        )
