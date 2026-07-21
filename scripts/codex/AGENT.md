# LLM Wiki — Master Schema

## Domain
[Enter your wiki subject here; for example, "AI and LLM Research — May 2026"]

## Wiki Philosophy
The wiki is organized into three layers.

### Knowledge
Knowledge pages describe canonical facts and observations.

Examples:

- entities
- concepts
- sources

### Work
Work pages contain durable analyses derived from the knowledge pages.

Examples:

- syntheses
- traces
- comparisons

These pages answer questions and capture reasoning, but they are not themselves
knowledge pages.

### Tasks
Task pages represent operational work required to curate or improve the wiki.

Examples:

- contradiction resolutions

Tasks represent current operational state.

`wiki/log.md` records history.

`wiki/tasks/` records current state.

Operational questions should preferentially be answered from task pages rather
than reconstructing history from `wiki/log.md`.

## Project Structure
- `raw/` — immutable source documents (may be symlinks to other locations).
  NEVER modify any file in `raw/`.
- `wiki/` — LLM-generated wiki. You own this layer entirely.
  - `entities/`
  - `concepts/`
  - `sources/`
  - `comparisons/`
  - `syntheses/`
  - `traces/`
  - `tasks/`
    - `contradiction-resolutions/`
- `wiki/index.md` — master catalog. Update on EVERY ingest.
- `wiki/log.md` — append-only activity log. Never delete entries.
- `wiki/overview.md` — high-level synthesis. Revise after major ingests.
- `AGENT.md` — this file. Re-read at the start of every session.
- `wiki/hot.md` — session hot cache (~500 words). Read silently at session
  start BEFORE responding.

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
source_type: article
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
confidence: high
---
```

The `confidence` value MUST be one of `high`, `medium`, or `low`.

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

The `source_type` value MUST be one of the values in the following table.

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

### Concept Pages (`wiki/concepts/`)

```yaml
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
confidence: high
---
```

### Entity Pages (`wiki/entities/`)

```yaml
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
```

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


### Comparison Pages (`wiki/comparisons/`)

```yaml
---
type: comparison
comparison_id: comparison:{slug}
title: "Comparing X vs Y"
status: active  # active | superseded | deprecated
subjects:
  - "[[entity1]]"
  - "[[entity2]]"
sources:
  - "[[source1]]"
  - "[[source2]]"
related:
  - "[[concept1]]"
question: "How does X compare to Y?"
origin: query  # query | ingest | migration | manual
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Comparison pages capture a structured analysis of two or more entities,
concepts, products, companies, technologies, strategies, or sources.

The goal is **not** merely to list differences. A comparison page should help
a future reader understand the important dimensions of comparison and the
evidence supporting each conclusion.

Use a comparison page when answering questions such as:

- Company A vs Company B
- GPT-5 vs Claude
- Product X vs Product Y
- Strategy A vs Strategy B
- Two competing interpretations of the same evidence

A comparison page should:

- identify the comparison subjects
- define the comparison dimensions
- summarize similarities and differences
- cite supporting source pages
- explicitly distinguish evidence from inference
- identify areas where evidence is incomplete or conflicting
- conclude with the most important takeaways

Comparisons should remain as objective as possible. Avoid making recommendations
unless the user's question explicitly requests one.

The `origin` value MUST be one of `query`, `ingest`, `migration`, or `manual`.
The `status` value MUST be one of `active`, `superseded`, or `deprecated`.

Example structure:

- Purpose
- Subjects
- Comparison dimensions
- Evidence
- Areas of agreement
- Areas of difference
- Open questions
- Conclusion

### Synthesis Pages (`wiki/syntheses/`)

```yaml
---
type: synthesis
synthesis_id: synthesis:{slug}
title: "Synthesis Title"
question: "What question does this synthesis answer?"
origin: query  # query | ingest | migration | manual
status: active  # active | superseded | deprecated
subjects:
  - "[[concept1]]"
  - "[[entity1]]"
sources:
  - "[[source1]]"
  - "[[source2]]"
related:
  - "[[comparison1]]"
  - "[[trace1]]"
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high  # high | medium | low
---
```

The `origin` value MUST be one of `query`, `ingest`, `migration`, or `manual`.
The `status` value MUST be one of `active`, `superseded`, or `deprecated`.
The `confidence` value MUST be one of `high`, `medium`, or `low`.

A synthesis page combines evidence from multiple independent sources to produce
a higher-level understanding of a topic. Unlike a source page, a synthesis is
not a summary of one document. Unlike a comparison, it is not primarily
organized around contrasting subjects. Instead, a synthesis answers a broader
question by integrating many sources into a coherent explanation.

Typical synthesis questions include:

- What is this company's AI strategy?
- What do we currently know about the market?
- How has this product evolved?
- What is the current consensus on this technology?
- What themes repeatedly emerge across the available evidence?

A synthesis should:

- organize information into logical themes
- reconcile overlapping evidence
- identify changes over time
- distinguish established facts from inference
- highlight uncertainty where evidence is incomplete
- identify contradictions that deserve their own contradiction page
- link heavily to entities, concepts, and sources

Do not duplicate source summaries. Instead, synthesize them into a higher-level
understanding.

Example structure:

- Executive summary
- Current understanding
- Supporting evidence
- Major themes
- Timeline (if applicable)
- Confidence assessment
- Open questions
- Related concepts

### Trace Pages (`wiki/traces/`)

```yaml
---
type: trace
trace_id: trace:{slug}
title: "Trace Title"
question: "What question does this trace answer?"
origin: query  # query | ingest | migration | manual
status: active  # active | superseded | deprecated
subjects:
  - "[[entity1]]"
  - "[[concept1]]"
sources:
  - "[[source1]]"
  - "[[source2]]"
related:
  - "[[synthesis1]]"
  - "[[comparison1]]"
ingest_range:
  start: YYYY-MM-DD
  end: YYYY-MM-DD
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high  # high | medium | low
---
```

The `origin` value MUST be one of `query`, `ingest`, `migration`, or `manual`.
The `status` value MUST be one of `active`, `superseded`, or `deprecated`.
The `confidence` value MUST be one of `high`, `medium`, or `low`.

A trace page reconstructs the evidence trail behind a conclusion, claim,
strategy, policy, decision, or narrative.

Unlike a synthesis, which explains **what we currently know**, a trace explains
**how we know it** by following evidence across multiple sources and, when
appropriate, over time.

Unlike a comparison, a trace is not organized around contrasting subjects.
Instead, it reconstructs the sequence of evidence that supports a particular
understanding.

Create a trace when answering questions such as:

- How did this conclusion develop?
- Where did this claim originate?
- How has this strategy evolved?
- Which sources support this belief?
- How did messaging change over time?
- What evidence led us to this understanding?

A trace should:

- clearly state the question being investigated
- identify the primary subject(s) of the trace
- organize evidence chronologically whenever possible
- distinguish direct evidence from inference
- identify where claims first appear, evolve, or disappear
- note conflicting evidence and link to a contradiction page if the conflict
  cannot be reconciled
- cite every significant conclusion back to one or more source pages
- conclude with the strongest evidence-supported narrative

A trace is investigative rather than encyclopedic.

Avoid merely summarizing documents. Instead, reconstruct the chain of evidence
that allows a future reader to understand how the conclusion was reached.

Throughout the trace, clearly distinguish:

- Evidence — observations, quotations, dates, and facts directly supported by
  one or more source pages.
- Inference — conclusions drawn by reasoning across the evidence.

Every material inference should be traceable back to one or more cited sources.

Suggested structure:

- Research Question
- Executive Summary
- Scope
- Timeline of Evidence
- Evolution of the Evidence
- Key Turning Points
- Remaining Uncertainties
- Conclusion

### Contradiction Resolution Pages

Each page represents exactly one operational contradiction.

```yaml
---
type: contradiction-resolution
contradiction_resolution_id: contradiction-resolution:{slug}
title: "Resolve ..."
status: open
priority: medium
subjects:
  - "[[entity-or-concept]]"
claims:
  - "Claim text — [[supporting-source]]"
resolution_question: >-
  What evidence is needed?
evidence:
  - "[[source]]"
log_references:
  - "[YYYY-MM-DD] query | Exact heading"
resolution: >-
  Required when status: resolved.
dismissal_reason: >-
  Required when status: dismissed.
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Rules:

- `status` MUST be one of `proposed`, `open`, `in-progress`,
  `resolution-proposed`, `resolved`, or `dismissed`.
- `priority` MUST be one of `low`, `medium`, or `high`.
- `claims` MUST be a flat list of scalar strings.
- Do not use nested YAML objects inside `claims`.
- Each claim should include one or more supporting wikilinks.
- `resolution` is required only for resolved pages.
- `dismissal_reason` is required only for dismissed pages.

#### Operational Rules

When an ingest or query uncovers contradictory information:

1. Search existing contradiction-resolution pages.
2. Update an existing page if one already represents the contradiction.
3. Otherwise create a new contradiction-resolution page.
4. Record the discovery in `wiki/log.md`.

Do not use `wiki/log.md` as the primary source of current operational state.

#### Design Principles

- Prefer concrete operational needs over speculative abstractions.
- Do not introduce new task families until a real operational backlog exists.
- Optimize schemas for both machine parsing and Obsidian usability.
- Frontmatter should remain human-readable.
- Every schema migration should have a measurable "success query".

Example:

> "What contradictions remain outstanding?"

should be answerable from
`wiki/tasks/contradiction-resolutions/`
without replaying `wiki/log.md`.
## Stable Page IDs

Every wiki page type defined above MUST have its corresponding stable ID.

Stable IDs use `{type}:{slug}`:

- `source:sample-report`
- `concept:machine-learning`
- `entity:acme-corporation`
- `comparison:acme-vs-globex`
- `synthesis:market-overview`
- `trace:machine-learning-adoption`
- `contradiction-resolution:conflicting-market-estimates`

Derive the slug from the page filename when creating a page.

Stable IDs are permanent once assigned. Do not change an ID because a page
title, filename, canonical label, or folder location changes.

Before assigning an ID, search existing wiki pages to ensure it is unique.

## Choosing the Correct Work Page

When filing persistent analysis, choose the page type that best matches the
work performed.

| If the work primarily... | Create |
|--------------------------|--------|
| summarizes one document | Source |
| defines a concept | Concept |
| describes an entity | Entity |
| integrates many sources into one understanding | Synthesis |
| compares multiple subjects | Comparison |
| reconstructs how a conclusion evolved | Trace |
| records unresolved conflicting evidence | Contradiction Resolution |

A work page should capture reasoning that would otherwise need to be repeated in
future conversations.

Prefer updating an existing work page over creating a duplicate.

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

1. Read `wiki/index.md` to identify the most relevant pages.
2. Read only the pages needed to answer the question.
3. Synthesize an answer with `[[wiki-link]]` citations.
4. Reconcile differences between sources whenever possible, distinguishing
   changes over time, differences in scope, and genuine contradictions.
5. If the work produces knowledge that should persist beyond the current
   conversation, offer to create or update the appropriate work page:
    - `wiki/syntheses/`
    - `wiki/comparisons/`
    - `wiki/traces/`
    - `wiki/tasks/contradiction-resolutions/` (only for unresolved material conflicts)
6. Update `wiki/log.md` with a query entry.

## Lint Workflow
When I say “lint” or “health check”:

1. Check the structural integrity of the wiki:
    - broken or invalid `[[wiki-links]]`
    - orphan pages (no inbound links)
    - duplicate or missing stable IDs
    - invalid or incomplete frontmatter
    - pages that violate the required schema
2. Check the wiki for curation opportunities:
    - concepts or entities frequently mentioned but lacking canonical pages
    - pages that should be linked but are not
    - sources that have not yet been connected to relevant concepts or entities
3. Check for knowledge consistency:
    - identify material conflicts between pages
    - determine whether each conflict is already explained or tracked by an
      existing contradiction page
    - report only new or unresolved contradictions
4. Check for stale knowledge:
    - identify claims that newer evidence may supersede
    - distinguish historical statements from information that should be updated
5. Recommend the highest-value maintenance actions (typically 3–5), such as:
    - creating missing entity or concept pages
    - updating syntheses or traces
    - investigating unresolved contradictions
    - ingesting additional sources
6. Append a lint entry to `wiki/log.md`.

## Log Format
Each log entry MUST start with this prefix for parsability:

```text
## [YYYY-MM-DD] {ingest|query|lint} | {title/description}
```

Example:

```text
## [2026-04-12] ingest | Mixture of Experts Efficiency Study
Source: raw/2026-04-moe-efficiency.md
Pages created: wiki/sources/summary-moe-efficiency.md
Pages updated: wiki/concepts/mixture-of-experts.md,
               wiki/concepts/scaling-laws.md
Contradictions flagged: wiki/concepts/dense-vs-sparse.md (see note)
```

## Hot Cache (`wiki/hot.md`)
Read `wiki/hot.md` silently at the start of EVERY session, before responding.
This file contains ~500 words of recent session context. Do not summarize it
to the user — just use it to restore your operating context.

After EVERY session (or when the user says `/close`), update `wiki/hot.md`:

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

- Stage only `wiki/` and `raw/` files. Never stage `.obsidian/`, `.claude/`, or
  `.DS_Store`.
- Write a concise commit message summarizing what was ingested or updated.
- End every commit message with:
  `Co-Authored-By: {active_llm_model_and_effort} <{llm_company_email}>`
  Use the actual current session model and provider email, for example,
  `gpt-5.4 medium <noreply@openai.com>` or
  `Claude Opus 4.6 <noreply@anthropic.com>`.
- Do NOT push to remote unless explicitly asked.

## Safety Rules
- NEVER write to `raw/`. This is a hard constraint with no exceptions.
- NEVER delete wiki pages. Mark as deprecated in frontmatter instead.
- Always update wiki/index.md and wiki/log.md on every operation.
- When uncertain about a claim's accuracy, set `confidence: low`.
- Cross-reference all new pages to at least 2 existing pages.
