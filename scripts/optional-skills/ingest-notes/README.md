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

Simple connectivity test:

```bash
osascript -e 'tell application "Notes" to get name of every note'
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
raw_output_dir: "raw/articles"
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

## Raw Output

Each relevant Apple Note should become one raw markdown file in
`raw/articles/` or the configured raw output directory.

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

## Notes

Apple Notes is a good fit for wiki capture because notes are usually richer
than reminders. This skill is designed to turn those notes into durable raw
inputs without requiring the user to pre-tag every note.
