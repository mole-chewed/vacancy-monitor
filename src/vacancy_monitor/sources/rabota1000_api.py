from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlencode

import requests

from vacancy_monitor.models import SearchQuery

VACANCY_BLOCK_RE = re.compile(r'<div[^>]*x-data="vacancy"[^>]*>.*?</button>\s*</div>', re.DOTALL)
VACANCY_ID_RE = re.compile(r'data-vacancy-id="(?P<id>\d+)"')
SITE_RE = re.compile(r'data-site="(?P<site>[^"]+)"')
LOCATION_SLUG_RE = re.compile(r'data-location="(?P<location>[^"]+)"')
TITLE_RE = re.compile(r"<h2[^>]*>\s*(?P<title>.*?)\s*</h2>", re.DOTALL)
SALARY_RE = re.compile(
    r'<p class="mb-4 font-medium text-gray-800 text-lg leading-tight">\s*(?P<salary>.*?)\s*</p>',
    re.DOTALL,
)
COMPANY_RE = re.compile(
    r'<a class="mb-1 text-gray-700[^"]*" href="(?P<href>[^"]+)">(?P<company>.*?)</a>',
    re.DOTALL,
)
LOCATION_RE = re.compile(r'<span class="block font-normal leading-tight">\s*(?P<location>.*?)\s*</span>', re.DOTALL)
DATE_RE = re.compile(
    r'<span class="bg-blue-100 text-blue-800 text-xs font-semibold[^"]*">\s*(?P<date>.*?)\s*</span>',
    re.DOTALL,
)
SNIPPET_RE = re.compile(
    r'<p class="mb-3 text-\[15px\] md:text-base font-normal text-gray-500 overflow-x-hidden">\s*(?P<snippet>.*?)\s*</p>',
    re.DOTALL,
)
SOURCE_RE = re.compile(r'Источник:\s*<span class="text-sky-600">(?P<source>.*?)</span>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

ORDER_BY_ALIASES = {
    "relevance": "1",
    "publication_time": "2",
    "date": "2",
    "salary": "3",
}
REMOTE_SCHEDULE_ALIASES = {"remote", "удаленная работа", "удаленно"}


class Rabota1000ApiError(RuntimeError):
    """Raised when rabota1000.ru responds with an unusable payload."""


class Rabota1000Client:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search_jobs(self, query: SearchQuery) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        while True:
            html = self._get_html("/result", params=self._build_search_params(query, page))
            items = parse_listing_page(html, base_url=self.base_url)
            if query.only_with_salary:
                items = [item for item in items if _clean_text(item.get("salary_text"))]
            jobs.extend(items)
            if not items:
                break
            if query.fetch_all:
                page += 1
                continue
            if page >= max(query.pages, 1):
                break
            page += 1
        return jobs

    def build_search_preview(self, query: SearchQuery, page: int) -> dict[str, Any]:
        params = self._build_search_params(query, page)
        return {
            "source": query.source,
            "url": f"{self.base_url}/result?{urlencode(params)}",
            "params": params,
        }

    def get_job(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        url = None
        if isinstance(raw_item, dict):
            url = raw_item.get("url")
        if not url:
            url = f"{self.base_url}/vacancy/{external_id.split(':', 1)[-1]}"

        response = self.session.get(str(url), timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
            detail = response.text[:500]
            raise Rabota1000ApiError(f"Rabota1000 request failed: {response.status_code} {detail}") from exc
        return {"url": str(response.url), "html": str(response.text)}

    def _build_search_params(self, query: SearchQuery, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "query": query.text,
            "page": page,
        }
        if query.area is not None:
            params["locationId"] = query.area
        sort_order = _normalize_order_by(query.order_by)
        if sort_order:
            params["sort"] = sort_order
        job_type = self.resolve_job_type(query)
        if job_type:
            params["jobType"] = job_type
        if query.experience:
            params["experience"] = query.experience
        if query.search_field:
            params["source"] = query.search_field
        return params

    def resolve_job_type(self, query: SearchQuery) -> str | None:
        if query.employment:
            return str(query.employment)
        if query.schedule and query.schedule.strip().lower() in REMOTE_SCHEDULE_ALIASES:
            return "6"
        return None

    def _get_html(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
            detail = response.text[:500]
            raise Rabota1000ApiError(f"Rabota1000 request failed: {response.status_code} {detail}") from exc
        return str(response.text)


def parse_listing_page(html: str, *, base_url: str) -> list[dict[str, Any]]:
    vacancies: list[dict[str, Any]] = []
    for block in VACANCY_BLOCK_RE.findall(html):
        vacancy_id = _extract(VACANCY_ID_RE, block, "id")
        title = _clean_text(_extract(TITLE_RE, block, "title"))
        source_site = _clean_text(_extract(SOURCE_RE, block, "source")) or _clean_text(_extract(SITE_RE, block, "site"))
        if not vacancy_id or not title:
            continue
        company_href = _extract(COMPANY_RE, block, "href")
        vacancies.append(
            {
                "id": vacancy_id,
                "url": f"{base_url}/vacancy/{vacancy_id}",
                "title": title,
                "salary_text": _clean_text(_extract(SALARY_RE, block, "salary")),
                "company": _clean_text(_extract(COMPANY_RE, block, "company")),
                "company_url": _absolute_url(company_href, base_url=base_url),
                "location": _clean_text(_extract(LOCATION_RE, block, "location")),
                "listed_at": _clean_text(_extract(DATE_RE, block, "date")),
                "snippet": _clean_text(_extract(SNIPPET_RE, block, "snippet")),
                "source_site": source_site,
                "source_site_slug": _clean_text(_extract(SITE_RE, block, "site")),
                "location_slug": _clean_text(_extract(LOCATION_SLUG_RE, block, "location")),
            }
        )
    return vacancies


def _normalize_order_by(order_by: str | None) -> str | None:
    if not order_by:
        return None
    normalized = order_by.strip().lower()
    if normalized in {"1", "2", "3"}:
        return normalized
    return ORDER_BY_ALIASES.get(normalized)


def _extract(pattern: re.Pattern[str], text: str, group: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(group)


def _absolute_url(url: str | None, *, base_url: str) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{base_url}{url}"
    return f"{base_url}/{url.lstrip('/')}"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    no_tags = TAG_RE.sub(" ", unescape(str(value)))
    return WHITESPACE_RE.sub(" ", no_tags).strip()
