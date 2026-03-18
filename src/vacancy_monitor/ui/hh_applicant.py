from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vacancy_monitor.ui.playwright_exporter import (
    PlaywrightUnavailableError,
    _dismiss_cookie_banners,
    _existing_storage_state_path,
    _load_playwright,
)

LOGGER = logging.getLogger(__name__)

APPLY_BUTTON_SELECTORS = [
    'button[data-qa="vacancy-response-link-top"]',
    'a[data-qa="vacancy-response-link-top"]',
    'button[data-qa="vacancy-response-link-bottom"]',
    'a[data-qa="vacancy-response-link-bottom"]',
]

ALREADY_APPLIED_SELECTORS = [
    'span[data-qa="vacancy-response-link-view-topic"]',
    'a[data-qa="vacancy-response-link-view-topic"]',
    'text=Вы откликнулись',
    'text=Отклик отправлен',
]

COVER_LETTER_SELECTORS = [
    'textarea[data-qa="vacancy-response-popup-form-letter-input"]',
    'textarea[data-qa="vacancy-response-letter-toggle"]',
    'textarea[name="letter"]',
]

SUBMIT_SELECTORS = [
    'button[data-qa="vacancy-response-submit-popup"]',
    'button[data-qa="vacancy-response-letter-submit"]',
    'button[type="submit"]',
]

LETTER_TOGGLE_SELECTORS = [
    'button[data-qa="vacancy-response-letter-toggle"]',
    'text=Сопроводительное письмо',
]

SUCCESS_INDICATORS = [
    'text=Отклик отправлен',
    'text=Вы откликнулись',
    'span[data-qa="vacancy-response-link-view-topic"]',
]


class ApplyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApplyResult:
    vacancy_id: str
    success: bool
    already_applied: bool
    error: str | None
    screenshot_path: str | None


def apply_to_vacancy(
    vacancy_url: str,
    vacancy_id: str,
    *,
    cover_letter: str | None = None,
    storage_state_path: str | Path | None = None,
    headless: bool = True,
    timeout_ms: int = 30000,
    screenshot_dir: str | Path | None = None,
) -> ApplyResult:
    sync_playwright, playwright_timeout = _load_playwright()

    screenshot_path: str | None = None
    if screenshot_dir:
        sd = Path(screenshot_dir)
        sd.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(sd / f"apply_{vacancy_id}.png")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context_kwargs: dict[str, Any] = {}
        resolved_state = _existing_storage_state_path(storage_state_path)
        if resolved_state:
            context_kwargs["storage_state"] = str(resolved_state)
        context = browser.new_context(**context_kwargs)

        try:
            page = context.new_page()
            page.goto(vacancy_url, wait_until="domcontentloaded", timeout=timeout_ms)
            _dismiss_cookie_banners(page)

            # Check if already applied
            if _is_already_applied(page):
                _take_screenshot(page, screenshot_path)
                return ApplyResult(
                    vacancy_id=vacancy_id,
                    success=False,
                    already_applied=True,
                    error=None,
                    screenshot_path=screenshot_path,
                )

            # Find and click apply button
            apply_btn = _find_first_visible(page, APPLY_BUTTON_SELECTORS, timeout_ms=3000)
            if not apply_btn:
                _take_screenshot(page, screenshot_path)
                return ApplyResult(
                    vacancy_id=vacancy_id,
                    success=False,
                    already_applied=False,
                    error="Apply button not found on page",
                    screenshot_path=screenshot_path,
                )

            apply_btn.click(timeout=timeout_ms)
            page.wait_for_timeout(1500)

            # Check if apply went through immediately (no modal)
            if _check_success(page):
                _take_screenshot(page, screenshot_path)
                return ApplyResult(
                    vacancy_id=vacancy_id,
                    success=True,
                    already_applied=False,
                    error=None,
                    screenshot_path=screenshot_path,
                )

            # Try to fill cover letter if modal appeared
            if cover_letter:
                _try_fill_cover_letter(page, cover_letter, timeout_ms)

            # Try to submit if there's a submit button in modal
            submit_btn = _find_first_visible(page, SUBMIT_SELECTORS, timeout_ms=2000)
            if submit_btn:
                submit_btn.click(timeout=timeout_ms)
                page.wait_for_timeout(2000)

            # Verify success
            if _check_success(page):
                _take_screenshot(page, screenshot_path)
                return ApplyResult(
                    vacancy_id=vacancy_id,
                    success=True,
                    already_applied=False,
                    error=None,
                    screenshot_path=screenshot_path,
                )

            # Also check if already applied appeared after clicking
            if _is_already_applied(page):
                _take_screenshot(page, screenshot_path)
                return ApplyResult(
                    vacancy_id=vacancy_id,
                    success=False,
                    already_applied=True,
                    error=None,
                    screenshot_path=screenshot_path,
                )

            _take_screenshot(page, screenshot_path)
            return ApplyResult(
                vacancy_id=vacancy_id,
                success=False,
                already_applied=False,
                error="Could not confirm application was submitted",
                screenshot_path=screenshot_path,
            )

        except PlaywrightUnavailableError:
            raise
        except Exception as exc:
            _take_screenshot_safe(page if "page" in dir() else None, screenshot_path)
            return ApplyResult(
                vacancy_id=vacancy_id,
                success=False,
                already_applied=False,
                error=str(exc),
                screenshot_path=screenshot_path,
            )
        finally:
            context.close()
            browser.close()


def _is_already_applied(page: Any) -> bool:
    for selector in ALREADY_APPLIED_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


def _check_success(page: Any) -> bool:
    for selector in SUCCESS_INDICATORS:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


def _find_first_visible(page: Any, selectors: list[str], *, timeout_ms: int = 2000) -> Any | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=timeout_ms):
                return locator
        except Exception:
            continue
    return None


def _try_fill_cover_letter(page: Any, text: str, timeout_ms: int) -> None:
    # Try to expand cover letter section first
    toggle = _find_first_visible(page, LETTER_TOGGLE_SELECTORS, timeout_ms=1000)
    if toggle:
        try:
            toggle.click(timeout=timeout_ms)
            page.wait_for_timeout(500)
        except Exception:
            pass

    textarea = _find_first_visible(page, COVER_LETTER_SELECTORS, timeout_ms=1500)
    if textarea:
        textarea.fill(text)


def _take_screenshot(page: Any, path: str | None) -> None:
    if path:
        try:
            page.screenshot(path=path, full_page=True)
        except Exception:
            pass


def _take_screenshot_safe(page: Any | None, path: str | None) -> None:
    if page and path:
        try:
            page.screenshot(path=path, full_page=True)
        except Exception:
            pass
