# LLM Wiki — Master Schema

## Domain
[Enter your wiki subject here example - "AI LLM Research, May 2026 -"]

## Project Structure
- `raw/` — immutable source documents (may be symlinks to other locations). NEVER modify any file in raw/.
- `wiki/` — LLM-generated wiki. You own this layer entirely.
- `wiki/index.md` — master catalog. Update on EVERY ingest.
- `wiki/log.md` — append-only activity log. Never delete entries.
- `wiki/overview.md` — high-level synthesis. Revise after major ingests.
- `CLAUDE.md` — this file. Re-read at the start of every session.
- `wiki/hot.md` — session hot cache (~500 words). Read silently at session start BEFORE responding.

## Tool Dependency Resolution
Do not install or update a dependency merely because its bare command is
unavailable. Check the skill's documented non-installing resolution methods
first, and request user approval before installing anything.

## Page Conventions
Every wiki page MUST have YAML frontmatter. Use these schemas:

### Source Summary Pages (`wiki/sources/`)

Each source page represents **exactly one independently attributable source**
(publication, communication, presentation, transcript, dataset, etc.).

A source page MUST NOT summarize multiple independent sources.
If analysis combines multiple sources, create one source page for each source
and place the combined analysis in a synthesis page.

```yaml
---
type: source
source_id: source:{slug}
title: "Source Title"
slug: summary-{slug}
source_file: "[[raw/{canonical_source}.md]]"
renditions:
  - "[[raw/{original}.pdf]]"
  - "[[raw/{original}.pptx]]"
source_type: article | paper | report | presentation | communication |
             transcript | recording | book | documentation |
             dataset | webpage | note | other | unknown
attribution: "Author, organization, or complete credit line"
date_published: YYYY-MM-DD
date_ingested: YYYY-MM-DD
key_claims:
  - claim1
  - claim2
  - claim3
related:
  - "[[entity1]]"
  - "[[concept1]]"
  - "[[source1]]"
confidence: high | medium | low
---
```

#### Source identity

A source page represents one intellectual work.

Examples of one source:

- one news article
- one research paper
- one PitchBook report
- one earnings-call transcript
- one investor presentation
- one email
- one meeting transcript

Do **not** combine multiple independent documents into a single source page,
even if they were ingested together or concern the same topic.

#### `source_file`

`source_file` identifies the canonical Markdown representation consumed by the
wiki.

There is exactly **one** `source_file` per source page.
Store it as a quoted wikilink into `raw/`, for example:
`source_file: "[[raw/example.md]]"`. Do not store it as a plain path.

#### `renditions`

`renditions` lists alternate representations of the **same source**.

Examples:

- original PowerPoint
- exported PDF
- HTML capture
- DOCX version

All renditions must represent the same intellectual work.

Do **not** place unrelated documents in `renditions`.

For example, these are **different sources**, not renditions:

- PitchBook report
- earnings-call transcript
- investor presentation
- annual report

Each requires its own source page.

#### Source Types

Choose the source type that best describes the intellectual work, not its file
format.

| Type | Description |
|------|-------------|
| `article` | News article, magazine article, blog post, or other published article. |
| `paper` | Academic paper, technical paper, white paper, or research paper. |
| `report` | Structured analytical or informational report, including analyst reports, annual reports, market reports, and financial reports. |
| `presentation` | Slide deck or presentation prepared for an audience, including investor decks, conference presentations, and CIMs. |
| `communication` | Written communication such as an email, memo, letter, announcement, or press release. |
| `transcript` | Transcript of spoken communication, including meetings, interviews, earnings calls, webinars, podcasts, and presentations. |
| `recording` | Audio or video recording when the recording itself is the primary source. |
| `book` | Book or book chapter. |
| `documentation` | Product documentation, manuals, specifications, API documentation, or technical documentation. |
| `dataset` | Structured data such as spreadsheets, CSV files, benchmark datasets, or database exports. |
| `webpage` | A standalone webpage that is not more appropriately classified as an article or documentation. |
| `note` | Personal, internal, or research notes. |
| `other` | Any source that does not reasonably fit another category. |
| `unknown` | Temporary value for a legacy source that has not yet been assessed. |

Replace `unknown` after reviewing the intellectual work. Do not infer a source
type from its filename or extension alone. `other` means the source was
reviewed and does not fit another category; it does not mean unreviewed.

Classify based on the intellectual work rather than the file extension. For
example, a PDF exported from PowerPoint is still a `presentation`, and an HTML
copy of a news story is still an `article`.

Examples:

- Confidential Information Memorandum (CIM) → presentation
- PitchBook Company Profile → report
- Earnings Call Transcript → transcript
- Investor Presentation → presentation
- CEO Email → communication

#### Attribution

- `attribution` is a single, quoted scalar containing the complete credit line.
- Preserve names, organizations, ordering, punctuation, and contribution notes
  exactly as presented.
- Multiple authors remain in one scalar.
- Do not convert `attribution` into a YAML list.
- Do not infer contributors or expand abbreviated credits.

#### Related

The `related` field may contain wikilinks to:

- entity pages
- concept pages
- other source pages
- synthesis pages
- trace pages
- contradiction pages
- comparison pages

Preserve existing links and their order.

Only add relationships that are supported by the source material or explicitly
provided by the user.

### Concept Pages (wiki/concepts/)
---
type: concept
concept_id: concept:{slug}
canonical_name: "Concept Name"
aliases: []
abbreviations: []
known_variants: []
known_errors: []
sources:
  - "[[source1]]"
  - "[[source2]]"
related:
  - "[[concept2]]"
  - "[[entity1]]"
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---

### Entity Pages (wiki/entities/)
---
type: entity
entity_id: entity:{slug}
entity_type: person | company | product | org
canonical_name: "Entity Name"
aliases: []
abbreviations: []
known_variants: []
known_errors: []
sources:
  - "[[source1]]"
  - "[[source2]]"
related:
  - "[[concept1]]"
  - "[[entity2]]"
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

Concept and entity naming fields follow these rules:

- `canonical_name` is the single preferred display name and MUST be a nonempty
  scalar string. Concept and entity pages MUST NOT use `title`.
- `aliases` contains other established names.
- `abbreviations` contains acronyms, initialisms, and established shortened
  forms.
- `known_variants` contains legitimate spelling, formatting, transliteration,
  or historical variants.
- `known_errors` contains documented incorrect names and common misspellings.
- Represent an empty name list as `field: []`. Represent a populated name list
  in block form, with one nonempty scalar string per item. Do not use populated
  inline lists.
- Never invent, infer, normalize, deduplicate, or reclassify name values merely
  to populate a field. Add a value only when supported by source material or
  explicitly supplied by the user. Leave unknown categories as `[]`.
- When updating a concept or entity, preserve its stable ID, existing naming
  values, and value order unless correcting a demonstrated error. Keep exactly
  one `canonical_name` and never reintroduce `title`.

The `related` field may contain wikilinks to both concept and entity pages.
Preserve existing links and their order. Add relationships only when supported
by source material or explicitly supplied by the user.


### Comparison Pages (wiki/comparisons/)
---
type: comparison
comparison_id: comparison:{slug}
title: "Comparing X vs Y"
sources:
  - "[[source1]]"
  - "[[source2]]"
filed_from_query: true
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

### Synthesis Pages (wiki/syntheses/)
---
type: synthesis
synthesis_id: synthesis:{slug}
title: "Synthesis Title"
sources:
  - "[[source1]]"
  - "[[source2]]"
filed_from_query: true
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

### Trace Pages (wiki/traces/)
---
type: trace
trace_id: trace:{slug}
concept: "Concept Title"
sources:
  - "[[source1]]"
  - "[[source2]]"
filed_from_query: true
created: YYYY-MM-DD
updated: YYYY-MM-DD
ingest_range: YYYY-MM-DD → YYYY-MM-DD
---

## Stable Page IDs

Every wiki page type defined above MUST have its corresponding stable ID.

Stable IDs use `{type}:{slug}`:

- `source:sample-report`
- `concept:machine-learning`
- `entity:acme-corporation`
- `comparison:acme-vs-globex`
- `synthesis:market-overview`
- `trace:machine-learning-adoption`

Derive the slug from the page filename when creating a page.

Stable IDs are permanent once assigned. Do not change an ID because a page
title, filename, canonical label, or folder location changes.

Before assigning an ID, search existing wiki pages to ensure it is unique.

## Ingest Workflow
When I say "ingest [filename]" or "ingest raw/[path]":
1. Run the ingest guard before reading or summarizing the source:
   `python3 scripts/wiki/ingest_guard.py check raw/[path]`
2. If the guard reports a duplicate, stop and report the matching manifest
   record instead of ingesting the file again.
3. If the guard reports `status: "skip"`, this file was previously marked
   do-not-ingest. Stop and tell me the recorded reason (if any); only
   continue if I explicitly confirm I want to ingest it anyway.
4. If the guard reports `status: "ignored_by_path"`, this file falls under a
   folder or pattern I've excluded in `.llm-wiki/raw-ignore.txt`. Stop and
   tell me the matched pattern; only continue if I explicitly confirm.
5. Read the source file from raw/.
6. Discuss key takeaways with me (3–5 bullet points).
7. Create wiki/sources/summary-{slug}.md with full summary.
8. Update wiki/index.md — add new page with one-line summary.
9. Update ALL relevant concept and entity pages with new info.
10. If new info contradicts an existing page, flag it explicitly.
11. Create new concept/entity pages if the source introduces them.
12. Append a structured entry to wiki/log.md (see Log Format below).
13. Record the successful ingest — this also overrides any prior skip
    decision for this file:
    `python3 scripts/wiki/ingest_guard.py record raw/[path]`
14. A single ingest should touch 5–15 wiki pages.

If instead I say a file or folder should never be ingested, record that
decision rather than just skipping it silently:
- one file: `python3 scripts/wiki/ingest_guard.py skip raw/[path] --reason "..."`
- a folder or pattern: `python3 scripts/wiki/ingest_guard.py ignore-path "[folder]/"`

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
Source: raw/2026-04-moe-efficiency.md
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
