from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from vacancy_monitor.models import NormalizedVacancy, SearchQuery


@dataclass(frozen=True)
class AdapterCapabilities:
    supports_search: bool = True
    supports_detail_hydration: bool = False
    supports_pagination: bool = False
    supports_remote_filtering: bool = False
    requires_source_url: bool = False


class BaseAdapter(ABC):
    source_name: str
    capabilities: AdapterCapabilities = AdapterCapabilities()

    @abstractmethod
    def search(self, query: SearchQuery, **kwargs: Any) -> list[NormalizedVacancy]:
        raise NotImplementedError

    @abstractmethod
    def fetch_details(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_item: dict[str, Any], raw_details: dict[str, Any] | None = None) -> NormalizedVacancy:
        raise NotImplementedError
