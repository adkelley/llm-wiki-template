---
name: ingest-apple-notes
description: |
  Apple Notes ingest skill for LLM Wiki users. Trigger whenever the user
  types "/ingest-apple-notes", says "ingest Apple Notes", "process Apple
  Notes", "scan Apple Notes", or asks to pull recent Apple Notes into the
  wiki. Uses the local apple-notes-parser Python package, not inline
  AppleScript, to scan Apple Notes on macOS. Reads config and state before
  scanning, evaluates new note versions against the wiki topic, asks for
  approval, exports approved notes into raw/, and finalizes reviewed
  decisions only after wiki ingest completes.
---

# /ingest-apple-notes - Apple Notes Ingest

## Purpose

Scan Apple Notes on macOS, find note versions that may belong in the current
wiki, ask for approval, and preserve approved notes as immutable raw sources for
the normal wiki ingest workflow.

This skill is specific to Apple Notes. It is not a generic notes importer and
does not scan Apple Reminders, Apple Mail, Obsidian notes, or arbitrary
filesystem notes.

Use `apple-notes-parser` only. Do not use inline `osascript` for the primary v1
workflow.

## Required Local Files

The installed skill directory is usually one of:

- Codex: `./skills/ingest-apple-notes/`
- Claude: `.claude/skills/ingest-apple-notes/`

Use whichever directory contains the currently loaded `ingest-apple-notes`
skill. Read and write state only inside that installed skill directory.

Required user-managed files:

- `config.toml` - scan window, raw output directory, database path, optional
  account/folder/tag filters, and limits.
- `state.jsonl` - append-only records for evaluated note versions.
- `last_scan.txt` - UTC ISO-8601 timestamp for the last successful finalize.

Required helper files:

- `scan_notes.py` - orchestrates preflight, scanning, decisions templates,
  approved raw export, and finalize.
- Sibling Python modules such as `config.py`, `state.py`, `notes_client.py`,
  `raw_export.py`, `models.py`, and `errors.py`.

If helper files are missing, stop and ask the user to reinstall or update the
skill. Do not recreate the Python logic inline in the agent response.

## Configuration

If `config.toml` is missing, stop and ask the user to create it in the installed
skill directory. The template includes `config.example.toml`; copy that file to
`config.toml` and edit it:

```toml
lookback_days = 7
raw_output_dir = "raw/"
database_path = ""
accounts = []
folders = []
include_tags = []
exclude_tags = []
max_notes = 25
wiki = "your-wiki-name"
```

Rules:

- `database_path = ""` lets `apple-notes-parser` auto-detect the default Apple
  Notes database.
- `accounts = []` scans all accounts. Use explicit values such as `"iCloud"` or
  `"On My Mac"` to restrict scope.
- `folders = []` scans all folders. Folder filters may match a full path or leaf
  folder name.
- `include_tags = []` applies no tag restriction. Explicit values keep notes
  with at least one matching tag.
- `exclude_tags = []` applies no tag exclusion. Explicit values skip notes with
  any matching tag. Exclusions win over inclusions.
- `raw_output_dir` should normally be `raw/`.

Tag matching is case-insensitive. Config filters for accounts, folders, and
tags are applied before scan-window and state checks. Notes removed by config
filters do not currently appear in the scan output `excluded` list.

## Dependency And Permissions

Use the repository virtual environment when running this skill. In command
examples, `{python}` means the repo-root `.venv/bin/python`, not bare `python`
or `python3`.

The user must install `apple-notes-parser` for that same Python interpreter:

```bash
.venv/bin/python -m pip install apple-notes-parser
.venv/bin/python -c "from apple_notes_parser import AppleNotesParser; print('ok')"
```

If `.venv/bin/python` is missing, stop and ask the user to create the repo
virtual environment before running this skill. Do not substitute a global
Python, because it may not have the same installed packages or macOS privacy
permissions.

If Apple Notes database access fails with an authorization error, report that
macOS may require Full Disk Access for the terminal or app running Python. Do
not treat permission failure as "no notes found."

To grant access, tell the user to open **System Settings** → **Privacy &
Security** → **Full Disk Access**, enable the terminal/editor/agent host that
runs `{python}`, quit and reopen that app, then retry `preflight`. The app that
launches Python needs access; granting access to Apple Notes itself is not
enough.

## Step 1 - Read Wiki Topic

Read the active wiki instructions before scanning:

1. In Codex-oriented installs, read `AGENT.md`.
2. In Claude-oriented installs, read `CLAUDE.md`.
3. If both files exist, prefer the one matching the active agent.
4. Extract the `## Domain` section and use it as the primary topic.
5. If the domain is still placeholder text, inspect `wiki/index.md`,
   `wiki/overview.md`, and existing `wiki/concepts/` or `wiki/entities/` pages
   to infer the wiki topic.

Evaluate notes against this wiki's actual topic and existing pages, not generic
interests.

## Step 2 - Read Config And State

Before scanning, read:

- `config.toml`
- `state.jsonl` if present
- `last_scan.txt` if present

Treat `state.jsonl` as append-only. The durable note-version key is:

```text
note_id + content_hash
```

Expected state record shape:

```json
{"note_id":"x-coredata://...","content_hash":"abc123...","modified_at":"2026-05-12T09:00:00Z","decision":"no","evaluated_at":"2026-05-12T17:42:56Z"}
```

Apple Notes are mutable. Do not dedupe by title or modification date alone.
Titles can change and duplicate; modification timestamps are metadata, not the
version identity. The content hash includes title, plaintext, and Apple Notes
tags so retagged notes can be reviewed again.

If `state.jsonl` is malformed, stop and report the problem rather than skipping
state.

## Step 3 - Preflight Apple Notes

Run:

```bash
{python} {skill_dir}/scan_notes.py preflight --skill-dir {skill_dir}
```

Preflight should verify:

- `apple_notes_parser` can be imported
- config can be loaded
- the Apple Notes database path is auto-detectable or explicitly configured
- database access is permitted by macOS

If preflight fails, stop. Do not write raw files, update wiki pages, append
`state.jsonl`, or update `last_scan.txt`.

## Current Command Sequence

For normal review, use helper commands in this order:

```bash
{python} {skill_dir}/scan_notes.py preflight --skill-dir {skill_dir}
{python} {skill_dir}/scan_notes.py scan --skill-dir {skill_dir} --include-content --limit 10
{python} {skill_dir}/scan_notes.py decisions-template --skill-dir {skill_dir} --limit 10
{python} {skill_dir}/scan_notes.py export-approved --skill-dir {skill_dir} --decisions {path_to_decisions_json}
{python} {skill_dir}/scan_notes.py finalize --skill-dir {skill_dir} --decisions {path_to_decisions_json}
```

Only run `export-approved` after the user approves the relevant `yes` rows.
Only run `finalize` after approved raw files and wiki updates are complete.

## Step 4 - Scan Candidates

Run:

```bash
{python} {skill_dir}/scan_notes.py scan --skill-dir {skill_dir} --include-content --limit 10
```

The scanner should return structured JSON containing:

- `ok`
- `candidate_count`
- `candidates`, each containing a `note`
- `excluded_count`
- `excluded`, each containing a deterministic skip reason
- `scan_window_days`
- `filters`, echoing the account, folder, include-tag, and exclude-tag filters
  active for the scan
- `last_scan`

The scanner computes a content hash from the note title, plaintext, and Apple
Notes tags. If the same note ID appears with a new content hash, review it
again.

If no candidates remain, report:

```text
No new Apple Notes found within the configured scan scope.
```

## Step 5 - Evaluate Relevance

For each candidate note, decide:

**Relevant (`yes`)** if it contains durable wiki value, such as:

- a hypothesis, observation, claim, source, link, quote, or reference related to
  the wiki topic
- a design idea, product concept, research lead, or open question worth tracking
- a person, organization, product, or concept already tracked by the wiki
- substantive notes that could become a source summary, concept update, entity
  update, comparison, or synthesis

**Not relevant (`no`)** if it is:

- routine logistics, personal admin, shopping lists, or calendar coordination
- too short, vague, or attachment-dependent to evaluate
- unrelated sensitive personal content

**Ambiguous (`ambiguous`)** if:

- it may belong to another wiki
- relevance depends on user intent
- it contains sensitive material and the durable value is unclear

Never silently ingest an ambiguous note.

## Step 6 - Present Review

Before writing anything, show a compact review:

```text
Apple Notes scan complete.
Last scan: {last_scan or "none"}
Scan window: last {scan_window_days} day(s)
Candidates evaluated: {N}
Mechanically excluded: {M}

[yes] {title} - {one-sentence reason}
[no]  {title} - {one-sentence reason}
[?]   {title} - needs user routing/approval: {reason}

Excluded:
- {title or note_id} - {reason}
```

Then ask for approval before export.

Generate a fail-closed decisions template:

```bash
{python} {skill_dir}/scan_notes.py decisions-template --skill-dir {skill_dir} --limit 10
```

Edit decisions so approved notes are `yes`, clear non-matches are `no`, and
unresolved items remain `ambiguous` or `context_only`.

## Step 7 - Save Approved Raw Sources

After approval, write raw files through the helper:

```bash
{python} {skill_dir}/scan_notes.py export-approved --skill-dir {skill_dir} --decisions {path_to_decisions_json}
```

Only decisions marked `yes` are exported. Each approved Apple Note becomes one
raw markdown file:

```text
{raw_output_dir}/{YYYY-MM-DD}-note-{slug}-{short_note_id_hash}.md
```

Raw file format:

```text
Title: {title}
Note ID: {note_id}
Content hash: {content_hash}
Source: Apple Notes
Account: {account}
Folder: {folder}
Tags: {tags}
Created: {created_at}
Modified: {modified_at}
Capture method: apple-notes-parser

{verbatim plaintext content}
```

Do not paraphrase or clean the note body. Do not overwrite an existing raw file.

If raw export fails, stop before wiki ingest and before finalizing state.

## Step 8 - Run Standard Wiki Ingest

After raw files are written, run the repository's standard ingest workflow for
each approved raw Apple Note source:

1. Run the ingest guard when available.
2. Read the raw note source.
3. Present 3-5 key takeaways.
4. Create or update the relevant `wiki/sources/summary-{slug}.md` page.
5. Update `wiki/index.md`.
6. Update relevant concept and entity pages.
7. Flag contradictions.
8. Append a structured entry to `wiki/log.md`.
9. Record successful ingest in the ingest guard when available.

Suggested log entry:

```text
## [YYYY-MM-DD] ingest | {title} (Apple Note)
Source: raw/{filename}.md
Original note ID: {note_id}
Content hash: {content_hash}
Folder: {folder}
Pages created: ...
Pages updated: ...
Contradictions flagged: ...
Notes: {topic summary}
```

## Step 9 - Update State

Only after approved raw files and wiki updates complete, append state records:

```bash
{python} {skill_dir}/scan_notes.py finalize --skill-dir {skill_dir} --decisions {path_to_decisions_json}
```

The finalize step should:

- append `yes`, `no`, `ambiguous`, and `context_only` decisions supplied in the
  decisions JSON file
- write the current UTC timestamp to `last_scan.txt`
- fail closed if state cannot be appended

Do not stage or commit installed skill state files unless explicitly asked.

## Step 10 - Commit Wiki Changes

If raw or wiki files changed, follow the local repository's git procedure. Stage
only allowed source/wiki files. Do not stage skill state, local config,
`.claude/`, `.codex/`, or downloaded attachments.

## Safety Rules

- Never treat dependency, parser, permission, or state failures as an empty
  Notes corpus.
- Never export or finalize ambiguous notes silently.
- Never finalize before approved raw files and wiki updates complete.
- Never key dedupe on note title or modification date alone.
- Keep `state.jsonl` append-only.
- Keep raw Apple Note sources immutable after creation.
- Do not commit local `config.toml`, `state.jsonl`, or `last_scan.txt`.
