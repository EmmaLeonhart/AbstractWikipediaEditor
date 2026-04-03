"""Deep dive: look at store getters and how to manipulate fragments."""

import io
import sys
import os
import json
import time
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"


def api_login_cookies():
    session = requests.Session()
    session.headers.update({"User-Agent": "AbstractTestBot/1.0"})
    r = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "login", "format": "json"})
    login_token = r.json()["query"]["tokens"]["logintoken"]
    username = os.environ.get("WIKI_USERNAME", "").split("@")[0]
    password = os.environ.get("WIKI_MAIN_PASSWORD", "")
    r = session.post(API_URL, data={
        "action": "login", "lgname": username, "lgpassword": password,
        "lgtoken": login_token, "format": "json",
    })
    result = r.json()["login"]
    if result["result"] != "Success":
        raise RuntimeError(f"Login failed: {result}")
    print(f"Logged in as {result['lgusername']}", flush=True)
    return session.cookies.get_dict()


# First look at an EXISTING article to see how fragments are stored
SOURCE_QID = "Q11581011"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    # Look at existing article's store state
    print(f"Loading existing article {SOURCE_QID}...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={SOURCE_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)

    result = page.evaluate("""
        (() => {
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');

            return JSON.stringify({
                qid: store.qid,
                fragments: store.fragments,
                dirty: store.dirty,
                createNewPage: store.createNewPage,
                clipboardItems: store.clipboardItems,
                jsonObject: typeof store.jsonObject === 'string'
                    ? store.jsonObject.slice(0, 500)
                    : JSON.stringify(store.jsonObject)?.slice(0, 500),
            }, null, 2);
        })()
    """)
    print(f"Existing article store state:\n{result}", flush=True)

    # Now look at a NEW article
    print(f"\nLoading new article Q11259219...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title=Q11259219&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)

    result2 = page.evaluate("""
        (() => {
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');

            return JSON.stringify({
                qid: store.qid,
                fragments: store.fragments,
                dirty: store.dirty,
                createNewPage: store.createNewPage,
                jsonObject: typeof store.jsonObject === 'string'
                    ? store.jsonObject.slice(0, 500)
                    : JSON.stringify(store.jsonObject)?.slice(0, 500),
            }, null, 2);
        })()
    """)
    print(f"New article store state:\n{result2}", flush=True)

    # Now try: set the fragments and jsonObject directly, mark dirty
    RICH_ARTICLE = json.dumps({
        "qid": "Q11259219",
        "sections": {
            "Q8776414": {
                "index": 0,
                "fragments": [
                    "Z89",
                    {"Z1K1":"Z7","Z7K1":"Z27868","Z27868K1":{"Z1K1":"Z7","Z7K1":"Z14396","Z14396K1":{"Z1K1":"Z7","Z7K1":"Z26570","Z26570K1":{"Z1K1":"Z18","Z18K1":"Z825K1"},"Z26570K2":{"Z1K1":"Z6091","Z6091K1":"Q845945"},"Z26570K3":{"Z1K1":"Z6091","Z6091K1":"Q17"},"Z26570K4":{"Z1K1":"Z18","Z18K1":"Z825K2"}}}},
                    {"Z1K1":"Z7","Z7K1":"Z29749","Z29749K1":{"Z1K1":"Z7","Z7K1":"Z28016","Z28016K1":{"Z1K1":"Z6091","Z6091K1":"Q10948069"},"Z28016K2":{"Z1K1":"Z6091","Z6091K1":"Q11591100"},"Z28016K3":{"Z1K1":"Z18","Z18K1":"Z825K1"},"Z28016K4":{"Z1K1":"Z18","Z18K1":"Z825K2"}},"Z29749K2":{"Z1K1":"Z18","Z18K1":"Z825K2"}}
                ]
            }
        }
    })

    print(f"\nTrying to inject article content via store...", flush=True)
    result3 = page.evaluate(f"""
        (() => {{
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');

            const article = {RICH_ARTICLE};

            // Set the jsonObject
            store.jsonObject = JSON.stringify(article);
            store.dirty = true;

            // Also try setting fragments directly
            store.fragments = article.sections.Q8776414.fragments;

            return JSON.stringify({{
                dirty: store.dirty,
                jsonObject: store.jsonObject?.slice(0, 200),
                fragments: JSON.stringify(store.fragments)?.slice(0, 200),
            }});
        }})()
    """)
    print(f"After injection:\n{result3}", flush=True)

    time.sleep(2)
    page.screenshot(path="rich_02_after_inject.png")

    # Check if Publish is now enabled
    pub = page.locator("button.ext-wikilambda-app-abstract-publish__publish").first
    pub_disabled = pub.get_attribute("disabled")
    print(f"Publish disabled: {pub_disabled}", flush=True)

    # Check the preview
    preview = page.locator(".ext-wikilambda-app-abstract-preview__body")
    if preview.count() > 0:
        print(f"Preview: {preview.first.inner_text()[:300]}", flush=True)

    print("\nBrowser open for 20 seconds...", flush=True)
    time.sleep(20)
    browser.close()
