from __future__ import annotations

from typing import Any

from hh_monitor.adapters.base import BaseAdapter
from hh_monitor.models import NormalizedVacancy, SearchQuery


class RemoteOkAdapter(BaseAdapter):
    source_name = "remoteok"

    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raise NotImplementedError("RemoteOK adapter is a placeholder. Collection is not implemented in this iteration.")

    def fetch_details(self, external_id: str) -> dict[str, Any]:
        raise NotImplementedError("RemoteOK adapter is a placeholder. Detail fetching is not implemented.")

    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        raise NotImplementedError("RemoteOK adapter is a placeholder. Normalization is not implemented.")
