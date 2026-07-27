#!/usr/bin/env python3
"""Reusable Playwright QA snapshot harness for phantom-ledger web UI.

Loads a URL against the running dev server, waits for network idle, captures
any console/page errors and failed network requests, and saves a screenshot.
Replaces the ad-hoc Playwright boilerplate that used to get rewritten each
session.

Usage:
    uv run python scripts/qa_snapshot.py [PATH_OR_URL] [--out screenshot.png] [--full-page]

Examples:
    uv run python scripts/qa_snapshot.py /quick
    uv run python scripts/qa_snapshot.py /positions/abc123 --out /tmp/pos.png
    uv run python scripts/qa_snapshot.py http://127.0.0.1:8000/ --full-page

Exit code is non-zero if any console errors or failed requests were captured,
so it can be used as a quick pass/fail gate.
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://127.0.0.1:8000"


def resolve_url(target: str) -> str:
    if target.startswith("http://") or target.startswith("https://"):
        return target
    if not target.startswith("/"):
        target = "/" + target
    return DEFAULT_BASE + target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="/", help="Path (e.g. /quick) or full URL")
    parser.add_argument("--out", default="/tmp/phantom_qa_snapshot.png", help="Screenshot output path")
    parser.add_argument("--full-page", action="store_true", help="Capture full scrollable page")
    parser.add_argument("--timeout", type=int, default=15000, help="Navigation timeout in ms")
    args = parser.parse_args()

    url = resolve_url(args.target)
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.on(
            "console",
            lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
            if msg.type == "error"
            else None,
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "requestfailed",
            lambda req: failed_requests.append(
                f"{req.method} {req.url} -> {req.failure}"
            ),
        )
        page.on(
            "response",
            lambda resp: failed_requests.append(f"{resp.request.method} {resp.url} -> {resp.status}")
            if resp.status >= 400
            else None,
        )

        print(f"Navigating to {url} ...")
        page.goto(url, wait_until="networkidle", timeout=args.timeout)
        page.screenshot(path=args.out, full_page=args.full_page)
        browser.close()

    print(f"Screenshot saved to {args.out}")

    ok = True
    if console_errors:
        ok = False
        print(f"\nConsole errors ({len(console_errors)}):")
        for e in console_errors:
            print(f"  {e}")
    if page_errors:
        ok = False
        print(f"\nPage errors ({len(page_errors)}):")
        for e in page_errors:
            print(f"  {e}")
    if failed_requests:
        ok = False
        print(f"\nFailed/errored requests ({len(failed_requests)}):")
        for e in failed_requests:
            print(f"  {e}")

    if ok:
        print("\nNo console errors, page errors, or failed requests detected.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
