---
name: cleanvibe-update-check
description: Use at the start of a session in a cleanvibe-scaffolded project, at most weekly — fetch cleanvibe's updates page and refresh this repo's .claude/skills/ to the latest shipped versions.
---

# Check cleanvibe for skill updates (weekly)

This repo's `.claude/skills/` were vendored by **cleanvibe**. cleanvibe ships new and revised skills over time — when one lands, every cleanvibe-scaffolded project should pick it up.

**The check is weekly, not per-session.** At the top of a session, look at the *last cleanvibe update check* date recorded in this repo's CLAUDE.md `## Skills` section. If it has been more than 7 days:

1. **Fetch the current skill index** — `WebFetch https://cleanvibe.emmaleonhart.com/updates.md`. This is the canonical, hand-maintained page describing every skill cleanvibe ships, keyed by the cleanvibe version that introduced or revised it.
2. **Compare against the skills currently in `.claude/skills/`.** If the page lists newer skills or revisions, update the corresponding `.claude/skills/<slug>/SKILL.md` files to match. Match the wording from `updates.md`; don't paraphrase.
3. **Update the last-check date** in CLAUDE.md's `## Skills` section. Commit with a message describing which skills were refreshed.

If the fetch fails (offline, DNS, page not yet up), leave the date alone and try next session — the check is opportunistic, not mandatory.
