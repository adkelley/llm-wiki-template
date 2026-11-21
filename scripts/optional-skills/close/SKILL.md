---
name: close
description: 
  Evening session-close skill for LLM-wiki users. Trigger whenever the user types "/close",
  says "wrap up for the night", "end of day", "evening close", or asks to log the session before
  stopping. Reads the current conversation to extract key decisions, exports them to the appropriate
  wiki pages, and appends an entry to wiki/log.md. Always use this skill at the end of the user's
  workday — do not answer conversationally without writing to the wiki first.
---

# /close — Session Close & Wiki Export

## Purpose

Summarize the session's key decisions and persist them into the user's LLM-wiki before the
day ends. The wiki (per Karpathy's llm-wiki pattern) is a directory of LLM-maintained markdown
files with a running `index.md` and append-only `log.md`. This skill **writes** to that artifact —
extracting what was decided, routing each decision to the right page, and leaving a timestamped
log entry so tomorrow's `/today` briefing has something real to read.

---

## Workflow

### Step 1 — Orient via index.md and log.md

Before writing anything, read the wiki's entry points to understand what already exists:

```bash
cat wiki/hot.md               # Rolling session hot cache
cat wiki/log.md | tail -20    # Recent session history
cat wiki/index.md             # catalog of existing pages
```

If the wiki lives somewhere other than `wiki/`, ask the user before proceeding.

---

### Step 2 — Extract Key Decisions from the Conversation

Review the full conversation and identify **key decisions** — not a transcript, not a summary
of everything discussed, but the choices, conclusions, and commitments worth preserving.

Good candidates:
- Architecture or design choices ("we decided X over Y because...")
- New conventions or standards adopted
- Conclusions reached after deliberation
- Explicit next steps or commitments
- Reversals of prior decisions (flag these prominently)

Skip: exploratory tangents, rejected ideas, routine back-and-forth, questions that weren't resolved.

Aim for **3–8 decisions** per session. If there are genuinely none, that's fine — log the session anyway.

---

### Step 3 — Export Decisions to the Wiki

For each key decision:

1. **Find the right page** — check `index.md` for an existing page where the decision belongs.
   If one exists, append to it. If not, create a new page.

2. **Write the entry** using this structure:

   ```markdown
   ## [YYYY-MM-DD] <Short Decision Title>

   **Decision**: <what was decided, in one sentence>
   **Rationale**: <why, in 1–3 sentences>
   **Context**: [[related-page]] if relevant
   ```

3. **Flag reversals** — if a decision overturns something prior, add:
   `**Reverses**: [[page-name#prior-decision-heading]]`

4. **Update index.md** — if you created a new page, add it with a one-line summary.

---

### Step 4 — Append to wiki/log.md

Append a new entry at the **bottom** of `wiki/log.md` using this exact format
(consistent prefix makes it grep-parseable):

```markdown
## [YYYY-MM-DD] close | Evening

**Summary**: <1–2 sentences on what the session covered>

**Decisions exported**:
- [[page-name]] — Decision title
- [[page-name]] — Decision title

**Next steps** (optional):
- <anything the user flagged as coming next>
```

The `## [YYYY-MM-DD] close | Evening` prefix must be exact — it's what makes the log parseable
with `grep "^## \[" wiki/log.md | tail -5`.

---

### Step 5 — Confirm

Tell the user briefly:
- How many decisions were exported and to which pages
- That `wiki/log.md` was updated

Keep it short. This is a closing action, not a new conversation.

---

## Behavior Guidelines

- **Write before responding.** Don't summarize conversationally without actually updating the wiki.
- **Be specific.** Name the actual decisions made — generic entries like "discussed the project"
  are a failure mode.
- **Log is append-only.** Never edit previous log entries.
- **Respect the wiki's schema.** If the user's `index.md` or `CLAUDE.md` describes page conventions,
  follow them.
- **No decisions this session?** Still write the log entry. Write `(none)` under decisions exported.
  A complete log matters even for quiet sessions.

---

## Fallback: Wiki Not Found

If `wiki/` can't be located:

```
🌙 Ready to close out — but I can't find your wiki directory.

Could you point me to where your wiki lives? I'm looking for
index.md and log.md as entry points.

If you haven't set one up yet, I can initialize one now.
```

---

## Notes on the LLM-Wiki Pattern

This skill assumes the user's wiki follows Karpathy's llm-wiki pattern:

- **Raw sources** — immutable input documents (never modified)
- **Wiki** — LLM-maintained markdown pages (index.md, log.md, entity/concept pages)
- **Schema** — a CLAUDE.md or AGENTS.md describing the wiki's conventions

The `/close Evening` skill **writes** to the wiki layer. It is the complement to `/today`,
which reads it. Together they close the daily loop: morning orientation → evening consolidation.
