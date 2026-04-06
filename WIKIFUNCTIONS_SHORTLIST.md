# Wikifunctions Shortlist

Curated list of functions useful for building Abstract Wikipedia articles.
Focuses on **language-agnostic sentence generators** (multilingual dispatchers that accept a `language` argument)
and **structural/utility functions** for composing articles.

For the full catalog of all 3,911 functions and 71 types, see [`data/wikifunctions_catalog.json`](data/wikifunctions_catalog.json).

*See also: [Full catalog (too large for GitHub preview)](WIKIFUNCTIONS_CATALOG.md)*

---

## Currently Implemented

These functions are used by the editor's wikitext template system to create articles.

### Z26570: State location using entity and class ✅

> "Seoul is a city in South Korea."

| Arg | Key | Type |
|-----|-----|------|
| entity | `Z26570K1` | Wikidata item ref (Z6091) |
| class | `Z26570K2` | Wikidata item ref (Z6091) |
| location | `Z26570K3` | Wikidata item ref (Z6091) |
| language | `Z26570K4` | Natural language (Z60) |

**Returns:** Monolingual text (Z11) | [View](https://www.wikifunctions.org/view/en/Z26570)

### Z28016: defining role sentence ✅

> "Paris is the capital of France." / "Elisabeth II is the mother of Charles III."

| Arg | Key | Type |
|-----|-----|------|
| subject | `Z28016K1` | Wikidata item ref (Z6091) |
| role | `Z28016K2` | Wikidata item ref (Z6091) |
| dependency | `Z28016K3` | Wikidata item ref (Z6091) |
| language | `Z28016K4` | Natural language (Z60) |

**Returns:** Monolingual text (Z11) | [View](https://www.wikifunctions.org/view/en/Z28016)

### Z29749: Monolingual text as HTML fragment w/ auto-langcode ✅

Wraps monolingual text into an HTML fragment with automatic language code detection.

| Arg | Key | Type |
|-----|-----|------|
| text | `Z29749K1` | Monolingual text (Z11) |
| requested language | `Z29749K2` | Natural language (Z60) |

**Returns:** HTML fragment (Z89) | [View](https://www.wikifunctions.org/view/en/Z29749)

### Z27868: string to HTML fragment ✅

Converts a plain string into an HTML fragment (escaping reserved characters).

| Arg | Key | Type |
|-----|-----|------|
| string | `Z27868K1` | String (Z6) |

**Returns:** HTML fragment (Z89) | [View](https://www.wikifunctions.org/view/en/Z27868)

### Z14396: string of monolingual text ✅

Extracts the raw string (without language) from a monolingual text.

| Arg | Key | Type |
|-----|-----|------|
| full monolingual text | `Z14396K1` | Monolingual text (Z11) |

**Returns:** String (Z6) | [View](https://www.wikifunctions.org/view/en/Z14396)

### Z6091: Wikidata item reference (Type) ✅

Wrapper type for Wikidata QIDs. Used in virtually every article-building function.

| Key | ID | Type |
|-----|-----|------|
| Wikidata item id | `Z6091K1` | String (Z6) |

[View](https://www.wikifunctions.org/view/en/Z6091)

---

## Promising: Sentence Generators (Multilingual)

These are the **multilingual dispatcher** functions — they accept a `language` argument and route to
language-specific implementations. These are the ones to target for new article types.

### Z26570: State location using entity and class ✅ (already implemented)

> "Seoul is a city in South Korea."

`(entity, class, location, language)` -> monolingual text

### Z28016: defining role sentence ✅ (already implemented)

> "Paris is the capital of France."

`(subject, role, dependency, language)` -> monolingual text

### Z26039: Article-less instantiating fragment

> "Nairobi is a city." / "Berlin is a city."

Takes an entity and its class, generates "X is a Y" without articles.

`(entity: Z6091, class: Z6091, language: Z60)` -> String | [View](https://www.wikifunctions.org/view/en/Z26039)

### Z26095: Article-ful instantiating fragment

> "An antelope is a mammal." / "A frog is an amphibian."

`(class: Z6091, super-class: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z26095)

### Z26627: Classifying a class of nouns

> "Antelopes are mammals." / "Squares are rectangles."

`(class: Z6091, class: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z26627)

### Z29591: describing entity with adjective / class

> "Venus is a rocky planet."

`(entity: Z6091, adjective: Z6091, class: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z29591)

### Z27173: Describe the class of a class

> "Ice is frozen water."

`(class being described: Z6091, adjective: Z6091, class describing: Z6091, language: Z60)` -> String | [View](https://www.wikifunctions.org/view/en/Z27173)

### Z29743: description of class with adjective and superclass

> "A sheep is a domesticated animal."

`(described class: Z6091, adjective: Z6091, superclass: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z29743)

### Z27243: Superlative definition

> "Mount Everest is the tallest mountain in Asia."

`(entity: Z6091, adjective: Z6091, class: Z6091, location: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z27243)

### Z27627: Ordinal class location fragment

> "Tokyo is the second-largest city in Asia."

`(entity: Z6091, ordinal: Z16683, adjectival: Z6095, class: Z6091, location: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z27627)

### Z26955: SPO sentence, S without and O with article

> "English is a language."

Subject-Predicate-Object sentence where subject has no article and object does.

`(Predicate: Z6091, Subject: Z6091, Object: Z6091, language: Z60)` -> String | [View](https://www.wikifunctions.org/view/en/Z26955)

### Z27137: indef number of objects phrase

> "1 watermelon" / "2 bikes"

`(number: Z13518, object: Z6091, language: Z60)` -> String | [View](https://www.wikifunctions.org/view/en/Z27137)

### Z30000: Sunset sentence for location on date

> "The sun set in Tokyo at 5:23 PM on March 28."

`(location: Z6091, date of sunset: Z20420, today's date: Z20420, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z30000)

### Z31405: Sentence that something begins

> "The beginning of X" / "X starts"

`(subject: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z31405)

### Z28803: short description for album

> "1968 album by The Beatles"

`(album: Z6091, language: Z60)` -> Monolingual text | [View](https://www.wikifunctions.org/view/en/Z28803)

---

## Promising: Article Structure & Rendering

Functions for composing fragments into full articles.

### Z29822: ArticlePlaceholder render article

Full article renderer from a Wikidata item — renders all statement groups.

`(display language: Z60, item: Z6091, include props with no best statements: Z40)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z29822)

### Z29786: ArticlePlaceholder render statement group list

Renders all statement groups for an item as a list.

`(display language: Z60, item: Z6091, include props with no best statements: Z40)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z29786)

### Z29784: ArticlePlaceholder render statement group

Renders a single statement group (one property with all its values).

`(display language: Z60, statements' predicate: Z6092, statements: list of Z6003)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z29784)

### Z29717: ArticlePlaceholder render main Wikidata statement

Renders a single main Wikidata statement.

`(display language: Z60, statement: Z6003)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z29717)

### Z33068: paragraph from sentences

Takes a list of sentences and creates a paragraph.

`(sentences: list of Z1)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z33068)

### Z32163: paragraph from list of sentences, space separated

Encloses a list of HTML fragments, separated by spaces, in paragraph tags.

`(list of sentences: list of Z89)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z32163)

### Z27849: join two HTML fragments

`(first: Z89, second: Z89)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z27849)

### Z27926: join multiple HTML fragments

`(fragments: list of Z89)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z27926)

### Z31465: section title

Create a section title out of a string.

`(title text: Z6)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z31465)

### Z32123: paragraph

Wrap content in HTML paragraph tags.

`(content: Z89)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z32123)

### Z30148: hatnote

Replacement for the hatnote template/Lua module.

`(note content: Z6)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z30148)

### Z32218: Abstract Wikipedia list

Renders a list of Wikidata items.

`(items: list of Z6091, language: Z60)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z32218)

### Z33057: See also list

Makes a list of pages like a "See Also" section.

`(list of links: list of Z6091, language: Z60)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z33057)

### Z31921: statement with reference

Adds a reference to a statement fragment.

`(statement: Z89, reference: Z89)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z31921)

### Z32053: Simple cite web

Simple version of the cite web template.

`(URL: Z6, Title: Z6, Website: Z6, Access date: Z20420, Language: Z60)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z32053)

### Z29588: HTML link to Wikipedia article about Wikidata Item

`(target site language: Z60, Item: Z6091)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z29588)

### Z30192: make a link

Works with links to Wikimedia sites.

`(target: Z6, label: Z6)` -> HTML fragment | [View](https://www.wikifunctions.org/view/en/Z30192)

---

## Promising: Wikidata Query Utilities

Functions that pull data from Wikidata items — useful as building blocks.

### Z23753: label of item reference in language

> Returns the label string of a Wikidata item in the specified language.

`(QID: Z6091, language: Z60)` -> String | [View](https://www.wikifunctions.org/view/en/Z23753)

### Z24766: label text for item in given language or fallback

From an ordered list of languages, returns the label in the best match.

`(QID: Z6091, preferred language: Z60)` -> String | [View](https://www.wikifunctions.org/view/en/Z24766)

### Z29623: item (QID) is instance of these items

Returns list of items that the input is an instance (P31) of.

`(child item reference: Z6091)` -> list of Z6091 | [View](https://www.wikifunctions.org/view/en/Z29623)

### Z29620: item (QID) is subclass of these items

Returns list of items that the input is a subclass (P279) of.

`(child item reference: Z6091)` -> list of Z6091 | [View](https://www.wikifunctions.org/view/en/Z29620)

### Z29865: defining qualities of Wikidata item

`(item: Z6091)` -> list of Z6003 (statements) | [View](https://www.wikifunctions.org/view/en/Z29865)

### Z30025: get properties' IDs from Wikidata item reference

`(item: Z6091)` -> list of Z6092 (property refs) | [View](https://www.wikifunctions.org/view/en/Z30025)

### Z32569: list of higher level administrative units

`(item: Z6091)` -> list of Z6091 | [View](https://www.wikifunctions.org/view/en/Z32569)

### Z23762: selected labels and properties of Wikidata item

Select specific labels and statements from an item.

`(topic: Z6091, languages: list of Z60, properties: list of Z6092)` -> nested list | [View](https://www.wikifunctions.org/view/en/Z23762)

### Z20041: Wikidata item reference ID string

Extract the QID string from a Wikidata item reference.

`(ref: Z6091)` -> String | [View](https://www.wikifunctions.org/view/en/Z20041)

---

## Useful Types for Article Composition

| Type | Z-ID | Purpose |
|------|------|---------|
| Wikidata item reference | Z6091 | Wrapper for QIDs (e.g. Q42 → Douglas Adams) |
| Wikidata property reference | Z6092 | Wrapper for PIDs (e.g. P31 → instance of) |
| Wikidata statement | Z6003 | A single claim with value and qualifiers |
| Monolingual text | Z11 | Text with associated language code |
| HTML fragment | Z89 | Rich text for the visual editor |
| Natural language | Z60 | Language selector (e.g. English, Japanese) |
| Wikidata lexeme reference | Z6095 | Wrapper for LIDs |
| Gregorian calendar date | Z20420 | Date values |
| Integer | Z16683 | For ordinals, counts |
| Natural number | Z13518 | For quantities |

---

## How Functions Nest in Articles

```
Fragment (clipboard item):
  Z29749 or Z27868 (→ HTML fragment)          ← outermost: makes it paste-able
    └─ Z14396 (string of monolingual text)     ← optional: unwraps Z11 → string
         └─ SENTENCE FUNCTION                  ← core: generates the actual text
              ├─ Z6091 (Wikidata item ref)     ← entity arguments
              └─ Z60 (language)                ← language argument
```

Each article is a list of these fragments. To add a new kind of sentence,
just swap the SENTENCE FUNCTION in the middle.
