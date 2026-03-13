from __future__ import annotations

from html import unescape
import json
import re
from typing import Any
from urllib.parse import quote_plus

import requests


ARTICLE_RE = re.compile(r"<article\b.*?</article>", re.DOTALL)
ARTICLE_CLASS_RE = re.compile(r'<article[^>]*class="(?P<class>[^"]+)"', re.DOTALL)
ID_RE = re.compile(r'<article[^>]*id="post-(?P<id>\d+)"')
URL_RE = re.compile(r'<h2 class="entry-title">\s*<a href="(?P<url>[^"]+)"', re.DOTALL)
TITLE_RE = re.compile(r'<h2 class="entry-title">\s*<a [^>]*>(?P<title>.*?)</a>', re.DOTALL)
COMPANY_RE = re.compile(
    r'Written by <a class="author-link entry-author__link"[^>]*>(?P<company>.*?)<br>',
    re.DOTALL,
)
LOCATION_RE = re.compile(r'⚲&nbsp;(?P<location>.*?)</a>', re.DOTALL)
DATE_RE = re.compile(r'<data class="entry-date entry-meta__date" value="(?P<date>[^"]+)"')
SUMMARY_RE = re.compile(r'<div class="entry-summary"><p>(?P<summary>.*?)</p>', re.DOTALL)
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(?P<json>.*?)</script>', re.DOTALL)
ENTRY_CONTENT_RE = re.compile(r'<div class="job_listing-description entry-content">(.*?)</div>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


class JobspressoApiError(RuntimeError):
    """Raised when Jobspresso responds with an unusable payload."""


class JobspressoClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search_jobs(self, query_text: str, *, pages: int = 1) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for page in range(1, max(pages, 1) + 1):
            response = self.session.get(self._build_search_url(query_text, page), timeout=self.timeout)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
                detail = response.text[:500]
                raise JobspressoApiError(f"Jobspresso request failed: {response.status_code} {detail}") from exc
            jobs.extend(parse_search_page(response.text))
        return jobs

    def get_job(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        url = None
        if isinstance(raw_item, dict):
            url = raw_item.get("url")
        if not url:
            raise JobspressoApiError("Jobspresso detail hydration requires a vacancy URL from source metadata.")

        response = self.session.get(url, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
            detail = response.text[:500]
            raise JobspressoApiError(f"Jobspresso detail request failed: {response.status_code} {detail}") from exc
        return parse_job_page(response.text, fallback_url=str(url))

    def _build_search_url(self, query_text: str, page: int) -> str:
        if page <= 1:
            return f"{self.base_url}/?s={quote_plus(query_text)}"
        return f"{self.base_url}/page/{page}/?s={quote_plus(query_text)}"


def parse_search_page(html: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for article in ARTICLE_RE.findall(html):
        article_classes = (_match(ARTICLE_CLASS_RE, article, "class") or "").lower()
        if "job_position_filled" in article_classes or "status-expired" in article_classes:
            continue

        post_id = _match(ID_RE, article, "id")
        url = _clean(_match(URL_RE, article, "url"))
        title = _clean(_match(TITLE_RE, article, "title"))
        company = _clean(_match(COMPANY_RE, article, "company"))
        summary = _clean(_match(SUMMARY_RE, article, "summary"))
        if not post_id or not url or not title:
            continue

        jobs.append(
            {
                "id": post_id,
                "url": unescape(url),
                "title": title,
                "company": company or "Unknown company",
                "location": _clean(_match(LOCATION_RE, article, "location")) or "Remote",
                "published_at": _clean(_match(DATE_RE, article, "date")),
                "summary": summary,
                "employment_type": "Full-Time" if "job_listing_category-full-time" in article_classes else "Unknown",
                "article_classes": article_classes,
            }
        )
    return jobs


def parse_job_page(html: str, *, fallback_url: str | None = None) -> dict[str, Any]:
    description = ""
    title = ""
    company = ""
    location = ""
    published_at = ""
    employment_type = "Unknown"
    url = fallback_url

    for block in JSON_LD_RE.findall(html):
        try:
            payload = json.loads(unescape(block))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            candidates = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            candidates = [payload]
        else:
            candidates = []
        for item in candidates:
            if item.get("@type") != "JobPosting":
                continue
            description = _clean(item.get("description"))
            title = _clean(item.get("title"))
            published_at = _clean(item.get("datePosted"))
            employment_type = _clean(item.get("industry")) or employment_type
            url = _clean(item.get("url")) or url
            hiring_org = item.get("hiringOrganization") or {}
            if isinstance(hiring_org, dict):
                company = _clean(hiring_org.get("name"))
            job_location = item.get("jobLocation")
            if isinstance(job_location, dict):
                location = _clean_address(job_location.get("address"))
            elif isinstance(job_location, list):
                parts = []
                for loc in job_location:
                    if isinstance(loc, dict):
                        parts.append(_clean_address(loc.get("address")))
                location = ", ".join(part for part in parts if part)
            break
        if description:
            break

    if not description:
        description = _clean(_match(ENTRY_CONTENT_RE, html, 1))

    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "published_at": published_at,
        "employment_type": employment_type,
        "description": description,
        "summary": description,
    }


def _match(pattern: re.Pattern[str], text: str, group: str | int) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(group)


def _clean(value: str | None) -> str:
    if not value:
        return ""
    no_tags = TAG_RE.sub(" ", unescape(value))
    return WHITESPACE_RE.sub(" ", no_tags).strip()


def _clean_address(value: Any) -> str:
    if isinstance(value, dict):
        parts = [
            _clean(value.get("streetAddress")),
            _clean(value.get("addressLocality")),
            _clean(value.get("addressRegion")),
            _clean(value.get("addressCountry")),
        ]
        return ", ".join(part for part in parts if part)
    return _clean(value)
