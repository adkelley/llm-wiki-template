# ingest-apple-notes

Apple Notes ingest for LLM Wiki.

This optional skill scans Apple Notes on macOS with the
[`apple-notes-parser`](https://pypi.org/project/apple-notes-parser/) Python
package, returns candidate notes for wiki relevance review, and records
evaluated note versions so unchanged notes are not reviewed repeatedly.

The skill is specific to Apple Notes. It is not a generic notes importer and it
does not use Apple Reminders, Apple Mail, or a cross-platform notes backend.

## Requirements

- macOS with Apple Notes available and synced locally
- Python 3.11+
- `apple-notes-parser` installed for the Python used to run this skill
- A readable Apple Notes database, usually auto-detected at:

```text
~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite
```

Install the dependency:

```bash
python3 -m pip install apple-notes-parser
python3 -c "from apple_notes_parser import AppleNotesParser; print('ok')"
```

If `preflight` reports an authorization error, grant Full Disk Access to the
terminal or app running the Python process, then retry.

## macOS Full Disk Access

Apple Notes stores its local database in a protected macOS location. If the
scanner reports `authorization denied`, grant Full Disk Access to the app that
runs Python:

1. Open **System Settings**.
2. Go to **Privacy & Security**.
3. Open **Full Disk Access**.
4. Enable the terminal or editor app that runs the command, such as Terminal,
   iTerm, Zed, VS Code, or another agent host.
5. If the app is not listed, click **+**, choose it from `/Applications`, then
   enable it.
6. Quit and reopen that app, then rerun `preflight`.

Grant access to the app that actually launches `python3`; granting access to
Apple Notes itself is not sufficient.

## Runtime Files

In a Codex install, runtime files live in:

```text
./skills/ingest-apple-notes/
```

In a Claude install, runtime files live in:

```text
.claude/skills/ingest-apple-notes/
```

User-managed runtime files:

```text
config.toml
state.jsonl
last_scan.txt
```

Do not commit real local config or scan state to the template repository.

## Setup

If you previously installed the old `ingest-notes` skill, delete that installed
skill before running `ingest-apple-notes`. This skill replaces `ingest-notes`;
keeping both installed can leave two notes-ingest skills available at the same
time, and may cause confusion by your agent.

Remove the old installed skill from whichever agent directory you use:

```bash
rm -rf ./skills/ingest-notes
rm -rf .claude/skills/ingest-notes
```

Copy the example config in the installed skill directory:

```bash
cp config.example.toml config.toml
```

Edit `config.toml`:

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

Notes:

- `database_path = ""` lets `apple-notes-parser` auto-detect the default Notes
  database.
- `accounts = []` means scan all accounts. Use values such as `"iCloud"` or
  `"On My Mac"` to restrict scanning.
- `folders = []` means scan all folders. Folder filters may match a full folder
  path or the leaf folder name.
- `include_tags = []` means no tag restriction. Add tag names to keep only notes
  with at least one matching tag.
- `exclude_tags = []` means no tag exclusion. Add tag names to skip notes with
  any matching tag. Exclusions win over inclusions.
- `raw_output_dir` should normally be `raw/`.

Tag matching is case-insensitive. Account, folder, and tag filters are applied
before scan-window and state checks. Notes removed by those config filters do
not currently appear in the scan output `excluded` list.

## Common Commands

Run preflight:

```bash
python3 scan_notes.py preflight --skill-dir .
```

Show parsed config:

```bash
python3 scan_notes.py config --skill-dir .
```

Show state:

```bash
python3 scan_notes.py state --skill-dir .
```

Scan candidate notes without note bodies:

```bash
python3 scan_notes.py scan --skill-dir . --limit 25
```

Scan candidate notes with plaintext content for review:

```bash
python3 scan_notes.py scan --skill-dir . --include-content --limit 10
```

The scan output includes a `filters` block that records the account, folder,
include-tag, and exclude-tag filters active for that scan:

```json
"filters": {
  "accounts": [],
  "exclude_tags": [],
  "folders": [],
  "include_tags": ["epiphan"]
}
```

Generate a fail-closed decisions template:

```bash
python3 scan_notes.py decisions-template --skill-dir . --limit 10
```

Export approved notes to raw files:

```bash
python3 scan_notes.py export-approved --skill-dir . --decisions /path/to/decisions.json
```

Finalize reviewed decisions:

```bash
python3 scan_notes.py finalize --skill-dir . --decisions /path/to/decisions.json
```

Decision files are JSON arrays:

```json
[
  {
    "note_id": "x-coredata://...",
    "content_hash": "abc123...",
    "modified_at": "2026-05-12T09:00:00Z",
    "decision": "yes"
  }
]
```

Use `yes` for approved notes, `no` for reviewed non-matches, `ambiguous` when
routing or sensitivity is unresolved, and `context_only` when a note only
informs another approved source.

## Candidate Selection

Apple Notes are mutable, so this skill deduplicates by note identity plus
content hash:

```text
note_id + content_hash
```

`modified_at` is retained for human debugging and file metadata, but it is not
the durable version key. The content hash includes the note title, plaintext,
and Apple Notes tags. If a note is edited or retagged, the content hash changes
and the note can be reviewed again.

The scanner uses `lookback_days` and `max_notes` to keep review batches small.
`state.jsonl` remains the durable dedupe layer.

## Raw Output

Each approved Apple Note becomes one immutable raw markdown file:

```text
{raw_output_dir}/{YYYY-MM-DD}-note-{slug}-{short_note_id_hash}.md
```

Raw files include:

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

Never overwrite an existing raw file. If a filename collision occurs, append a
deterministic numeric suffix.

## Safety Rules

- Run `preflight` before scanning.
- Never treat dependency, parser, permission, or state failures as "no notes
  found."
- Never export or finalize ambiguous decisions silently.
- Never finalize state until approved raw files and wiki updates are complete.
- Keep `state.jsonl` append-only.
- Keep raw note sources immutable after creation.
- Do not commit local `config.toml`, `state.jsonl`, or `last_scan.txt`.

## Development

Run tests from the repository root:

```bash
python3 -m unittest discover scripts/optional-skills/ingest-apple-notes/tests
python3 -m py_compile scripts/optional-skills/ingest-apple-notes/*.py
```
