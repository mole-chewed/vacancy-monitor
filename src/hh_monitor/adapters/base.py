from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from hh_monitor.models import NormalizedVacancy, SearchQuery


class BaseAdapter(ABC):
    source_name: str
    supports_detail_hydration: bool = False

    @abstractmethod
    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raise NotImplementedError

    @abstractmethod
    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        raise NotImplementedError
