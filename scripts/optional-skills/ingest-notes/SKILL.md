---
name: ingest-notes
description: |
  Apple Notes ingest skill for LLM-wiki users. Trigger whenever the user
  types "/ingest-notes", says "ingest notes", "process Apple Notes", or
  asks to pull in recent notes. Scans Apple Notes on macOS via osascript,
  selects notes modified within a configurable lookback window, evaluates
  each note for wiki relevance, saves qualifying notes into raw/,
  and runs the standard wiki ingest workflow. Tracks Apple note IDs and
  modification dates in a manifest so unchanged notes are skipped and
  edited notes can be re-ingested later. Always read config.md and
  processed.txt before scanning.
---

# /ingest-notes — Apple Notes Ingest

## Purpose

Scan Apple Notes on macOS for recently modified notes, evaluate which notes
belong in the current wiki, and feed qualifying notes into the standard wiki
ingest workflow.

This skill is for turning capture notes into wiki source material. It works
best when the user writes notes that contain enough domain-specific context
for the agent to determine whether they belong to the current wiki.

This skill uses Apple Notes via `osascript` directly. It does not use tags,
folder routing, or a secondary adapter layer in v1. Relevance comes from
semantic reasoning against this wiki's actual domain.

---

## Configuration Files

This skill requires two files in its own directory. The exact path depends on
how the skill is installed:

- Codex repo-local install:
  - `./skills/ingest-notes/config.md` — lookback window and raw output directory
  - `./skills/ingest-notes/processed.txt` — append-only manifest of processed note IDs
- Claude Code-style install:
  - `.claude/skills/ingest-notes/config.md` — lookback window and raw output directory
  - `.claude/skills/ingest-notes/processed.txt` — append-only manifest of processed note IDs

If either is missing, run first-time setup (Step 1).

---

## Step 1 — Read Config and Manifest (or First-Time Setup)

### If config.md exists:

Read it and extract:
- `lookback_days` — number of days back to consider note modifications
- `raw_output_dir` — directory to write raw note files into
- `wiki` — optional wiki identifier for reporting and routing context

Read `processed.txt`. If it doesn't exist, treat it as empty.

### If config.md does not exist (first run):

Tell the user to create `config.md` in the skill's own directory
(`./skills/ingest-notes/` or `.claude/skills/ingest-notes/`, depending on the
installation) with at least:

```text
# ingest-notes config

lookback_days: 7
raw_output_dir: "raw/"
wiki: "your-wiki-name"
```

Create an empty `processed.txt` in that same skill directory.

Do not try to auto-configure Apple Notes access in v1. Stop after explaining
the required config.

---

## Step 2 — Scan Apple Notes

Apple Notes is a GUI automation source, so treat it as flaky until proven
available in the current execution environment.

### 2a. Preflight Notes automation

Before the full scan, run a minimal connectivity check:

```bash
osascript -e 'tell application "Notes" to count notes'
```

If this fails with errors such as:

- `Expected class name but found identifier`
- `Connection invalid`
- Automation permission prompts or denials

then do **not** continue to the full scan. Report that the skill requires:

- macOS
- Apple Notes available in a normal GUI session
- user-granted Automation permission for the terminal/agent process
- an execution context allowed to talk to GUI apps

In sandboxed agent environments, the same command may fail in the sandbox but
work when run with approved elevated permissions. If the agent has an
escalation mechanism, retry the preflight and full scan with permission instead
of treating the note corpus as empty.

Do not update `processed.txt` if preflight fails.

### 2b. Full scan

Run `osascript` to retrieve Apple Notes metadata and plaintext content.

Use this AppleScript pattern:

```bash
osascript <<'APPLESCRIPT'
set recordSep to character id 30
set fieldSep to character id 31
set outputRecords to {}

tell application "Notes"
	repeat with n in notes
		try
			set noteID to id of n
			set noteName to name of n
			try
				set noteFolder to name of container of n
			on error
				set noteFolder to "Unknown"
			end try
			set createdAt to creation date of n as text
			set modifiedAt to modification date of n as text
			set noteText to plaintext of n
			set end of outputRecords to noteID & fieldSep & noteName & fieldSep & noteFolder & fieldSep & createdAt & fieldSep & modifiedAt & fieldSep & noteText
		end try
	end repeat
end tell

set AppleScript's text item delimiters to recordSep
return outputRecords as text
APPLESCRIPT
```

**Why two try blocks?** The outer `try` guards against any per-note failure aborting the entire loop. The inner `try` specifically guards `container of n`, which throws error `-1728` ("can't get object") on Exchange-synced notes and orphaned notes that lack a parent folder. Without this guard, a single containerless note silently kills the scan. Default to `"Unknown"` for folder when the property is unavailable.

Interpret the output as:
- records separated by ASCII record separator (`character id 30`)
- fields inside each record separated by ASCII unit separator (`character id 31`)

Each record is:

```text
note_id <US> note_name <US> folder_name <US> creation_date <US> modification_date <US> plaintext
```

Immediately parse the scan into structured records keyed by `note_id`. Do not
use note titles as internal identifiers; titles are mutable, may contain curly
punctuation, and may not be unique. Use titles only for display, slugs, and
human-facing summaries.

If Apple Notes access fails, report that the skill requires:
- macOS
- Apple Notes available in a GUI session
- user-granted Automation permission for terminal/agent access to Notes

Stop without updating `processed.txt`.

---

## Step 3 — Select Candidate Notes

From the scanned note set:

1. Filter to notes whose modification date is within `lookback_days`
2. Ignore notes with empty or near-empty plaintext
3. If a note is password-protected or unreadable, skip it and report it

Load `processed.txt` and interpret it as an append-only manifest with one
entry per processed version of a note:

```text
{note_id}\t{modification_date_text}
```

Example:

```text
x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567\tThursday, April 23, 2026 at 4:14:18 PM
x-coredata://11112222-3333-4444-5555-666677778888\tThursday, April 23, 2026 at 5:01:02 PM
```

Manifest rules:
- Latest entry for a given note ID wins
- If note ID is absent: note is new and eligible
- If note ID exists and modification date matches: skip as already processed
- If note ID exists and modification date is newer/different: re-evaluate

Parsing guidance:
- Treat Apple date strings as localized display text, not as durable timestamps.
- When possible, normalize dates to ISO-8601 or epoch seconds in any temporary
  parsed representation used during the run.
- Keep the original Apple modification date text in `processed.txt` because it
  is what AppleScript returns and is useful for human debugging.
- Compare processed versions by exact note ID plus exact modification date text
  unless a normalized timestamp is also stored by a future manifest version.

If no candidate notes remain, report:

```text
No new Apple Notes found within the last {lookback_days} day(s).
Manifest: {N} processed note version(s).
```

Stop here.

---

## Step 4 — Evaluate Each Note for Wiki Relevance

For each candidate note, answer two questions.

**Q1: Is this wiki-relevant?**

Relevant if it contains any of:
- A hypothesis, observation, or claim about any topic in `wiki/concepts/`
  or `wiki/entities/`
- A design idea, product concept, or open question the user wants to track
- A reference to a person, company, product, or term already in the wiki
- Anything that clearly belongs to the current wiki's domain even without tags

Not relevant if it is:
- A shopping list, logistical note, calendar coordination, or personal admin
- A low-signal scratch note with no durable wiki value
- Too vague or too short to route confidently

**Q2: Which wiki?**

Currently: evaluate against this wiki first.

If a note clearly belongs to another wiki or could plausibly belong to more
than one wiki, ask the user before ingesting it.

Show the evaluation summary before proceeding:

```text
Evaluation results:
  ✓ {note_name} — relevant: {one-sentence reason}
  ✗ {note_name} — skipped: {reason}
  ? {note_name} — ambiguous: needs routing confirmation
```

Never silently ingest an ambiguous note into the current wiki.

---

## Step 5 — Save Notes and Run Ingest

For each note marked relevant:

### 5a. Write the raw note file

Create `{raw_output_dir}/{date}-{slug}-{short_note_id}.md` where:
- `date` is derived from the note modification date when possible
- `slug` is a filesystem-safe form of the note title
- `short_note_id` is a short stable hash or suffix derived from `note_id`

The note-ID suffix prevents collisions from duplicate titles and repeated
edited versions of the same note.

Format:

```text
Title: {note_name}
Note ID: {note_id}
Source: Apple Notes
Folder: {folder_name}
Created: {creation_date_text}
Modified: {modification_date_text}
Capture method: Apple Notes via osascript

{verbatim plaintext content}
```

Do not paraphrase or clean the note text. `raw/` is immutable.

Before writing, check whether the target path already exists. If it does, do
not overwrite it; add a deterministic numeric suffix or use a longer note-ID
hash.

### 5b. Run the standard ingest workflow

Per CLAUDE.md, the ingest workflow for `{raw_output_dir}/{filename}.md`:

1. Read the note
2. Present 3–5 key takeaways to the user
3. Create `wiki/sources/summary-{slug}.md`
4. Update `wiki/index.md`
5. Update all relevant concept and entity pages
6. Flag any contradictions with existing pages
7. Create new concept/entity pages if introduced
8. Append to `wiki/log.md`

Suggested log entry format:

```text
## [YYYY-MM-DD] ingest | {note_name} (Apple Note)
Source: {raw_output_dir}/{filename}.md
Original note ID: {note_id}
Folder: {folder_name}
Pages created: ...
Pages updated: ...
Contradictions flagged: ...
Notes: {topic summary}
```

---

## Step 6 — Update the Processed Manifest

After all notes are evaluated, append entries for every note version that was
processed in this run:

```text
{note_id}\t{modification_date_text}
```

Rules:
- One processed note version per line
- No paths
- No quotes
- Skipped notes that were evaluated should also be recorded
- If a note changes later, append a new line with the same note ID and the new
  modification date
- The latest line for a note ID is the source of truth

This keeps the manifest append-only while still allowing edited notes to be
re-ingested.

---

## Step 7 — Commit

Per CLAUDE.md git procedure:

```bash
git add raw/ wiki/
```

Do not stage `.claude/`. Do not push.

Commit message format:

```text
ingest: Apple Note(s) {slug1}, {slug2}

Co-Authored-By: {active_llm_model_and_effort} <{llm_company_email}>
```

Use the **actual LLM identity for the current session**, not a fixed placeholder.

---

## Step 8 — Report Completion

```text
Apple Notes ingest complete.

Processed: {N} note(s)
  ✓ Ingested: {list of note titles}
  ✗ Skipped:  {list of note titles with reason}
  ? Asked:    {list of ambiguous note titles}

Wiki pages touched: {count}
Manifest updated: {skill_dir}/processed.txt
Log updated: wiki/log.md
```

---

## Behavior Guidelines

- **Use Apple Notes directly.** Do not route through another backend in v1.
- **Read config before scanning.** The lookback window and output directory are
  configurable. Do not hardcode them.
- **Use plaintext, not HTML.** The note body may contain HTML markup. In v1,
  the ingest source is the note's plaintext field.
- **Preflight Apple Notes automation.** Always run the minimal `count notes`
  check before the full scan. Sandbox/GUI permission failures are common; stop
  cleanly without touching the manifest if Notes cannot be reached.
- **Use note IDs internally.** Never key processing logic off exact note titles.
  Titles can change, duplicate, and contain Unicode punctuation that breaks
  brittle string matching.
- **Manifest is append-only.** Never rewrite or deduplicate the manifest file.
  Use the most recent line for a note ID when deciding whether a note is new.
- **raw/ is immutable.** Once a note is written to `raw/`, never
  modify it in place.
- **Evaluate before ingesting.** Never ingest every recent note blindly.
- **Ambiguous relevance: ask.** Do not guess when multiple wikis are plausible.
- **Skip unreadable notes.** Password-protected or unreadable notes must be
  reported and skipped.
- **Generate collision-resistant filenames.** Include date, slug, and a short
  note-ID hash or suffix. Never overwrite an existing raw note file.
- **One commit per batch.** If multiple notes are ingested in one run, commit
  them together.

## Known Edge Cases

- Apple Notes automation may fail in sandboxed or headless contexts even when
  it works in Terminal. Retry with approved GUI/Automation permissions when
  available.
- `container of n` may fail for Exchange-synced or orphaned notes. Keep the
  inner folder `try` block and default folder to `Unknown`.
- Apple date strings are localized and may include non-breaking spaces or
  locale-specific punctuation. Normalize for in-run comparisons when possible.
- Notes with image-only content may produce near-empty plaintext and should be
  skipped as low-signal unless the user explicitly asks to handle attachments.
- Duplicate note titles are legal. The Apple note ID is the durable identity.

---

## Notes

This skill makes Apple Notes a wiki capture inbox:

**capture in Notes → /ingest-notes → raw/ → standard ingest → wiki**

The core idea is simple: Apple Notes is where many ideas first appear. This
skill turns those notes into immutable raw sources and lets the normal wiki
ingest flow do the synthesis and cross-linking.
