Home | [Article Catalog](catalog.html) | [QuickStatements](quickstatements.html)

# Abstract Wikipedia Editor

## Why this exists

[Abstract Wikipedia](https://abstract.wikipedia.org/) is a Wikimedia project where articles are written as language-neutral function calls that can be rendered into any language automatically. It's a powerful idea, but right now it is extremely difficult to actually edit. There is no source editor, no wikitext mode, and no way to see what you're writing until you publish. The visual editor is a custom Vue.js app that works nothing like a traditional wiki, and articles frequently fail to render in the browser at all.

This project exists to make editing Abstract Wikipedia feel more like editing a traditional Wikipedia. You write human-readable wikitext templates, see a live English preview of what the article will say, and publish with one click.

## The API problem

Abstract Wikipedia's API does not currently support creating or editing articles. The standard MediaWiki `action=edit` endpoint does not work with the `abstractwiki` content model, and there is no alternative API for publishing article content.

To work around this, the editor uses [Playwright](https://playwright.dev/) browser automation to inject article content into the visual editor's internal clipboard and click through the publish flow. This is fragile and slower than API access, but it works.

Our hope is that this style of editing -- writing human-readable wikitext that compiles to Abstract Wikipedia's Z-objects -- could eventually become a normal mode of editing on Abstract Wikipedia itself, similar to how traditional Wikipedia offers both a visual editor and a source/code editor. The wikitext roundtrip (wikitext to Z-objects and back) could serve as the basis for a code editor view that sits alongside the existing visual editor.

We also envision this rendering approach being used as a default page for Wikidata items that don't yet have an Abstract Wikipedia article. Instead of showing a blank "this page does not exist" message, Abstract Wikipedia could auto-generate a preview from Wikidata properties, giving users a starting point to edit from rather than a blank page.

In the shorter term, we hope Abstract Wikipedia will open up direct API access for article creation so the browser automation can be replaced with straightforward API calls.

## Download

**[Download current version](https://github.com/EmmaLeonhart/AbstractWikipediaEditor/archive/refs/heads/master.zip)** | [View on GitHub](https://github.com/EmmaLeonhart/AbstractWikipediaEditor)

After extracting, run the desktop editor:

```bash
cd editor
npm install
npm start
```

## What the editor does

- Enter any Wikidata QID and auto-generate article content from its properties
- Write and edit wikitext templates with human-readable function names
- Live English preview that resolves Wikidata QIDs to labels as you type
- Pull existing articles from Abstract Wikipedia to edit them
- Push articles back to Abstract Wikipedia via browser automation
- Built-in login screen for Wikimedia credentials

### Example

A wikitext template like this:

```
{{location|SUBJECT|Q845945|Q17}}
{{spo|Q3080728|Q1762010|SUBJECT}}
```

Renders in the preview as: "Sasuke Inari Shrine is a Shinto shrine in Japan. Sasuke Inari Shrine is dedicated to Inari."

## Planned features

- **Multilingual preview** -- render articles in languages other than English, matching Abstract Wikipedia's core promise of language-neutral content
- **Expanded property coverage** -- map more Wikidata properties to Wikifunctions sentence generators beyond the current 17
- **Installable .exe** -- one-click Windows installer instead of requiring Node.js

## Article catalog

Abstract Wikipedia articles often fail to render in the browser. This catalog provides pre-rendered English previews of all articles on Abstract Wikipedia, so you can actually see what each article says.

**[View rendered articles](catalog.html)** -- every Abstract Wikipedia article with live English rendering powered by the same engine as the desktop editor.

## Links

- [GitHub repository](https://github.com/EmmaLeonhart/AbstractWikipediaEditor)
- [Abstract Wikipedia](https://abstract.wikipedia.org/)
- [Full documentation](https://github.com/EmmaLeonhart/AbstractWikipediaEditor/blob/master/DOCUMENTATION.md)
