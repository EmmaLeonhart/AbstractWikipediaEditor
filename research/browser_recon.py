"""Quick recon: see what the edit page looks like on Abstract Wikipedia."""

import io
import sys
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

WIKI_URL = "https://abstract.wikipedia.org"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Check the edit page for a non-existent Q article (no login)
    print("--- Checking edit page for Q29682 (not logged in) ---")
    page.goto(f"{WIKI_URL}/w/index.php?title=Q29682&action=edit")
    page.wait_for_load_state("networkidle")
    print(f"URL: {page.url}")

    # Check for textarea
    ta = page.locator("#wpTextbox1")
    print(f"Textarea found: {ta.count() > 0}")

    # Check for any form elements
    forms = page.locator("form").count()
    print(f"Forms on page: {forms}")

    # Check for any Vue/React app container (Abstract Wiki might use a custom editor)
    app_div = page.locator("#ext-wikilambda-app, .ext-wikilambda-app, [data-app]")
    print(f"WikiLambda app container found: {app_div.count() > 0}")

    # Get page title text
    heading = page.locator("h1").first.text_content() if page.locator("h1").count() > 0 else "No heading"
    print(f"Page heading: {heading}")

    # Look for any relevant elements
    body_text = page.locator("body").inner_text()[:2000]
    print(f"\nPage text (first 2000 chars):\n{body_text}")

    # Take screenshot
    page.screenshot(path="recon_edit_page.png")
    print("\nScreenshot saved: recon_edit_page.png")

    # Also check what the create page looks like directly
    print("\n--- Checking Q29682 view page ---")
    page.goto(f"{WIKI_URL}/wiki/Q29682")
    page.wait_for_load_state("networkidle")
    print(f"URL: {page.url}")
    body_text2 = page.locator("body").inner_text()[:1000]
    print(f"Page text:\n{body_text2}")

    page.screenshot(path="recon_view_page.png")
    print("Screenshot saved: recon_view_page.png")

    browser.close()
