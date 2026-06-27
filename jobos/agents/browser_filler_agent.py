"""Placeholder for Phase 3 browser automation.

Do not enable auto-submit yet.
Start with Greenhouse/Lever only, fill green fields, and stop before final submission.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def fill_safe_fields(url: str, field_plan: Iterable[dict], cv_path: Path | None = None) -> None:
    """Open a browser and fill only fields marked action='auto_fill'.

    This is intentionally minimal and not wired into the MVP yet.
    Install browsers first with: playwright install
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url)

        for field in field_plan:
            if field.get("action") != "auto_fill":
                continue
            label = field.get("field_label")
            value = field.get("mapped_value")
            if not label or value is None:
                continue
            try:
                page.get_by_label(label).fill(str(value))
            except Exception as exc:  # noqa: BLE001 - useful during exploratory automation
                print(f"Could not fill {label!r}: {exc}")

        print("Safe fields filled where possible. Review manually before submitting.")
        input("Press Enter to close browser...")
        browser.close()
