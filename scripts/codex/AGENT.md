# LLM Wiki — Master Schema

## Domain
[REPLACE WITH YOUR TOPIC, e.g.: "Machine Learning Research, 2024–2026"]

---

## Skill System (Local to This Repository)

This project defines **project-scoped skills** under `./skills/`.  
These skills are ONLY available when operating within this repository.

### Skill Structure
- Each subdirectory in `./skills/` is a skill module
- Each skill MUST contain a `SKILL.md` describing:
  - purpose
  - triggers
  - tools (if any)
  - usage patterns

### Skill Loading Rules
- BEFORE answering any request, check whether a skill in `./skills/` applies
- If a relevant skill exists:
  1. Read its `SKILL.md`
  2. Follow its instructions
  3. Prefer its tools and workflows over general reasoning

- Do NOT ignore relevant skills in favor of generic responses

### Tool Usage Rules
- If a skill defines tools (e.g., CLI scripts):
  - Generate commands using those tools
  - Do NOT reimplement tool logic inline unless explicitly required
  - Prefer deterministic, reproducible commands

### Skill Composition
- Multiple skills may be used together when appropriate
- Example:
  - `obsidian-cli` + wiki ingest workflow
  - `ontology` + concept/entity page generation
  - `git-ops` + Git Procedure

### Priority
Skill-based execution takes precedence over:
- default model behavior
- ad-hoc reasoning
- generic formatting

---

## Project Structure
- `raw/` — immutable source documents. NEVER modify any file in raw/.
- `wiki/` — LLM-generated wiki. You own this layer entirely.
- `wiki/index.md` — master catalog. Update on EVERY ingest.
- `wiki/log.md` — append-only activity log. Never delete entries.
- `wiki/overview.md` — high-level synthesis. Revise after major ingests.
- `CLAUDE.md` — this file. Re-read at the start of every session.
- `wiki/hot.md` — session hot cache (~500 words). Read silently at session start BEFORE responding.

---

## Page Conventions
Every wiki page MUST have YAML frontmatter. Use these schemas:

### Source Summary Pages (wiki/sources/)
---
type: source
title: "Article/Paper Title"
slug: summary-{slug}
source_file: raw/articles/{filename}.md
author: "Author Name"
date_published: YYYY-MM-DD
date_ingested: YYYY-MM-DD
key_claims: [claim1, claim2, claim3]
related: [[concept1]], [[concept2]]
confidence: high | medium | low
---

### Concept Pages (wiki/concepts/)
---
type: concept
title: "Concept Name"
aliases: [alt-name, abbreviation]
sources: [[[source1]], [[source2]]]
related: [[concept2]], [[entity1]]
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---

### Entity Pages (wiki/entities/)
---
type: entity
entity_type: person | company | product | org
title: "Entity Name"
sources: [[source1]], [[source2]]
related: [[concept1]], [[entity2]]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

### Comparison Pages (wiki/comparisons/)
---
type: comparison
title: "Comparing X vs Y"
sources: [[source1]], [[source2]]
filed_from_query: true
date: YYYY-MM-DD
---

### Synthesis Pages (wiki/syntheses/)
---
type: synthesis
title: "Synthesis Title"
sources: [[source1]], [[source2]]
filed_from_query: true
date: YYYY-MM-DD
---

## Ingest Workflow
When I say "ingest [filename]" or "ingest raw/[path]":
1. Read the source file from raw/.
2. Discuss key takeaways with me (3–5 bullet points).
3. Create wiki/sources/summary-{slug}.md with full summary.
4. Update wiki/index.md — add new page with one-line summary.
5. Update ALL relevant concept and entity pages with new info.
6. If new info contradicts an existing page, flag it explicitly.
7. Create new concept/entity pages if the source introduces them.
8. Append a structured entry to wiki/log.md (see Log Format below).
9. A single ingest should touch 5–15 wiki pages.

---

## Query Workflow
When I ask a question:
1. Identify relevant skills in `./skills/` and load them if applicable
2. Read wiki/index.md to identify relevant pages
3. Read those pages directly
4. Synthesize an answer with [[wiki-link]] citations
5. If the answer is valuable, offer to file it as a new page
6. Update wiki/log.md with a query entry

---

## Lint Workflow
When I say "lint" or "health check":
1. Identify if any linting skill exists in `./skills/` and use it
2. Scan for contradictions between pages. List them.
3. Find orphan pages (no inbound links). List them.
4. List concepts mentioned 3+ times but lacking their own page.
5. Check for stale claims that newer sources may have superseded.
6. Suggest 3–5 new questions or sources to investigate.
7. Append a lint entry to wiki/log.md.

---

## Log Format
Each log entry MUST start with this prefix for parsability:
## [YYYY-MM-DD] {ingest|query|lint} | {title/description}

Example:
## [2026-04-12] ingest | Mixture of Experts Efficiency Study
Source: raw/articles/2026-04-moe-efficiency.md
Pages created: wiki/sources/summary-moe-efficiency.md
Pages updated: wiki/concepts/mixture-of-experts.md,
               wiki/concepts/scaling-laws.md
Contradictions flagged: wiki/concepts/dense-vs-sparse.md (see note)

---

## Hot Cache (`wiki/hot.md`)
Read `wiki/hot.md` silently at the start of EVERY session, before responding.
This file contains ~500 words of recent session context. Do not summarize it
to the user — just use it to restore your operating context.

After EVERY session (or when the user says /close), update wiki/hot.md:
- Keep total length under 500 words.
- Overwrite (do not append).

### Structure

### Current Focus
[1–2 sentences]

### Open Questions
[Bullet list]

### Recent Decisions
[Bullet list]

### Last Operations
[Recent log entries]

### Active Pages
[List of active pages]

---

## Git Procedure
After every ingest, lint, or wiki update operation, commit the changes:
- Stage only wiki/ and raw/ files
- Never stage .obsidian/, .claude/, or .DS_Store
- Write a concise commit message
- End with:
  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- Do NOT push unless explicitly asked

---

## Safety Rules
- NEVER write to raw/
- NEVER delete wiki pages (mark deprecated instead)
- ALWAYS update wiki/index.md and wiki/log.md
- Use confidence: low when uncertain
- Cross-reference all new pages to at least 2 existing pages

---

## YAML Frontmatter Rules (Obsidian Compatibility)
Obsidian's property parser is stricter than the YAML spec. Follow these rules
to avoid invalid property errors:

ALL list fields (`key_claims`, `aliases`, `sources`, `related`) MUST use
block list format with each item quoted on its own line:
  key_claims:
    - "First claim text"
    - "Second claim text"
  related:
    - "[[page-one]]"
    - "[[page-two]]"

NEVER use inline format: `related: [[page1]], [[page2]]`
NEVER use bracket format: `aliases: [item1, item2]`

Additionally, avoid these characters inside quoted YAML values:
- NO unescaped double-quote characters inside a quoted string value.
  Rephrase to avoid them.
- NO `→` arrow characters. Write "to" instead.
- NO `~` tilde. Write "approx" instead.
