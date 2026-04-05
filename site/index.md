Home | [Article Catalog](catalog.html)

# Abstract Wikipedia Editor

A desktop editor and automation toolkit for creating and editing articles on [Abstract Wikipedia](https://abstract.wikipedia.org/).

Abstract Wikipedia stores articles as language-neutral function calls that render into every language automatically. This project provides an Electron desktop app for writing and previewing articles, plus command-line tools for batch creation.

## Download

**[Download ZIP](https://github.com/EmmaLeonhart/AbstractWikipediaEditor/archive/refs/heads/master.zip)** | [View on GitHub](https://github.com/EmmaLeonhart/AbstractWikipediaEditor)

After extracting, run the desktop editor:

```bash
cd editor
npm install
npm start
```

The desktop editor lets you:
- Enter any Wikidata QID and pull its properties
- Auto-generate wikitext templates from Wikidata
- Live preview with resolved English labels (same renderer used on this site)
- Pull existing articles from Abstract Wikipedia
- Push edits back to Abstract Wikipedia

## How it works

1. **Wikitext templates** map Wikidata properties to Wikifunctions sentence generators
2. Each `{{function | arg1 | arg2}}` block becomes one article fragment
3. The renderer resolves QIDs to labels and renders English sentences
4. Articles are published via Playwright browser automation (the API doesn't support it)

### Example template

```
{{location | $subject | Q845945 | Q17}}
{{spo | Q1762010 | $subject | Q3080728}}
```

Renders as: "Sasuke Inari Shrine is a Shinto shrine in Japan. Sasuke Inari Shrine is dedication of Inari."

## Article catalog

Abstract Wikipedia articles often fail to render in the browser. This catalog provides pre-rendered English previews of all articles on Abstract Wikipedia, so you can actually see what each article says.

**[View rendered articles](catalog.html)** -- every Abstract Wikipedia article with live English rendering powered by the same engine as the desktop editor.

## Links

- [GitHub repository](https://github.com/EmmaLeonhart/AbstractWikipediaEditor)
- [Abstract Wikipedia](https://abstract.wikipedia.org/)
- [Full documentation](https://github.com/EmmaLeonhart/AbstractWikipediaEditor/blob/master/DOCUMENTATION.md)
