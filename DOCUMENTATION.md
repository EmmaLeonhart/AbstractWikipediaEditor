# Abstract Wikipedia Editor: Technical Documentation

## Overview

This document covers the technical details of how the Abstract Wikipedia Editor works, including all the API dead ends and workarounds discovered during development. Abstract Wikipedia's API does not support creating or editing articles, so we use Playwright browser automation to publish through the visual editor.

---

## Abstract Wikipedia: What You Need to Know

### It is NOT a normal MediaWiki wiki

Abstract Wikipedia runs on MediaWiki but uses a custom extension called **WikiLambda**. Pages in the main namespace use the `abstractwiki` content model (not `wikitext`). This means:

- Pages are JSON documents, not wikitext
- The visual editor is a custom Vue.js app, not the standard MediaWiki editor
- There is no source editor / textarea — you cannot view or edit raw JSON through the web UI
- The API does not support creating or editing articles

### Article structure

An Abstract Wikipedia article is JSON with this structure:

```json
{
    "qid": "Q11581011",
    "sections": {
        "Q8776414": {
            "index": 0,
            "fragments": [
                "Z89",
                {
                    "Z1K1": "Z7",
                    "Z7K1": "Z27868",
                    "Z27868K1": { ... nested function calls ... }
                }
            ]
        }
    }
}
```

Key identifiers:
- **Q8776414** = "lead paragraph" (section type from Wikidata)
- **Z89** = HTML fragment type
- **Z27868** = "string to HTML fragment" function
- **Z14396** = "string of monolingual text" function
- **Z26570** = "State location using entity and class" function (generates the actual text)
- **Z6091** = Wikidata entity reference wrapper
- **Z18** = Argument reference (pulls dynamic data like entity name)

The nested function calls evaluate to produce text like: "Kashima Shrine is a Shinto shrine in Kashima."

### The raw JSON can be fetched

You CAN read article content via:
```
https://abstract.wikipedia.org/w/index.php?title=Q11581011&action=raw
```

This returns the JSON. But you CANNOT write it back via the API.

---

## What We Tried and Why It Failed

### Attempt 1: Standard MediaWiki API (`action=edit`) with `contentmodel=zobject`

**Error:** `no-direct-editing` — "Direct editing via API is not supported for content model zobject"

**Why:** `zobject` is the content model for Z-objects (functions, types on Wikifunctions), not for Abstract Wikipedia articles.

### Attempt 2: `action=edit` with `contentmodel=abstractwiki`

**Error:** `protectednamespace` — "You do not have permission to edit pages in the Page namespace."

**Why:** The `action=edit` endpoint simply does not work with the `abstractwiki` content model. The main namespace on Abstract Wikipedia requires WikiLambda-specific rights (`wikilambda-abstract-create`, `wikilambda-abstract-edit`) that are not accessible through the API.

### Attempt 3: `wikilambda_edit` API endpoint

**Error:** `wikilambda-zerror` — "Error of type Z559"

**Why:** The `wikilambda_edit` endpoint is designed for Z-objects (functions, types, implementations on Wikifunctions). It expects ZObject format (with Z2K1, Z2K2, Z2K3 wrapper keys), not the abstractwiki article JSON format.

### Attempt 4: Browser automation — force-clicking Publish on empty template

**Result:** Pages were created, but with only `"Z89"` in the fragments array — no actual content. The editor needs real fragment data before publishing.

### Attempt 5: Browser automation — clipboard paste (WHAT WORKS)

**The winning approach.** See next section.

---

## What Actually Works: The Browser Automation Approach

### Login

We log in through the browser UI. The editor opens a Playwright browser, fills in the login form, and waits for the redirect. VPN usage may trigger email verification (see Authentication section below).

### The clipboard injection workflow

Abstract Wikipedia's editor has an internal clipboard stored in browser localStorage. The workflow is:

1. Compile wikitext templates to Z-object JSON (clipboard format)
2. Navigate to the article's edit page
3. For each fragment:
   - Inject the clipboard item into localStorage and the Pinia store
   - Click "Add empty fragment"
   - Click the fragment's three-dots menu → "Paste from clipboard"
   - Select the item in the clipboard dialog
4. Force-enable the Publish button via JS
5. Click Publish, then confirm in the dialog

### Critical UI selectors

| Element | Selector |
|---------|----------|
| + button | `button[aria-label='Menu for selecting and adding a new fragment']` |
| "Add empty fragment" | `get_by_role("option", name="Add empty fragment")` |
| Three-dots menu | `button[aria-label*='fragment-actions-menu']` |
| "Paste from clipboard" | `get_by_role("option", name="Paste from clipboard")` |
| Clipboard item | `div.ext-wikilambda-app-clipboard__item` |
| Publish button | `button.ext-wikilambda-app-abstract-publish__publish` |

### Timing matters

The Vue editor needs time to render. Key wait points:
- After page load: **5 seconds** for the editor app to initialize
- After clicking menu items: **1-2 seconds** for menu animations
- After paste: **2 seconds** for content to render

### Force-enabling Publish

The Publish button starts disabled and only enables when the editor detects changes. After pasting content, we force-enable it:

```javascript
const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
if (btn) { btn.removeAttribute('disabled'); btn.disabled = false; }
```

This is safe — the content is genuinely there, the disabled state is just a UI quirk.

---

## Authentication: VPN vs 2FA

The email verification prompts during login are **NOT two-factor authentication (2FA)**. They are triggered by **VPN usage**. When Wikimedia detects a login from an unfamiliar IP (as happens with VPN), it sends an email verification code as a security check. Without VPN, login proceeds directly without any verification step.

This distinction matters because:
- **VPN-triggered verification** only happens when the IP looks suspicious
- CI runners (GitHub Actions, etc.) always use unfamiliar IPs, so they always trigger verification — this is why CI-based article creation is disabled
- Running locally without VPN avoids the verification entirely

---

## Credentials

The editor stores Wikimedia credentials in a `.env` file in the project root. You can enter these through the Login button in the desktop editor.

| Credential | .env key | Purpose |
|-----------|----------|---------|
| Username | `WIKI_USERNAME` | Your Wikimedia account |
| Main password | `WIKI_MAIN_PASSWORD` | Used for browser login to create/edit articles |

---

## Available API Endpoints

### WikiLambda-specific actions on abstract.wikipedia.org

| Action | Purpose | Works for articles? |
|--------|---------|-------------------|
| `wikilambda_edit` | Edit Z-objects | NO (only Z-objects, not abstractwiki content) |
| `wikilambda_fetch` | Fetch Z-objects by ZID | NO (only Z-IDs, not Q-IDs) |
| `abstractwiki_run_fragment` | Render a fragment | Read-only |

### Standard MediaWiki actions that work

| Action | Purpose | Notes |
|--------|---------|-------|
| `action=query` | Check page existence, get tokens | Works normally |
| `action=login` | Log in | Works |
| `action=parse` | Parse page content | Works, returns rendered HTML |
| `action=edit` with `contentmodel=abstractwiki` | Create/edit articles | Does not work |

---

## Wikitext Generation Pipeline

The path from a Wikidata QID to a published article goes through three stages:

### Stage 1: Wikidata → Wikitext (`generate_wikitext.py`)

Given a QID, the script fetches the item's claims from the Wikidata API and maps each property to a Wikifunctions sentence generator using `data/property_function_mapping.json`.

For example, Sophocles (Q7235) has P106 (occupation: tragedy writer) and P27 (citizenship: Classical Athens). The mapping produces:

```
{{Z28016|SUBJECT|Q22073916|Q844930}}
```

Which renders as: "Sophocles is a tragedy writer of Classical Athens."

**Deduplication rules** prevent redundant or awkward sentences:
- **Location priority**: P131 (admin territory) > P17 (country) > P30 (continent) — only the most specific is used
- **Occupation over instance**: P31 (instance of) is skipped when P106 (occupation) exists, since "X is a human" adds nothing when "X is a physicist" is already there
- **Occupation + citizenship merge**: When both P106 and P27 exist, they combine into one Z28016 call using the occupation as the role, instead of generating two separate sentences
- **Capital inverse**: P1376 (capital of) is skipped when P36 (capital) exists — they express the same relationship from opposite directions

### Stage 2: Wikitext → Z-object JSON (`wikitext_parser.py`)

The parser reads the wikitext template and converts each `{{...}}` block into the nested Z-object JSON that Abstract Wikipedia's visual editor expects. It handles:

- Resolving function aliases (`location` → `Z26570`) using `data/function_aliases.json`
- Wrapping Q-items as Wikidata entity references (`Z6091`)
- Resolving `SUBJECT` and `$lang` to the article's entity and language
- Auto-wrapping return types (Z11-returning functions get `Z29749`, Z6-returning get `Z27868`)

### Stage 3: Publish via Playwright (`create_from_qid.py` / `edit_from_qid.py`)

The compiled JSON is injected into the editor's localStorage clipboard and pasted via the visual editor. See the "What Actually Works" section above for the full browser automation workflow.

---

## Running the Desktop Editor

```bash
cd editor
npm install
npm start
```

Or double-click `runeditor.bat` on Windows.

The editor calls Python scripts (`generate_wikitext.py`, `create_from_qid.py`, `edit_from_qid.py`) for Wikidata fetching and Playwright publishing. These require Python 3.13+ with `requests`, `python-dotenv`, `pyyaml`, and `playwright`.

---

## Lessons Learned

1. **Abstract Wikipedia is not a normal wiki.** Don't assume standard MediaWiki API patterns work. The entire editing stack is custom.

2. **There is no API for creating articles.** The `action=edit` endpoint does not work with the `abstractwiki` content model. The `wikilambda_edit` endpoint is for Z-objects only.

3. **The editor has its own clipboard.** It's stored in browser localStorage, not the OS clipboard. You inject data into it programmatically via JavaScript.

4. **`contentmodel=zobject` vs `contentmodel=abstractwiki` are different things.** Z-objects are functions/types on Wikifunctions. Abstractwiki articles are the Q-pages on Abstract Wikipedia.

5. **UI selectors can be fragile.** The editor uses Vue.js with dynamic IDs that change between page loads. Use aria-labels and class names instead.

6. **The Publish button disabled state is an editor-side check.** It doesn't reflect server-side permissions. Force-enabling it via JS is safe when content is genuinely present.

7. **Timing is everything.** The Vue editor needs generous wait times. Rushing through clicks will cause failures.

8. **This may all change.** Abstract Wikipedia is under active development. The editing experience may become more regularized in the future.
