from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

import requests

JOB_BLOCK_RE = re.compile(r'<li class="[^"]*new-listing-container[^"]*">(.*?)</li>', re.DOTALL)
HREF_RE = re.compile(r'href="(?P<href>/remote-jobs/[^"]+)"')
TITLE_RE = re.compile(r'new-listing__header__title__text">(?P<title>.*?)</span>', re.DOTALL)
COMPANY_RE = re.compile(r'new-listing__company-name">\s*(?P<company>.*?)\s*(?:<img|</p>)', re.DOTALL)
LOCATION_RE = re.compile(r'new-listing__company-headquarters">\s*(?P<location>.*?)\s*<i ', re.DOTALL)
CATEGORY_RE = re.compile(r'new-listing__categories__category[^"]*">\s*(?P<category>.*?)\s*</p>', re.DOTALL)
DATE_RE = re.compile(r'new-listing__header__icons__date">\s*(?P<date>.*?)\s*</p>', re.DOTALL)
JSON_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(?P<json>.*?)</script>', re.DOTALL)
DETAIL_CONTENT_RE = re.compile(r'<div class="listing-container__content">(?P<body>.*?)</div>\s*</div>', re.DOTALL)
META_DESCRIPTION_RE = re.compile(r'<meta[^>]+name="description"[^>]+content="(?P<value>[^"]+)"', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


class WeWorkRemotelyApiError(RuntimeError):
    """Raised when We Work Remotely responds with an unusable payload."""


class WeWorkRemotelyClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def fetch_listing_page(self, url: str) -> list[dict[str, Any]]:
        response = self.session.get(url, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
            detail = response.text[:500]
            raise WeWorkRemotelyApiError(
                f"We Work Remotely request failed: {response.status_code} {detail}"
            ) from exc
        return parse_listing_page(response.text, base_url=self.base_url)

    def get_job(self, external_id: str, *, raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
        url = None
        if isinstance(raw_item, dict):
            url = raw_item.get("url")
        if not url:
            slug = external_id.split(":", 1)[-1]
            url = f"{self.base_url}/remote-jobs/{slug}"

        try:
            response = self.session.get(str(url), timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return {"id": external_id.split(":", 1)[-1], "url": url, "_detail_unavailable": True}

        detail = parse_job_page(response.text, fallback_url=str(url))
        if not detail.get("description") and _looks_like_cloudflare_challenge(response.text):
            detail["_detail_unavailable"] = True
        return detail


def parse_listing_page(html: str, *, base_url: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for block in JOB_BLOCK_RE.findall(html):
        href_match = HREF_RE.search(block)
        title_match = TITLE_RE.search(block)
        company_match = COMPANY_RE.search(block)
        if not href_match or not title_match or not company_match:
            continue
        href = href_match.group("href")
        categories = [_clean_text(match) for match in CATEGORY_RE.findall(block)]
        jobs.append(
            {
                "id": href.rsplit("/", 1)[-1],
                "url": f"{base_url}{href}",
                "title": _clean_text(title_match.group("title")),
                "company": _clean_text(company_match.group("company")),
                "location": _clean_text(LOCATION_RE.search(block).group("location")) if LOCATION_RE.search(block) else "Remote",
                "categories": [item for item in categories if item],
                "listed_at": _clean_text(DATE_RE.search(block).group("date")) if DATE_RE.search(block) else None,
            }
        )
    return jobs


def parse_job_page(html: str, *, fallback_url: str | None = None) -> dict[str, Any]:
    description = ""
    title = ""
    company = ""
    location = ""
    employment_type = "Unknown"
    apply_url = None
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
            description = _clean_text(str(item.get("description") or ""))
            title = _clean_text(str(item.get("title") or ""))
            hiring_org = item.get("hiringOrganization") or {}
            if isinstance(hiring_org, dict):
                company = _clean_text(str(hiring_org.get("name") or ""))
            job_location = item.get("jobLocation")
            if isinstance(job_location, dict):
                location = _clean_text(str(job_location.get("address") or ""))
            apply_url = _clean_text(str(item.get("url") or "")) or apply_url
            break
        if description:
            break

    if not description:
        description = _clean_text(_match(DETAIL_CONTENT_RE, html, "body"))
    if not description:
        description = _clean_text(_match(META_DESCRIPTION_RE, html, "value"))

    categories = []
    if employment_type and employment_type != "Unknown":
        categories.append(employment_type)

    result = {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "categories": categories,
        "description": description,
        "requirements": description,
        "apply_url": apply_url,
    }
    return result


def _looks_like_cloudflare_challenge(html: str) -> bool:
    lowered = html.lower()
    return "just a moment" in lowered or "challenge-platform" in lowered or "cf_chl_opt" in lowered


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    no_tags = TAG_RE.sub(" ", unescape(value))
    return WHITESPACE_RE.sub(" ", no_tags).strip()


def _match(pattern: re.Pattern[str], text: str, group: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(group)
