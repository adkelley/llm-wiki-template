# Make `ingest-apple-notes` Structurally Match `ingest-mail`

## Summary

Refactor the Apple Notes ingest skill into a helper-backed Python workflow like
`ingest-mail`. The skill should be explicit that it is for Apple Notes, use the
optional `apple-notes-parser` package instead of inline AppleScript, and keep
agent judgment focused on wiki relevance rather than brittle IO/state handling.

## Key Changes

- Rename the optional skill directory and skill identity to `ingest-apple-notes`.
- Use `scan_notes.py` as the command helper for:
  - `config`
  - `preflight`
  - `state`
  - `scan`
  - `decisions-template`
  - `export-approved`
  - `finalize`
- Use `config.toml`, `state.jsonl`, and `last_scan.txt`, matching the mail skill.
- Use `apple-notes-parser` as an optional local dependency:
  - install with `python3 -m pip install apple-notes-parser`
  - import as `apple_notes_parser`
  - fail clearly from `preflight` when missing or when macOS denies database access
- Keep `osascript` out of the primary v1 workflow. Mention it only as historical
  context or a possible fallback, not as the expected scanner.

## Interfaces And State

- `config.example.toml` should include:
  - `lookback_days = 7`
  - `raw_output_dir = "raw/"`
  - `database_path = ""` for auto-detect
  - `accounts = []` and `folders = []` as optional filters; empty means no filter
  - `max_notes = 25`
  - `wiki = "your-wiki-name"`
- `state.jsonl` is append-only. Each record stores:
  - `note_id`
  - `content_hash`
  - `modified_at`
  - `decision`
  - `evaluated_at`
- Use `note_id + content_hash` as the durable note-version identity. The hash
  includes title, plaintext, and Apple Notes tags. `modified_at` is useful
  metadata but must not be the dedupe key because Apple Notes are mutable and
  timestamp behavior can be unreliable.
- `decisions-template` defaults each candidate to `ambiguous`.
- `export-approved` writes raw files only for `decision: "yes"`.
- `finalize` appends reviewed decisions only after approved raw files and wiki
  ingest are complete.

## Workflow Behavior

- `preflight` verifies the Python dependency and parser/database access.
- `scan` returns structured JSON with candidates and deterministic exclusions.
- Candidate filtering skips already evaluated `note_id + content_hash` versions.
- Raw export writes immutable markdown files named:
  - `{YYYY-MM-DD}-note-{slug}-{short_note_id_hash}.md`
- Raw files include title, note ID, content hash, source, account, folder, tags,
  created/modified timestamps, capture method, and verbatim plaintext.
- Attachments are metadata-only or out of scope in v1.

## Test Plan

- Unit tests should cover:
  - TOML config parsing
  - state and decisions parsing
  - `content_hash` stability and mutation detection
  - dedupe filtering by `note_id + content_hash`
  - scan and decisions-template JSON output
  - raw filename generation and collision handling
  - export-approved behavior and fail-closed decisions
  - parser adapter mapping with fake Apple Notes parser objects
  - CLI exit codes for config, dependency, parser, state, decisions, and raw-write failures
- Keep live Apple Notes database access out of normal tests.
- Manual integration checks should use a local Python environment, run
  `preflight`, then `scan --include-content --limit 5`, and only proceed to
  export/finalize after user review.

## Assumptions

- This is specifically an Apple Notes skill, not a generic notes ingestion
  framework.
- `apple-notes-parser` is acceptable as an optional dependency despite relying
  on Apple Notes' local database format.
- Existing legacy files such as `config.md` and `processed.txt` may exist in
  old installs and should not be deleted automatically.
- Installed runtime state files must be preserved during skill updates.
