from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_WAIT_SELECTOR = 'a[href*="/vacancy/"]'
NEGOTIATIONS_PAGER_SELECTOR = 'button[data-qa*="number-pages-"]'
DEFAULT_COOKIE_BUTTONS = [
    "text=Принять",
    "text=Согласен",
    "text=Понятно",
    "text=Accept",
    "text=OK",
]


class PlaywrightUnavailableError(RuntimeError):
    """Raised when browser automation is requested but Playwright is unavailable."""


class ExportPageNotReadyError(RuntimeError):
    """Raised when the target page never exposes the expected content."""


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    metadata_path: Path
    final_url: str
    page_title: str
    vacancy_link_count: int
    captured_pages: int


def export_hh_page(
    *,
    url: str,
    output_path: str | Path,
    browser_name: str = "chromium",
    headless: bool = False,
    wait_selector: str = DEFAULT_WAIT_SELECTOR,
    timeout_ms: int = 30000,
    login_wait_seconds: int = 0,
    max_scrolls: int = 12,
    scroll_pause_ms: int = 1000,
    storage_state_path: str | Path | None = None,
    save_storage_state_path: str | Path | None = None,
    user_data_dir: str | Path | None = None,
    screenshot_path: str | Path | None = None,
) -> ExportResult:
    sync_playwright, playwright_timeout = _load_playwright()

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output.with_suffix(f"{output.suffix}.meta.json" if output.suffix else ".meta.json")

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name, None)
        if browser_type is None:
            raise ValueError(f"Unsupported Playwright browser: {browser_name}")

        browser = None
        context = None
        try:
            if user_data_dir:
                context = browser_type.launch_persistent_context(
                    user_data_dir=str(Path(user_data_dir)),
                    headless=headless,
                )
            else:
                browser = browser_type.launch(headless=headless)
                context_kwargs: dict[str, Any] = {}
                if storage_state_path:
                    context_kwargs["storage_state"] = str(Path(storage_state_path))
                context = browser.new_context(**context_kwargs)

            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            _dismiss_cookie_banners(page)

            if login_wait_seconds > 0:
                _wait_for_login_or_ready(
                    page,
                    wait_selector=wait_selector,
                    login_wait_seconds=login_wait_seconds,
                    playwright_timeout=playwright_timeout,
                )

            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms, state="attached")
            except playwright_timeout as exc:
                debug = _capture_debug_artifacts(
                    page,
                    output=output,
                    metadata_path=metadata_path,
                    screenshot_path=screenshot_path,
                    requested_url=url,
                    wait_selector=wait_selector,
                    browser_name=browser_name,
                    headless=headless,
                    login_wait_seconds=login_wait_seconds,
                    max_scrolls=max_scrolls,
                    error_message=str(exc),
                )
                raise ExportPageNotReadyError(
                    f"hh.ru page did not expose selector {wait_selector!r}. "
                    f"final_url={debug['final_url']} title={debug['page_title']!r} "
                    f"html={output} meta={metadata_path}"
                ) from exc

            _wait_for_load(page, timeout_ms, playwright_timeout)
            if max_scrolls > 0 and _same_page_family(page.url, url):
                _scroll_page(page, max_scrolls=max_scrolls, pause_ms=scroll_pause_ms)

            html, captured_pages = _collect_paginated_html(
                page,
                wait_selector=wait_selector,
                timeout_ms=timeout_ms,
                max_scrolls=max_scrolls,
                scroll_pause_ms=scroll_pause_ms,
                playwright_timeout=playwright_timeout,
            )
            output.write_text(html, encoding="utf-8")

            if screenshot_path:
                screenshot = Path(screenshot_path)
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=True)

            if save_storage_state_path:
                storage_output = Path(save_storage_state_path)
                storage_output.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(storage_output))

            link_count = page.locator(wait_selector).count()
            metadata = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "requested_url": url,
                "final_url": page.url,
                "page_title": page.title(),
                "wait_selector": wait_selector,
                "vacancy_link_count": link_count,
                "browser_name": browser_name,
                "headless": headless,
                "login_wait_seconds": login_wait_seconds,
                "max_scrolls": max_scrolls,
                "captured_pages": captured_pages,
            }
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            return ExportResult(
                output_path=output,
                metadata_path=metadata_path,
                final_url=page.url,
                page_title=page.title(),
                vacancy_link_count=link_count,
                captured_pages=captured_pages,
            )
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()


def _load_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise PlaywrightUnavailableError(
            "Playwright is not installed. Install it with `pip install playwright==1.58.0` "
            "and then run `python3 -m playwright install chromium`."
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def _dismiss_cookie_banners(page: Any) -> None:
    for selector in DEFAULT_COOKIE_BUTTONS:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=500):
                button.click(timeout=1000)
                return
        except Exception:
            continue


def _wait_for_load(page: Any, timeout_ms: int, playwright_timeout: type[Exception]) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except playwright_timeout:
        pass


def _wait_for_login_or_ready(
    page: Any,
    *,
    wait_selector: str,
    login_wait_seconds: int,
    playwright_timeout: type[Exception],
) -> None:
    try:
        page.wait_for_selector(wait_selector, timeout=login_wait_seconds * 1000, state="attached")
    except playwright_timeout:
        pass


def _scroll_page(page: Any, *, max_scrolls: int, pause_ms: int) -> None:
    previous_height = -1
    stable_rounds = 0
    for _ in range(max_scrolls):
        current_height = page.evaluate("() => document.body.scrollHeight")
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_ms)
        new_height = page.evaluate("() => document.body.scrollHeight")
        if new_height == previous_height == current_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
        previous_height = new_height


def _collect_paginated_html(
    page: Any,
    *,
    wait_selector: str,
    timeout_ms: int,
    max_scrolls: int,
    scroll_pause_ms: int,
    playwright_timeout: type[Exception],
) -> tuple[str, int]:
    visited_pages: set[str] = set()
    snapshots: list[str] = []

    while True:
        current_page = _current_page_label(page)
        page_key = current_page or f"page-{len(snapshots) + 1}"
        if page_key not in visited_pages:
            visited_pages.add(page_key)
            snapshots.append(f"<!-- hh_monitor_page:{page_key} -->\n{page.content()}")

        next_page = _next_unvisited_page(page, visited_pages)
        if next_page is None:
            break

        locator = page.locator(f'button[data-qa*="number-pages-{next_page}"]').first
        locator.click(timeout=timeout_ms)
        _wait_for_selected_page(page, next_page=next_page, timeout_ms=timeout_ms, playwright_timeout=playwright_timeout)
        page.wait_for_selector(wait_selector, timeout=timeout_ms, state="attached")
        _wait_for_load(page, timeout_ms, playwright_timeout)
        if max_scrolls > 0:
            _scroll_page(page, max_scrolls=max_scrolls, pause_ms=scroll_pause_ms)

    return "\n\n".join(snapshots), len(snapshots)


def _current_page_label(page: Any) -> str | None:
    selected = page.locator('button[data-qa*="number-pages-selected"]').first
    if selected.count() == 0:
        selected = page.locator('button[aria-current="true"][data-qa*="number-pages-"]').first
    if selected.count() == 0:
        return None
    text = selected.inner_text().strip()
    return text or None


def _next_unvisited_page(page: Any, visited_pages: set[str]) -> str | None:
    buttons = page.locator(NEGOTIATIONS_PAGER_SELECTOR)
    count = buttons.count()
    page_numbers: list[str] = []
    for index in range(count):
        data_qa = buttons.nth(index).get_attribute("data-qa") or ""
        page_label = _extract_page_label(data_qa)
        if page_label and page_label not in page_numbers:
            page_numbers.append(page_label)

    for page_label in page_numbers:
        if page_label not in visited_pages:
            return page_label
    return None


def _extract_page_label(data_qa: str) -> str | None:
    for part in data_qa.split():
        if part.startswith("number-pages-"):
            value = part.removeprefix("number-pages-").strip()
            if value.isdigit():
                return value
    return None


def _wait_for_selected_page(page: Any, *, next_page: str, timeout_ms: int, playwright_timeout: type[Exception]) -> None:
    try:
        page.wait_for_function(
            """target => {
                const selected = document.querySelector('button[data-qa*="number-pages-selected"], button[aria-current="true"][data-qa*="number-pages-"]');
                return selected && selected.textContent && selected.textContent.trim() === target;
            }""",
            arg=next_page,
            timeout=timeout_ms,
        )
    except playwright_timeout:
        pass


def _capture_debug_artifacts(
    page: Any,
    *,
    output: Path,
    metadata_path: Path,
    screenshot_path: str | Path | None,
    requested_url: str,
    wait_selector: str,
    browser_name: str,
    headless: bool,
    login_wait_seconds: int,
    max_scrolls: int,
    error_message: str,
) -> dict[str, Any]:
    html = page.content()
    output.write_text(html, encoding="utf-8")

    actual_screenshot_path: str | None = None
    if screenshot_path:
        screenshot = Path(screenshot_path)
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        actual_screenshot_path = str(screenshot)

    metadata = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "requested_url": requested_url,
        "final_url": page.url,
        "page_title": page.title(),
        "wait_selector": wait_selector,
        "browser_name": browser_name,
        "headless": headless,
        "login_wait_seconds": login_wait_seconds,
        "max_scrolls": max_scrolls,
        "error": error_message,
        "screenshot_path": actual_screenshot_path,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _same_page_family(current_url: str, requested_url: str) -> bool:
    return _path_family(current_url) == _path_family(requested_url)


def _path_family(url: str) -> str:
    if "://" not in url:
        return url
    tail = url.split("://", 1)[1]
    if "/" not in tail:
        return "/"
    path = "/" + tail.split("/", 1)[1]
    return path.split("?", 1)[0].rstrip("/") or "/"
