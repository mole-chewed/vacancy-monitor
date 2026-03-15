from __future__ import annotations

import logging
from typing import Any

import requests

from vacancy_monitor.models import SearchQuery, Vacancy
from vacancy_monitor.normalization import vacancy_from_payload

LOGGER = logging.getLogger(__name__)


class HeadHunterApiError(RuntimeError):
    """Raised when the hh.ru API responds with an unusable payload."""


class HeadHunterClient:
    def __init__(self, base_url: str, user_agent: str, api_token: str | None = None, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if api_token:
            self.session.headers.update({"Authorization": f"Bearer {api_token}"})

    def search_vacancies(
        self,
        text: str,
        per_page: int = 20,
        pages: int = 1,
        area: int | None = None,
        only_with_salary: bool = False,
        detailed: bool = False,
    ) -> list[Vacancy]:
        query = SearchQuery(
            source="hh",
            name="ad_hoc",
            text=text,
            per_page=per_page,
            pages=pages,
            area=area,
            only_with_salary=only_with_salary,
            detailed=detailed,
        )
        return self.search_vacancies_by_query(query)

    def search_vacancies_by_query(self, query: SearchQuery) -> list[Vacancy]:
        vacancies: list[Vacancy] = []
        page = 0
        while True:
            params = query.to_params()
            params["page"] = page
            page_payload = self._get_json("/vacancies", params=params)
            items = page_payload.get("items")
            if not isinstance(items, list):
                raise HeadHunterApiError("hh.ru vacancies response is missing list payload")
            for item in items:
                vacancy_payload = item
                if query.detailed and item.get("id"):
                    try:
                        vacancy_payload = self.get_vacancy(str(item["id"]))
                    except HeadHunterApiError as exc:
                        LOGGER.warning(
                            "Failed to fetch detailed vacancy %s for query %s, falling back to search item: %s",
                            item.get("id"),
                            query.name,
                            exc,
                        )
                vacancy = vacancy_from_payload(vacancy_payload, source=f"hh_api:{query.name}")
                if vacancy.is_archived:
                    LOGGER.info("Skipped archived hh vacancy %s for query %s", vacancy.external_id, query.name)
                    continue
                vacancies.append(vacancy)
            LOGGER.info("Fetched %s vacancies from hh.ru page %s for query %s", len(items), page, query.name)
            total_pages = page_payload.get("pages")
            if not items:
                break
            if query.fetch_all:
                if isinstance(total_pages, int) and page + 1 >= total_pages:
                    break
            else:
                if page + 1 >= query.pages:
                    break
            page += 1
        return vacancies

    def get_vacancy(self, vacancy_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/vacancies/{vacancy_id}")
        if not isinstance(payload, dict):
            raise HeadHunterApiError(f"hh.ru vacancy response for {vacancy_id} is not an object")
        return payload

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live API behavior
            detail = response.text[:500]
            raise HeadHunterApiError(f"hh.ru API request failed: {response.status_code} {detail}") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise HeadHunterApiError("hh.ru API returned a non-object JSON payload")
        return payload
