---
name: today
description:
  Morning daily briefing skill for LLM-wiki users. Trigger whenever the user types "/today",
  says "good morning", "morning briefing", "what should I focus on today", or asks for daily
  priorities. Reads the wiki's index.md, log.md, and any active task/daily-note pages to
  synthesize 3 priority focuses grounded in the wiki's current state. Always use this skill
  at the start of the user's workday — do not answer conversationally without reading the wiki first.
---

# /today — Morning Wiki Briefing

## Purpose

Give the user a grounded morning briefing by reading their LLM-wiki and surfacing exactly
**3 priority focuses** for the day — derived from the wiki's current state, not from generic advice.

The wiki (per Karpathy's LLM-wiki pattern) is a directory of LLM-maintained markdown files:
entity pages, concept pages, a running `index.md`, and an append-only `log.md`. It is the
compiled, cross-referenced synthesis of everything the user has ingested. The `/today` skill
reads this artifact — not a to-do list app — to understand what's active, what's stale, and
where attention is needed.

---

## Workflow

### Step 1 — Orient via index.md and log.md

Read these three files first. They are the entry points into the wiki.

- **hot.md**: a compressed, structured snapshot of recent context: decisions made, concepts currently under investigation, open questions, and the last few ingest/query actions.
- **index.md**: catalog of all pages with one-line summaries. Look for pages tagged or titled
  with signals like: "active", "in progress", "blocked", "pending", "draft", or dated recently.
- **log.md**: chronological record of ingests, queries, and lint passes. Parse the last 5–10
  entries to understand what has been worked on recently, what was just ingested, and what
  questions the user has been asking.

If these files don't exist or can't be found, ask the user where their wiki lives before proceeding.

---

### Step 2 — Read Relevant Wiki Pages

Based on what index.md and log.md reveal, read the specific wiki pages that seem most active
or relevant. Look for:

- Pages updated or ingested recently (per log.md timestamps)
- Entity or concept pages with open questions, contradictions flagged, or "TODO" notes
- Any page explicitly marked as a current focus, project, or active thread
- Orphan pages or stale summaries flagged during a recent lint pass

You are reading the **compiled synthesis** — the wiki's cross-references and summaries already
reflect the accumulated context. Trust them. You don't need to re-read raw sources.

---

### Step 3 — Identify 3 Priority Focuses

Reason over what you've read. A priority focus is not a single task — it is an **area of attention**
grounded in the wiki's current state. Consider:

- **Momentum**: what was just ingested or worked on that deserves follow-through today?
- **Staleness**: what pages haven't been touched in a while but are still marked active?
- **Synthesis gaps**: where does the wiki reveal a contradiction, an open question, or a
  missing cross-reference that would be valuable to resolve?
- **Blocked threads**: what is waiting on something the user controls?

Select exactly **3** focuses. Not 2, not 4. Prioritization is the skill.

---

### Step 4 — Output the Briefing

```
☀️ Good morning. Here's what your wiki says to focus on today:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① [Focus Area]
   [1–2 sentences grounded in specific wiki pages or log entries.
    Reference the page by name if relevant.]

② [Focus Area]
   [1–2 sentences grounded in specific wiki pages or log entries.]

③ [Focus Area]
   [1–2 sentences grounded in specific wiki pages or log entries.]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Also worth noting:
   • [Optional: 1–3 smaller items surfaced by the wiki — recent ingests
     to review, orphan pages to link, a question the log shows was asked
     but not yet resolved]

🔍 Wiki health: [One sentence on the state of the wiki — e.g. "Log shows
   no lint pass in 3 weeks" or "Index looks current as of yesterday's ingest"]
```

Keep the tone direct. This is a briefing, not a summary. Every sentence should connect
to something real in the wiki.

---

## Behavior Guidelines

- **Read before responding.** Never generate priorities from memory or guesswork. If the wiki
  can't be found, say so and ask where it lives.
- **Be specific.** Name pages, topics, entities from the wiki. Generic advice ("review your goals")
  is a failure mode.
- **Respect the wiki's structure.** If the user's schema distinguishes entity pages from concept
  pages from source summaries, honor those distinctions in how you describe priorities.
- **The log is a timeline.** Use it to understand recency and momentum — not just the index.
- **Don't re-derive from raw sources.** The wiki is the compiled artifact. Read the wiki, not
  the raw folder.
- **One focus per thread.** Don't collapse two unrelated active projects into one priority to
  hit the count of 3. If there are more than 3 genuinely active threads, pick the 3 that are
  most time-sensitive or highest leverage today.

---

## Fallback: Wiki Not Found

If index.md and log.md can't be located:

```
☀️ Good morning! I couldn't find your wiki to pull from.

To give you a real briefing, could you point me to your wiki directory?
I'm looking for index.md and log.md as entry points.

If you're just getting started with an LLM-wiki, I can help you set
one up — or if your notes live somewhere else, just let me know.
```

---

## Notes on the LLM-Wiki Pattern

This skill assumes the user's wiki follows Karpathy's llm-wiki pattern:

- **Raw sources** — immutable input documents (never modified)
- **Wiki** — LLM-maintained markdown pages (index.md, log.md, entity/concept pages)
- **Schema** — a CLAUDE.md or AGENTS.md describing the wiki's conventions

The `/today` skill reads the **wiki layer only**. It does not ingest sources, update pages,
or run lint. It is a read-only morning orientation, not a maintenance operation.
