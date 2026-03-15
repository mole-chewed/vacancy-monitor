from __future__ import annotations

from typing import Any

from vacancy_monitor.adapters.base import AdapterCapabilities, BaseAdapter
from vacancy_monitor.models import NormalizedVacancy, SearchQuery


class LinkedInAdapter(BaseAdapter):
    source_name = "linkedin"
    capabilities = AdapterCapabilities(
        supports_search=False,
        supports_detail_hydration=False,
        supports_pagination=False,
        supports_remote_filtering=False,
    )

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raise NotImplementedError("LinkedIn adapter is a placeholder. Collection is not implemented in this iteration.")

    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError("LinkedIn adapter is a placeholder. Detail fetching is not implemented.")

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        raise NotImplementedError("LinkedIn adapter is a placeholder. Normalization is not implemented.")
