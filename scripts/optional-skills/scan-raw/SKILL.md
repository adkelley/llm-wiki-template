---
name: scan-raw
description: |
  Un-ingested raw-file scanner for LLM Wiki users. Trigger whenever the user
  types "/scan-raw", asks "any new files in raw?", "check raw for new
  documents", "scan raw folder", or otherwise wants to know whether anything
  has been dropped into raw/ that hasn't been ingested yet. Runs the shared
  ingest guard's audit command against raw/, lists files with no manifest
  record, asks the user which ones to import, then runs the standard Ingest
  Workflow for each approved file. Also surfaces files or folders the user
  previously marked do-not-ingest so they aren't silently re-asked about, and
  can record new skip/ignore decisions on request. Read-only until the user
  approves.
---

# /scan-raw - Detect New Raw Files

## Purpose

Users often drop new source material straight into `raw/` (Obsidian web
clipper output, a saved PDF, a pasted note) without telling the agent to
ingest it. This skill finds files in `raw/` that have never been recorded in
the ingest manifest, shows them to the user, and asks which ones — if any —
should go through the normal ingest workflow. It also respects and surfaces
prior do-not-ingest decisions, so declined files and folders (such as a
`Financials/Archive/` directory the user never wants reviewed) are not
repeatedly re-asked about on every scan.

This skill does not add new detection logic. It wraps the existing shared
utility:

```text
scripts/wiki/ingest_guard.py audit
```

which already hashes every file under `raw/` and reports `known`, `new`,
`skipped`, or `ignored_by_path` against `.llm-wiki/ingest-manifest.jsonl` and
`.llm-wiki/raw-ignore.txt`. This skill is the missing "surface it and ask"
layer on top of that utility.

## Required Local Files

None. This skill has no config or state of its own — it reuses the core
ingest guard and manifest that the standard Ingest Workflow already depends
on:

- `scripts/wiki/ingest_guard.py`
- `.llm-wiki/ingest-manifest.jsonl`
- `.llm-wiki/raw-ignore.txt` (optional, only present once a folder or pattern
  has been ignored)

If `scripts/wiki/ingest_guard.py` is missing, stop and tell the user this
skill depends on the shared ingest guard utility and cannot run without it.

Run all commands from the repository/wiki root, since the guard's default
`--raw-dir` and `--manifest` paths are relative to the current directory.

## Step 1 - Run the Audit

```bash
python3 scripts/wiki/ingest_guard.py audit
```

This prints one JSON object with `known_count`, `new_count`, `skipped_count`,
`ignored_count`, `file_count`, and a `files` array. Each entry has a `status`
of `known`, `new`, `skipped` (previously marked do-not-ingest), or
`ignored_by_path` (excluded by a pattern in `raw-ignore.txt`), plus
`source_path` and, for hashed files, `size_bytes` and hash fields. `skipped`
entries also carry `reason` and `skipped_at` when available.

If the manifest file does not exist yet, treat that as "nothing has been
recorded yet," not an error — every file in `raw/` will report as `new`. If
this is the first run in a wiki that already has ingested history, tell the
user their manifest looks empty and ask whether they want to backfill it
first:

```bash
python3 scripts/wiki/ingest_guard.py index-existing
```

Only suggest `index-existing` once, and only when `new_count` looks
suspiciously close to `file_count` for a wiki that clearly has prior wiki
pages referencing raw sources. Do not run it without the user's confirmation
— it writes manifest records for every current file in `raw/`.

## Step 2 - Filter Candidates

From the `files` array, keep entries where `status == "new"`, then drop:

- `raw/assets/*` - these are attachments (clipper images, downloaded media)
  associated with another raw file, not standalone sources to ingest. Per
  `raw/README.md`, they are not independent documents.
- any file the user has already told you in this conversation to ignore or
  treat as scratch content.

`skipped` and `ignored_by_path` entries are already-resolved decisions, not
candidates — do not include them in the approval prompt in Step 3. They are
only mentioned as a one-line count in Step 5, so the user can see their prior
decisions are still being honored without being re-asked about them.

If nothing remains after filtering, report that and stop:

```text
Scanned raw/. No new, un-ingested files found ({known_count} already
ingested, {skipped_count} marked do-not-ingest, {ignored_count} excluded by
raw-ignore.txt).
```

## Step 3 - Present the List

Show the remaining candidates with enough context for the user to decide,
grouped by rough type if it's obvious from the extension (markdown, PDF,
image, etc.):

```text
Found {N} file(s) in raw/ that haven't been ingested yet:

1. raw/2026-07-05-some-article.md (4.2 KB)
2. raw/quarterly-notes.pdf (118 KB)
3. raw/2026-07-06-voice-memo.md (1.1 KB)

Import any of these into the wiki? Reply with numbers (e.g. "1,3"), "all",
or "none". You can also say "never ask about #2" or "ignore the whole
{folder}/ folder" to stop a file or folder from appearing in future scans.
```

Do not guess at relevance or summarize contents before the user decides —
unlike the mail/notes ingest skills, this skill has no external source to
filter for topical fit. Everything in `raw/` was already placed there
deliberately by the user; the only open question is whether it's been
processed yet.

## Step 4 - Handle Declines

A candidate the user does not approve falls into one of two buckets — ask if
it's ambiguous from their reply:

- **Defer for now**: take no action. Leave the file unrecorded so it appears
  as `new` again on the next scan. This is the default when the user just
  says "none" or omits a number without further comment.
- **Never ask again**: the user is telling you this specific file, or an
  entire folder, should stop being surfaced. Record that decision so future
  scans honor it:

  ```bash
  python3 scripts/wiki/ingest_guard.py skip raw/quarterly-notes.pdf \
    --reason "{short reason from the user if given}"
  ```

  ```bash
  python3 scripts/wiki/ingest_guard.py ignore-path "Financials/Archive/"
  ```

  Use `skip` for one specific file (it follows the file's content hash, so a
  later rename or copy is still recognized). Use `ignore-path` for a folder
  or glob pattern — this also silently covers files added to that folder
  later, so it's the right tool for something like an entire archive
  directory the user never wants reviewed, not just the files sitting in it
  today.

Confirm back what was recorded, e.g. "Got it — I won't ask about
`raw/quarterly-notes.pdf` again" or "Got it — anything under
`Financials/Archive/` will be excluded from future scans."

If the user later says a previously skipped file or ignored folder should
actually be reviewed, that overrides the prior decision automatically the
next time it goes through the standard Ingest Workflow's `record` step — no
separate "unskip" command is needed.

## Step 5 - Run the Standard Ingest Workflow

For each file the user approves, follow the existing **Ingest Workflow**
already defined in this wiki's `AGENT.md` or `CLAUDE.md` (guard check, read,
discuss takeaways, update `wiki/sources/`, `wiki/index.md`, concept/entity
pages, `wiki/log.md`, then record the file with the guard). Do not duplicate
or reimplement those steps here — this skill only decides *which* files enter
that workflow and *when*.

If the guard's `check` step reports `status: "skip"` for a file the user just
approved here (they changed their mind about an earlier decline), that is
expected — proceed with the Ingest Workflow as normal. Its `record` step will
override the prior skip.

Process approved files one at a time so the user can review each ingest's
wiki changes before moving to the next, rather than batching all approvals
into one large diff.

## Step 6 - Summarize

After processing, report what happened, distinguishing deferred candidates
from ones just marked do-not-ingest in Step 4:

```text
Imported: 2 (raw/2026-07-05-some-article.md, raw/2026-07-06-voice-memo.md)
Deferred for now: 1 (raw/quarterly-notes.pdf)
Marked do-not-ingest: 1 (raw/old-draft.md)
Also skipping {skipped_count} previously-declined file(s) and
{ignored_count} file(s) under ignored folders — unchanged this scan.
```

## Failure Modes

- **`ingest_guard.py` missing or errors out**: stop, report the failure, do
  not fall back to a manual directory listing that skips manifest state.
- **Malformed manifest JSONL**: the guard itself raises on invalid JSON; stop
  and report the parse error rather than ignoring the manifest.
- **`raw/` missing**: report that there is no raw directory to scan.
- **Empty `raw/`**: report zero new files; this is not an error.

## Safety Rules

- Never modify or move files inside `raw/`. This skill only reads and
  reports.
- Never run the standard Ingest Workflow for a file without explicit
  per-file (or explicit "all") user approval.
- Never call `ingest_guard.py record` for a file the user did not approve.
- Never call `ingest_guard.py skip` or `ignore-path` without the user
  explicitly asking to stop being asked about that file or folder — these
  are persistent decisions, not a way to quietly clear the candidate list.
- Never treat `raw/assets/*` files as ingestible documents.
- Never run `index-existing` without the user's confirmation.
