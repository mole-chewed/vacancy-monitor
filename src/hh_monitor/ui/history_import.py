from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re

from hh_monitor.models import ApplicationStatus, UiApplicationEntry
from hh_monitor.normalization import normalize_text


VACANCY_URL_RE = re.compile(r"(https?://hh\.ru)?/vacancy/(\d+)")
NEGOTIATIONS_ITEM_QA = "negotiations-item"
NEGOTIATIONS_TITLE_QA = "negotiations-item-vacancy"
NEGOTIATIONS_COMPANY_QA = "negotiations-item-company"
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

STATUS_PRIORITY = {
    ApplicationStatus.INTERVIEW: 5,
    ApplicationStatus.APPLIED: 4,
    ApplicationStatus.SAVED: 3,
    ApplicationStatus.REJECTED: 2,
    ApplicationStatus.IGNORE: 1,
}


class _VacancyLinkParser(HTMLParser):
    def __init__(self, default_status: ApplicationStatus, note: str | None) -> None:
        super().__init__()
        self.default_status = default_status
        self.note = note
        self.current_href: str | None = None
        self.current_parts: list[str] = []
        self.entries: list[UiApplicationEntry] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href and VACANCY_URL_RE.search(href):
            self.current_href = href
            self.current_parts = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self.current_href is None:
            return
        entry = _entry_from_link(self.current_href, "".join(self.current_parts), self.default_status, self.note)
        if entry is not None:
            self.entries.append(entry)
        self.current_href = None
        self.current_parts = []


class _NegotiationsParser(HTMLParser):
    def __init__(self, default_status: ApplicationStatus, note: str | None) -> None:
        super().__init__()
        self.default_status = default_status
        self.note = note
        self.entries: list[UiApplicationEntry] = []
        self._item_depth = 0
        self._current_item: dict[str, object] | None = None
        self._capture_stack: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        data_qa = normalize_text(attributes.get("data-qa"))
        href = attributes.get("href")

        if self._current_item is None and data_qa == NEGOTIATIONS_ITEM_QA:
            self._current_item = {
                "vacancy_id": None,
                "url": None,
                "title_parts": [],
                "company_parts": [],
                "status": self.default_status,
            }
            self._item_depth = 1
            return

        if self._current_item is None:
            return

        if tag not in VOID_TAGS:
            self._item_depth += 1

        if href and VACANCY_URL_RE.search(href):
            match = VACANCY_URL_RE.search(href)
            assert match is not None
            vacancy_id = match.group(2)
            self._current_item["vacancy_id"] = vacancy_id
            self._current_item["url"] = href if href.startswith("http") else f"https://hh.ru/vacancy/{vacancy_id}"

        if data_qa == NEGOTIATIONS_TITLE_QA:
            self._capture_stack.append(("title_parts", self._item_depth))
        elif data_qa == NEGOTIATIONS_COMPANY_QA:
            self._capture_stack.append(("company_parts", self._item_depth))
        else:
            mapped_status = _map_status_from_data_qa(data_qa)
            if mapped_status is not None:
                self._current_item["status"] = mapped_status

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self._current_item is None or not self._capture_stack:
            return
        field, _ = self._capture_stack[-1]
        value = normalize_text(data)
        if value:
            parts = self._current_item[field]
            assert isinstance(parts, list)
            parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if self._current_item is None:
            return

        if self._capture_stack and self._capture_stack[-1][1] == self._item_depth:
            self._capture_stack.pop()

        self._item_depth -= 1
        if self._item_depth > 0:
            return

        entry = _entry_from_negotiations_item(self._current_item, note=self.note)
        if entry is not None:
            self.entries.append(entry)
        self._current_item = None
        self._capture_stack = []


def load_ui_application_entries(
    path: str | Path,
    default_status: ApplicationStatus = ApplicationStatus.APPLIED,
    note: str | None = None,
) -> list[UiApplicationEntry]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    import_note = note or f"Imported from hh.ru UI file: {file_path.name}"
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_application_entries_from_json(stripped, default_status=default_status, note=import_note)
    return parse_application_entries_from_html(text, default_status=default_status, note=import_note)


def parse_application_entries_from_html(
    html: str,
    default_status: ApplicationStatus = ApplicationStatus.APPLIED,
    note: str | None = None,
) -> list[UiApplicationEntry]:
    negotiations_parser = _NegotiationsParser(default_status=default_status, note=note)
    negotiations_parser.feed(html)
    if negotiations_parser.entries:
        return _dedupe_entries(negotiations_parser.entries)

    parser = _VacancyLinkParser(default_status=default_status, note=note)
    parser.feed(html)
    return _dedupe_entries(parser.entries)


def parse_application_entries_from_json(
    text: str,
    default_status: ApplicationStatus = ApplicationStatus.APPLIED,
    note: str | None = None,
) -> list[UiApplicationEntry]:
    payload = json.loads(text)
    rows = payload if isinstance(payload, list) else payload.get("items", [])
    entries: list[UiApplicationEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        vacancy_id = _coerce_vacancy_id(row)
        if vacancy_id is None:
            continue
        url = _coerce_url(row, vacancy_id)
        title = normalize_text(
            row.get("title")
            or row.get("name")
            or row.get("vacancy_name")
            or (row.get("vacancy") or {}).get("name")
        )
        company = normalize_text(
            row.get("company")
            or row.get("employer_name")
            or (row.get("employer") or {}).get("name")
            or (row.get("vacancy") or {}).get("employer_name")
        )
        entries.append(
            UiApplicationEntry(
                vacancy_id=vacancy_id,
                url=url,
                title=title or f"Vacancy {vacancy_id}",
                company=company or None,
                status=default_status,
                note=note,
            )
        )
    return _dedupe_entries(entries)


def _entry_from_link(
    href: str,
    anchor_text: str,
    default_status: ApplicationStatus,
    note: str | None,
) -> UiApplicationEntry | None:
    match = VACANCY_URL_RE.search(href)
    if match is None:
        return None
    vacancy_id = match.group(2)
    url = href if href.startswith("http") else f"https://hh.ru/vacancy/{vacancy_id}"
    title = normalize_text(anchor_text) or f"Vacancy {vacancy_id}"
    return UiApplicationEntry(
        vacancy_id=vacancy_id,
        url=url,
        title=title,
        company=None,
        status=default_status,
        note=note,
    )


def _entry_from_negotiations_item(item: dict[str, object], note: str | None) -> UiApplicationEntry | None:
    vacancy_id = item.get("vacancy_id")
    if not isinstance(vacancy_id, str) or not vacancy_id:
        return None

    title = normalize_text(" ".join(_as_text_list(item.get("title_parts")))) or f"Vacancy {vacancy_id}"
    company = normalize_text(" ".join(_as_text_list(item.get("company_parts")))) or None
    url = item.get("url")
    status = item.get("status")
    return UiApplicationEntry(
        vacancy_id=vacancy_id,
        url=str(url) if isinstance(url, str) else f"https://hh.ru/vacancy/{vacancy_id}",
        title=title,
        company=company,
        status=status if isinstance(status, ApplicationStatus) else ApplicationStatus.APPLIED,
        note=note,
    )


def _coerce_vacancy_id(row: dict[str, object]) -> str | None:
    direct = row.get("vacancy_id") or row.get("id")
    if direct is not None and str(direct).isdigit():
        return str(direct)

    nested_vacancy = row.get("vacancy")
    if isinstance(nested_vacancy, dict):
        nested_id = nested_vacancy.get("id")
        if nested_id is not None and str(nested_id).isdigit():
            return str(nested_id)

    for candidate in [row.get("url"), row.get("alternate_url"), (nested_vacancy or {}).get("alternate_url")]:
        if isinstance(candidate, str):
            match = VACANCY_URL_RE.search(candidate)
            if match:
                return match.group(2)
    return None


def _coerce_url(row: dict[str, object], vacancy_id: str) -> str:
    for candidate in [
        row.get("url"),
        row.get("alternate_url"),
        (row.get("vacancy") or {}).get("alternate_url") if isinstance(row.get("vacancy"), dict) else None,
    ]:
        if isinstance(candidate, str) and candidate:
            return candidate
    return f"https://hh.ru/vacancy/{vacancy_id}"


def _dedupe_entries(entries: list[UiApplicationEntry]) -> list[UiApplicationEntry]:
    deduped: dict[str, UiApplicationEntry] = {}
    for entry in entries:
        existing = deduped.get(entry.vacancy_id)
        if existing is None or STATUS_PRIORITY[entry.status] >= STATUS_PRIORITY[existing.status]:
            deduped[entry.vacancy_id] = entry
    return list(deduped.values())


def _map_status_from_data_qa(data_qa: str) -> ApplicationStatus | None:
    normalized = data_qa.strip()
    if not normalized:
        return None
    if "negotiations-item-interview" in normalized:
        return ApplicationStatus.INTERVIEW
    if "negotiations-item-discard" in normalized:
        return ApplicationStatus.REJECTED
    if "negotiations-item-viewed" in normalized or "negotiations-item-not-viewed" in normalized:
        return ApplicationStatus.APPLIED
    if "negotiations-item-invitation" in normalized:
        return ApplicationStatus.SAVED
    return None


def _as_text_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
