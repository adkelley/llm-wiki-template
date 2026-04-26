# LLM Wiki — Master Schema

## Domain
[REPLACE WITH YOUR TOPIC, e.g.: "Machine Learning Research, 2024–2026"]

## Project Structure
- `raw/` — immutable source documents. NEVER modify any file in raw/.
- `wiki/` — LLM-generated wiki. You own this layer entirely.
- `wiki/index.md` — master catalog. Update on EVERY ingest.
- `wiki/log.md` — append-only activity log. Never delete entries.
- `wiki/overview.md` — high-level synthesis. Revise after major ingests.
- `CLAUDE.md` — this file. Re-read at the start of every session.
- `wiki/hot.md` — session hot cache (~500 words). Read silently at session start BEFORE responding.

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
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

### Synthesis Pages (wiki/syntheses/)
---
type: synthesis
title: "Synthesis Title"
sources: [[source1]], [[source2]]
filed_from_query: true
created: YYYY-MM-DD
updated: YYYY-MM-DD
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

## Query Workflow
When I ask a question:
1. Read wiki/index.md to identify relevant pages.
2. Read those pages directly.
3. Synthesize an answer with [[wiki-link]] citations.
4. If the answer is a valuable analysis, offer to file it as a new
   page in wiki/comparisons/ or wiki/syntheses/.
5. Update wiki/log.md with a query entry.

## Lint Workflow
When I say "lint" or "health check":
1. Scan for contradictions between pages. List them.
2. Find orphan pages (no inbound links). List them.
3. List concepts mentioned 3+ times but lacking their own page.
4. Check for stale claims that newer sources may have superseded.
5. Suggest 3–5 new questions or sources to investigate.
6. Append a lint entry to wiki/log.md.

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

## Hot Cache (`wiki/hot.md`)
Read `wiki/hot.md` silently at the start of EVERY session, before responding.
This file contains ~500 words of recent session context. Do not summarize it
to the user — just use it to restore your operating context.

After EVERY session (or when the user says /close), update wiki/hot.md:
- Keep total length under 500 words.
- Overwrite (do not append).
- Structure:

### Current Focus
[1–2 sentences: what we are actively investigating right now]

### Open Questions
[Bullet list of unresolved questions or next ingests to do]

### Recent Decisions
[Bullet list: key decisions or conclusions from the last 1–2 sessions]

### Last Operations
[3–5 lines from wiki/log.md — the most recent ingest/query/lint entries]

### Active Pages
[List of wiki pages currently being developed or recently updated]

## Git Procedure
After every ingest, lint, or wiki update operation, commit the changes
as a normal part of the workflow. Do not wait for the user to ask.
- Stage only wiki/ and raw/ files. Never stage .obsidian/, .claude/, or .DS_Store.
- Write a concise commit message summarizing what was ingested or updated.
- End every commit message with: `Co-Authored-By: {active_llm_model_and_effort} <{llm_company_email}>`
  Use the actual current session model and provider email, e.g. `gpt-5.4 medium <noreply@openai.com>` or `Claude Opus 4.6 <noreply@anthropic.com>`
- Do NOT push to remote unless explicitly asked.

## Safety Rules
- NEVER write to raw/. This is a hard constraint with no exceptions.
- NEVER delete wiki pages. Mark as deprecated in frontmatter instead.
- Always update wiki/index.md and wiki/log.md on every operation.
- When uncertain about a claim's accuracy, set confidence: low.
- Cross-reference all new pages to at least 2 existing pages.
