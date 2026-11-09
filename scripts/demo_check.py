"""Click through the whole demo in a real browser and save screenshots.

    make demo-check        (servers must be running: make dev)

Uses the locally installed Google Chrome via Playwright. Fails loudly if any step
of the Acme flow doesn't reach the expected state.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = "http://localhost:3000"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-shots")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name: str, full: bool = True):
    page.wait_for_timeout(1400)  # let entrance animations settle
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("saved", OUT / f"{name}.png")


def main():
    urllib.request.urlopen(urllib.request.Request("http://localhost:8000/api/admin/reset", method="POST"))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)

        page.goto(WEB)
        expect(page.get_by_text("Acme Industrial Supply")).to_be_visible()
        shot(page, "01-inbox")

        page.get_by_text("Acme Industrial Supply").click()
        expect(page.get_by_role("button", name="Run Matchbook")).to_be_visible()
        shot(page, "02-case-open", full=False)

        page.get_by_role("button", name="Run Matchbook").click()
        page.wait_for_timeout(3500)
        shot(page, "03-case-running", full=False)
        expect(page.get_by_text("Ready for your approval", exact=False).first).to_be_visible(timeout=30000)
        shot(page, "04-case-pending-approval")

        page.get_by_role("button", name="Approve & send").click()
        expect(page.get_by_role("button", name="Fast-forward follow-up")).to_be_visible(timeout=10000)
        page.get_by_role("button", name="Fast-forward follow-up").click()
        expect(page.get_by_text("Synced to Ramp", exact=True)).to_be_visible(timeout=30000)
        page.evaluate("window.scrollTo(0, 0)")
        shot(page, "05-case-synced")

        page.goto(f"{WEB}/cases/MB-0419")
        page.get_by_role("button", name="Run Matchbook").click()
        expect(page.get_by_text("Ready for your approval", exact=False).first).to_be_visible(timeout=30000)
        shot(page, "06-injection")

        page.goto(f"{WEB}/cases/MB-2207")
        page.get_by_role("button", name="Run Matchbook").click()
        expect(page.get_by_text("Ready for your approval", exact=False).first).to_be_visible(timeout=30000)
        shot(page, "07-legit-increase")

        page.goto(f"{WEB}/cases/MB-2290")
        page.get_by_role("button", name="Run Matchbook").click()
        expect(page.get_by_text("Handed to a person", exact=True)).to_be_visible(timeout=30000)
        shot(page, "08-escalated", full=False)

        page.goto(f"{WEB}/evals")
        page.get_by_role("button", name="Run the eval").click()
        expect(page.get_by_text("handled correctly")).to_be_visible(timeout=120000)
        shot(page, "09-scorecard")

        # Detailed mode: same pages with the full text layer.
        page.get_by_role("radio", name="detailed").click()
        expect(page.get_by_text("Expected").first).to_be_visible()
        shot(page, "11-scorecard-detailed")
        page.goto(f"{WEB}/cases/MB-4471")
        expect(page.get_by_text("Engine findings")).to_be_visible(timeout=10000)
        expect(page.get_by_text("Message thread")).to_be_visible()
        shot(page, "12-case-detailed")
        page.goto(WEB)
        shot(page, "13-inbox-detailed")
        page.get_by_role("radio", name="simple").click()
        expect(page.get_by_text("Engine findings")).to_have_count(0)

        # Ramp theme: switch, reload (must persist with no flash), capture, switch back.
        page.get_by_role("radio", name="Ramp").click()
        page.reload()
        assert page.evaluate("document.documentElement.dataset.theme") == "ramp"
        shot(page, "14-ramp-inbox")
        page.goto(f"{WEB}/cases/MB-4471")
        expect(page.get_by_text("Synced to Ramp", exact=True)).to_be_visible(timeout=10000)
        shot(page, "15-ramp-case")
        page.goto(f"{WEB}/cases/MB-0419")
        expect(page.get_by_text("Ready for your approval").first).to_be_visible(timeout=10000)
        shot(page, "16-ramp-approval")
        page.goto(f"{WEB}/evals")
        shot(page, "17-ramp-scorecard")
        page.get_by_role("radio", name="Editorial").click()
        assert page.evaluate("document.documentElement.dataset.theme") == "editorial"

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(WEB)
        expect(page.get_by_text("Acme Industrial Supply")).to_be_visible()
        shot(page, "10-mobile-inbox")
        browser.close()
    print("Demo flow OK")


if __name__ == "__main__":
    main()
