---
name: trace
description:
  A wiki query operation that traces how a concept evolved across an LLM-maintained personal wiki
  (in the spirit of Karpathy's LLM-Wiki pattern). Reads hot.md, index.md, and log.md to navigate
  the wiki, finds all pages mentioning the concept, maps mentions to ingest dates, reconstructs the
  intellectual arc, and files the resulting trace back as a new wiki page so the exploration
  compounds. Trigger whenever the user types `/trace [concept]`, asks how their thinking on X
  evolved, wants to see when a concept first appeared, asks "has my view on X shifted?", or says
  "trace X through my wiki/vault/notes". Also trigger for "when did I first encounter X", "show me
  my history with X", "how has X developed across my reading", or any phrasing implying longitudinal
  concept archaeology across a personal knowledge base. Always read the wiki before responding —
  never reconstruct an arc from memory or guesswork. If the wiki can't be found, say so and ask
  where it lives.
---

# /trace [concept]

A **wiki query operation**. You're not grepping a folder of notes — you're querying a living,
compounding knowledge artifact that the LLM has been building and maintaining. The cross-references
are already there. The synthesis is already partially done. Your job is to read the wiki
intelligently, map mentions to ingest dates, reconstruct the arc of how this concept evolved, and
file the result back so the trace itself becomes part of the knowledge base.

A good trace doesn't disappear into chat history. This is how explorations compound.

---

## The Mental Model

In a properly maintained LLM-Wiki:

- **Raw sources** — immutable input documents (articles, papers, transcripts). Never modified.
- **The wiki** — LLM-maintained markdown pages: entity pages, concept pages, summaries, comparisons.
- **hot.md** — a compressed snapshot of recent context: decisions made, concepts under active
  investigation, open questions, and recent actions. The fastest entry point.
- **index.md** — a catalog of all wiki pages with one-line summaries. Shows what exists and its status.
- **log.md** — append-only chronological record of every ingest, query, and lint pass. The backbone
  of the trace: it records when each source entered the wiki, which is how mentions get dated.

`/trace` is a **query** that writes back. It reads the wiki, reconstructs an arc, then files the
result as a new page. Unlike `/today`, it is not read-only — it adds to the wiki.

---

## Step 1 — Orient via hot.md, index.md, and log.md

Read these files first. They are the entry points.

```bash
cat wiki/hot.md      # compressed recent context — read this first if it exists
cat wiki/index.md    # full catalog of pages and their status
cat wiki/log.md      # chronological record of ingests, queries, lint passes
```

**From hot.md**, check whether this concept is already under active investigation:
- Is it mentioned as a current focus or open question?
- Has a prior `/trace` on this concept been noted?

**From index.md**, identify:
- Pages whose title or summary directly concerns the concept
- Pages in adjacent topic areas that likely mention it
- Whether a dedicated concept page already exists

**From log.md**, extract the full ingest timeline:
- Every source ingested, in order, with its date
- Any prior queries involving this concept
- Any lint passes that flagged this concept or related pages

Log entry format (adapt to whatever prefix convention the wiki uses):
```
## [YYYY-MM-DD] ingest | Source Title
## [YYYY-MM-DD] query  | Query text
## [YYYY-MM-DD] lint   | Notes
```

If none of these files exist, skip to the Fallback section.

---

## Step 2 — Read the Concept's Own Page, Then All Pages That Mention It

You are reading the **compiled synthesis** — the wiki's cross-references and summaries already
reflect accumulated context. Trust them. You don't need to re-read raw sources.

First, if a dedicated page exists, read it:

```bash
ls wiki/ | grep -i "concept-name"
cat wiki/concept-name.md
```

This page reflects the *current* state — where the trace ends. Then find every other page that mentions the concept:

```bash
grep -rni -l --include="*.md" "CONCEPT" wiki/
grep -rni -A 4 -B 2 --include="*.md" "CONCEPT" wiki/
```

Also search for wikilinks (`[[concept-name]]`), frontmatter tags, and synonym variants.

For each hit, note:
- The nearest section heading above the mention
- 5–8 lines of surrounding context
- Wikilinks and sources cited nearby

When reading, note the epistemic state of each passage:

| Signal in wiki text | What it means |
|--------------------|---------------|
| "According to [Source]..." | Attributed claim, not yet synthesized |
| "Across sources..." / "Consistently..." | Converging evidence, higher confidence |
| "However, [Source] argues..." | Active contradiction flagged |
| "See also [[X]]", "Related: [[Y]]" | Cross-reference already made |
| "TODO:", "Needs updating", "Unverified" | Lint-flagged gap |
| Frontmatter `status: seedling/evergreen` | Explicit maturity marker |

---

## Step 3 — Map Mentions to Ingest Dates

This is what makes `/trace` different from a search. The wiki pages cite their sources; log.md
records when those sources were ingested. Together, they let you date each mention.

For each mention found in Step 2:
1. Identify which source the relevant section draws from (look for citations or attribution)
2. Find that source's ingest date in log.md
3. Assign the mention to that point in time

If a wiki page has been updated by multiple ingests (common for entity pages), section-level
citations tell you which ingest introduced which claim.

Build a chronological timeline: `[(date, source_title, wiki_page, excerpt), ...]`

---

## Step 4 — Reconstruct the Arc

With the dated timeline in hand, analyze how the concept evolved. Look for:

**First contact** — When did this concept enter the wiki? Through what source? What was the initial framing?

**Accumulation** — How did subsequent ingests add to, nuance, or complicate the picture? Did new sources confirm, extend, or challenge the initial framing?

**Inflection points** — Moments where something clearly shifted:
- A source that contradicted previous understanding
- A synthesis that merged two previously separate treatments
- A lint pass that flagged a contradiction
- A new relationship to another concept being established

**Cross-reference density** — Concepts that kept appearing alongside this one across multiple ingests are likely genuinely related. Note which co-occurrences are persistent vs. incidental.

**Current state** — How does the most recent wiki treatment compare to the first? What's settled, what's still open?

---

## Step 5 — Write the Trace Page and Update the Wiki

File the trace back. Create `wiki/traces/trace-[concept]-[YYYY-MM-DD].md`:

```markdown
---
type: trace
concept: "[concept name]"
date: YYYY-MM-DD
wiki_pages_examined: N
ingest_range: "YYYY-MM-DD → YYYY-MM-DD"
---

# Trace: [Concept]

*Longitudinal query across the wiki. Reconstructs how understanding of [concept] evolved across ingests.*

## First Contact

**[YYYY-MM-DD] — [Source Title]** (via [[wiki-page]])
[How the concept first appeared. What framing. What question it was answering.]

## Arc

### Phase 1: [Descriptive Name] ([date range])
[What the concept meant. What sources contributed. Language used — tentative, assertive, exploratory?]
Key pages: [[page-a]], [[page-b]]

### Inflection: [What changed] ([date])
[Source] introduced a [contradiction / synthesis / refinement]. Specifically: [what shifted.]

### Phase 2: [Descriptive Name] ([date range])
[How framing evolved. New relationships established. Confidence increased or decreased?]

### Current State ([most recent date])
[How the concept stands now. What's settled, what's still open.]

## Persistent Co-occurrences
- [[concept-x]] — appeared alongside in N ingests
- [[concept-y]] — appeared alongside in N ingests

## Open Questions
- [Unresolved tension]
- [Gap flagged by lint or evident from the arc]

## Sources in Chronological Order
| Date | Source | Wiki Page | Nature of Mention |
|------|--------|-----------|-------------------|
| YYYY-MM-DD | Source Title | [[page]] | First definition |
```

Then update the wiki's bookkeeping:

**Append to log.md:**
```
## [YYYY-MM-DD] query | /trace [concept]
Pages examined: N. Ingest range: DATE → DATE. Phases: N. Filed: [[traces/trace-concept-YYYY-MM-DD]]
```

**Add to index.md** (under a "Traces" section, creating it if absent):
```
- [[traces/trace-concept-YYYY-MM-DD]] — Longitudinal trace of [concept] across N ingests, DATE–DATE
```

---

## Behavior Guidelines

**Read before responding.** Never reconstruct an arc from memory or guesswork. The wiki is the
source of truth. If it can't be found, say so.

**Be specific.** Name pages, sources, and dates from the wiki. Vague arc descriptions are not traces.

**The log is the dating mechanism.** Without log.md, mentions can't be reliably ordered. If it's
missing, note that date confidence is low and use file frontmatter or filesystem dates as fallback.

**hot.md is the fast path.** If hot.md is current, check it first — a prior trace on this concept
may already exist, or the concept may be flagged as actively under investigation.

**The trace is itself a synthesis.** The output should read like intellectual history, not a search
result list. The reader should finish understanding how they came to know what they know, which
sources were most formative, and where the understanding is still soft.

**File it back.** A trace that isn't written into the wiki is a lost exploration. Step 5 is not optional.

---

## Fallback: Wiki Not Found

If hot.md, index.md, and log.md can't be located:

```
🔍 I couldn't find your wiki to trace from.

To run a proper trace, could you point me to your wiki directory?
I'm looking for hot.md, index.md, and log.md as entry points.

If your notes live somewhere else, just let me know where —
or if you're starting fresh, I can help you set up an LLM-wiki.
```

Do not attempt to reconstruct an arc without the wiki. A trace without a wiki is just a search.
