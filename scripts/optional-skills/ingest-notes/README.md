# ingest-notes

This directory contains a skill for ingesting Apple Notes into the LLM wiki
workflow.

## Platform

This skill is intended for macOS only.

It depends on:

- the Apple Notes app
- `osascript`
- a GUI session where Notes automation is allowed

## Goal

The intended flow is:

1. Create or update notes in Apple Notes.
2. Run `/ingest-notes`.
3. Scan notes modified recently.
4. Use semantic reasoning to decide which notes belong to the current wiki.
5. Save relevant notes into `raw/transcripts/`.
6. Run the normal wiki ingest workflow.
7. Record processed note IDs and modification dates so unchanged notes are not
   handled twice.

## Prerequisites

Before running this skill, the user needs:

- macOS
- Apple Notes available and syncing normally
- `osascript` available in the terminal
- this repository checked out locally
- a note corpus that includes enough domain-specific text for the agent to
  tell whether a note belongs to the current wiki

## Notes Automation

This skill reads Apple Notes through AppleScript executed with `osascript`.

Apple Notes is a GUI automation source. Always run a minimal preflight before
the full scan.

Simple connectivity test:

```bash
osascript -e 'tell application "Notes" to count notes'
```

More detailed test:

```bash
osascript <<'APPLESCRIPT'
tell application "Notes"
	set outputLines to {}
	repeat with n in notes
		set end of outputLines to (id of n) & " | " & (modification date of n as text) & " | " & (name of n)
	end repeat
	return outputLines as string
end tell
APPLESCRIPT
```

If these commands fail, check:

- you are running in a normal macOS GUI session
- Terminal or your agent has permission to control Notes
- Notes is available on this machine
- your agent is not blocked by a sandbox from talking to GUI apps

Observed failure modes include errors such as `Connection invalid`,
`Expected class name but found identifier`, or Automation permission denials.
In agent sandboxes, the same `osascript` command may fail until it is rerun
with approved elevated permissions. Treat this as an automation access failure,
not as "no notes found." Do not update `processed.txt` if preflight fails.

## Config

The skill expects a config file that stores the lookback window and raw output
directory.

Before running the skill, set these values in `config.md`:

- `lookback_days`
- `raw_output_dir`
- `wiki`

Recommended value format:

```yaml
lookback_days: 7
raw_output_dir: "raw/transcripts"
wiki: "Your Wiki Name"
```

Notes:

- `lookback_days` controls which recently modified notes are considered
- `raw_output_dir` should be a writable raw source directory
- `wiki` is optional but useful when you maintain multiple wikis

## Candidate Selection

This skill does **not** rely on explicit note tags or special folders.

Instead, it:

1. scans notes modified within the lookback window
2. checks `processed.txt` to skip unchanged notes
3. uses semantic reasoning to decide if each note belongs to the current wiki

The Apple note ID is the durable identity. Do not key processing logic off
note titles, because titles can change, duplicate, and contain Unicode
punctuation. Titles are for display and filename slugs only.

If a note might belong to another wiki, the agent should ask before ingesting
it.

## Processed Manifest

The processed manifest is a plain text file. Each line represents one processed
version of a note:

```text
{note_id}\t{modification_date_text}
```

Example:

```text
x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567	Thursday, April 23, 2026 at 4:14:18 PM
x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567	Friday, April 24, 2026 at 9:02:11 AM
```

Recommended behavior:

- one processed note version per line
- append new lines instead of rewriting history
- the latest line for a note ID is the current processed state
- if the note changes later, it can be re-ingested
- keep the original Apple modification date text for human debugging
- normalize date strings to ISO-8601 or epoch timestamps in temporary parsing
  when possible, because Apple date strings are localized

## Raw Output

Each relevant Apple Note should become one raw markdown file in
`raw/transcripts/` or the configured raw output directory.

Recommended filename format:

```text
{YYYY-MM-DD}-{slug}-{short_note_id}.md
```

Include a short note-ID hash or suffix so duplicate titles and edited note
versions do not collide. Never overwrite an existing raw file; if a collision
still happens, add a deterministic numeric suffix or use a longer note-ID hash.

Recommended structure:

```text
Title: {note_name}
Note ID: {note_id}
Source: Apple Notes
Folder: {folder_name}
Created: {creation_date}
Modified: {modification_date}
Capture method: Apple Notes via osascript

{verbatim plaintext content}
```

The raw file is the immutable source record. The wiki ingest flow does the
synthesis afterward.

## What the User Must Do Before Running the Skill

Before the first run, the user should:

1. Confirm Apple Notes can be queried from Terminal with `osascript`.
2. Create or update `config.md`.
3. Create an empty `processed.txt` file if it does not already exist.
4. Make sure recent notes contain enough context for the agent to route them
   into the current wiki.

## Robustness Notes

- Run the `count notes` preflight before the full scan.
- If preflight fails, stop without updating `processed.txt`.
- Retry with approved elevated permissions when the failure is caused by
  sandboxed GUI automation access.
- Keep the guarded folder/container lookup in AppleScript; some Notes accounts
  throw errors when `container of n` is unavailable.
- Use plaintext only in v1 and skip image-only or near-empty notes.
- Use note IDs for dedupe and routing state; do not depend on exact title
  matching.

## Notes

Apple Notes is a good fit for wiki capture because notes are usually richer
than reminders. This skill is designed to turn those notes into durable raw
inputs without requiring the user to pre-tag every note.
