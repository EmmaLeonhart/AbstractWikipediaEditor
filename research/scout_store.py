"""Explore the Pinia store to find how to inject article content."""

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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    page.goto(f"{WIKI_URL}/w/index.php?title=Q11259219&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)

    # Explore the Pinia store
    result = page.evaluate("""
        (() => {
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            if (!app) return 'no app';

            const pinia = app.config.globalProperties?.$pinia;
            if (!pinia) return 'no pinia';

            const mainStore = pinia._s.get('main');
            if (!mainStore) return 'no main store';

            // Get the store state keys
            const stateKeys = Object.keys(mainStore.$state);

            // Get actions (methods)
            const actionKeys = Object.getOwnPropertyNames(Object.getPrototypeOf(mainStore))
                .filter(k => typeof mainStore[k] === 'function' && !k.startsWith('$') && !k.startsWith('_'));

            return JSON.stringify({
                stateKeys: stateKeys,
                actionCount: actionKeys.length,
                actionSample: actionKeys.slice(0, 50)
            }, null, 2);
        })()
    """)
    print(f"Store structure:\n{result}", flush=True)

    # Now look at specific state values related to abstract/article content
    result2 = page.evaluate("""
        (() => {
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');
            const state = store.$state;

            // Look for anything related to abstract, article, section, fragment
            const relevant = {};
            for (const [key, value] of Object.entries(state)) {
                const k = key.toLowerCase();
                if (k.includes('abstract') || k.includes('article') || k.includes('section')
                    || k.includes('fragment') || k.includes('zobject') || k.includes('content')
                    || k.includes('page') || k.includes('dirty') || k.includes('change')
                    || k.includes('edit') || k.includes('publish')) {
                    relevant[key] = typeof value === 'object' ? JSON.stringify(value)?.slice(0, 300) : value;
                }
            }
            return JSON.stringify(relevant, null, 2);
        })()
    """)
    print(f"\nRelevant state:\n{result2}", flush=True)

    # Look at the zobjects state more closely
    result3 = page.evaluate("""
        (() => {
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');

            // Find actions related to setting/modifying content
            const allMethods = Object.getOwnPropertyNames(Object.getPrototypeOf(store))
                .filter(k => typeof store[k] === 'function');

            const relevantMethods = allMethods.filter(k => {
                const kl = k.toLowerCase();
                return kl.includes('set') || kl.includes('add') || kl.includes('abstract')
                    || kl.includes('fragment') || kl.includes('section') || kl.includes('submit')
                    || kl.includes('publish') || kl.includes('save') || kl.includes('zobject')
                    || kl.includes('dirty') || kl.includes('change') || kl.includes('paste');
            });

            return JSON.stringify(relevantMethods);
        })()
    """)
    print(f"\nRelevant methods:\n{result3}", flush=True)

    print("\nBrowser open for 15 seconds...", flush=True)
    time.sleep(15)
    browser.close()
