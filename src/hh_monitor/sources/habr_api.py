from __future__ import annotations

from html import unescape
import json
import re
from typing import Any
from urllib.parse import urlencode

import requests

from hh_monitor.models import SearchQuery


SSR_STATE_RE = re.compile(r'<script[^>]+data-ssr-state="true"[^>]*>(?P<json>.*?)</script>', re.DOTALL)


class HabrCareerApiError(RuntimeError):
    """Raised when career.habr.com responds with an unusable payload."""


class HabrCareerClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search_jobs(self, query: SearchQuery) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        while True:
            html = self._get_html("/vacancies", params=self._build_search_params(query, page))
            items, total_pages = parse_listing_page(html, base_url=self.base_url)
            jobs.extend(items)
            if not items:
                break
            if query.fetch_all:
                if page >= total_pages:
                    break
            else:
                if page >= max(query.pages, 1):
                    break
            page += 1
        return jobs

    def get_job(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        url = None
        if isinstance(raw_item, dict):
            url = raw_item.get("url")
        if not url:
            vacancy_id = external_id.split(":", 1)[-1]
            url = f"{self.base_url}/vacancies/{vacancy_id}"

        html = self._get_html_absolute(str(url))
        return parse_job_page(html, fallback_url=str(url), base_url=self.base_url)

    def build_search_preview(self, query: SearchQuery, page: int) -> dict[str, Any]:
        params = self._build_search_params(query, page)
        return {
            "source": query.source,
            "url": f"{self.base_url}/vacancies?{urlencode(params)}",
            "params": params,
        }

    def _build_search_params(self, query: SearchQuery, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": query.text,
            "remote": "true",
            "with_salary": "true" if query.only_with_salary else "false",
            "page": page,
            "per_page": query.per_page,
        }
        return params

    def _get_html(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        return _raise_for_status(response)

    def _get_html_absolute(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        return _raise_for_status(response)


def parse_listing_page(html: str, *, base_url: str) -> tuple[list[dict[str, Any]], int]:
    state = _load_ssr_state(html)
    vacancies = state.get("vacancies") or {}
    items = vacancies.get("list") or []
    meta = vacancies.get("meta") or {}
    if not isinstance(items, list):
        raise HabrCareerApiError("Habr vacancies page is missing the vacancy list payload")
    parsed_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        parsed_items.append(_prepare_listing_item(item, base_url=base_url))
    total_pages = meta.get("totalPages")
    return parsed_items, int(total_pages) if isinstance(total_pages, int) and total_pages > 0 else 1


def parse_job_page(html: str, *, fallback_url: str | None = None, base_url: str) -> dict[str, Any]:
    state = _load_ssr_state(html)
    vacancy = state.get("vacancy")
    if not isinstance(vacancy, dict):
        raise HabrCareerApiError("Habr vacancy page is missing the vacancy payload")
    payload = _prepare_listing_item(vacancy, base_url=base_url)
    payload["url"] = payload.get("url") or fallback_url
    return payload


def _load_ssr_state(html: str) -> dict[str, Any]:
    match = SSR_STATE_RE.search(html)
    if not match:
        raise HabrCareerApiError("Habr page does not contain SSR JSON state")
    raw_json = unescape(match.group("json"))
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise HabrCareerApiError("Failed to parse Habr SSR JSON state") from exc
    if not isinstance(payload, dict):
        raise HabrCareerApiError("Habr SSR state payload is not an object")
    return payload


def _prepare_listing_item(payload: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    prepared = dict(payload)
    href = prepared.get("href")
    if isinstance(href, str) and href.startswith("/"):
        prepared["url"] = f"{base_url}{href}"
    elif isinstance(href, str):
        prepared["url"] = href
    company = prepared.get("company")
    if isinstance(company, dict):
        company_href = company.get("href")
        if isinstance(company_href, str) and company_href.startswith("/"):
            company = dict(company)
            company["href"] = f"{base_url}{company_href}"
            prepared["company"] = company
    return prepared


def _raise_for_status(response: requests.Response) -> str:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
        detail = response.text[:500]
        raise HabrCareerApiError(f"Habr request failed: {response.status_code} {detail}") from exc
    return response.text
