# ingest-otter-transcript

Otter transcript capture for LLM Wiki.

This optional skill uses the Otter.ai Public API to fetch a conversation
transcript and save it as immutable raw source material. It does not ingest the
transcript into `wiki/` automatically.

## Requirements

- Python 3.11+
- An Otter account with Public API access
- An Otter API key available in the environment as `OTTER_API_KEY`
- Network access to `https://api.otter.ai`

No third-party Python package is required. The helper uses the Python standard
library.

## API Key

Set the API key in the shell environment before running the helper:

```bash
export OTTER_API_KEY="..."
```

Do not store API keys in this repository, `config.toml`, raw files, or committed
skill files.

## Common Commands

Fetch a known conversation ID:

```bash
python3 otter_transcript.py \
  --conversation-id RgkONM_ydbGZSHfSzpfAd2bqvDw \
  --raw-output-dir raw
```

Find and capture a conversation by title, date, and participant email:

```bash
python3 otter_transcript.py \
  --title "Nick Divehall" \
  --date 2026-05-14 \
  --email-address nick@example.com \
  --raw-output-dir raw
```

Find conversations using a relative date range:

```bash
python3 otter_transcript.py \
  --list \
  --when "yesterday" \
  --limit 5
```

List matching conversations without writing a raw file:

```bash
python3 otter_transcript.py \
  --list \
  --title "Nick Divehall" \
  --limit 5
```

Use the repo-root virtual environment when working in this template repository:

```bash
.venv/bin/python scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --title "Nick Divehall" \
  --date 2026-05-14 \
  --email-address nick@example.com \
  --raw-output-dir /tmp/otter-raw-test
```

## How Matching Works

If `--conversation-id` is provided, the helper fetches that conversation
directly with transcript content included.

If no conversation ID is provided, the helper calls the conversations list
endpoint and filters the first page locally:

- `--title` matches case-insensitive title text.
- `--date` matches the beginning of `created_at`, normally `YYYY-MM-DD`.
- `--when` accepts `today`, `yesterday`, `last week`, or `last month`.
- `--email-address` matches owner, calendar guest, and shared email fields.

`--date` and `--when` are mutually exclusive. `--date` is for exact calendar
date matching. `--when` expands to a date range before filtering. Relative
ranges compare against the UTC date prefix in Otter's `created_at` timestamp.

Use `--list` to inspect matches without fetching transcript content or writing
raw Markdown. Use `--limit N` to limit how many matching conversations are
printed. `--limit` is applied after filtering; it does not make a broad search
safe to capture automatically.

If no conversations match, the helper stops. If multiple conversations match in
capture mode, it prints a table of candidates and stops so the user can rerun
with `--conversation-id`.

## Raw Output

The generated file is named:

```text
{raw_output_dir}/{YYYY-MM-DD-or-undated}-otter-{slugified-title}-{conversation_id}.md
```

The raw Markdown file includes:

```text
Title: {title}
Source: Otter.ai Public API
URL: {url}
Conversation ID: {conversation_id}
Created: {created_at}
Participant emails: {emails}
Transcript format: {format}
Captured: {captured_at}

{verbatim transcript content}
```

The helper refuses to overwrite an existing file. Raw transcript text should not
be edited after capture.

## Safety Rules

- Keep `OTTER_API_KEY` out of committed files.
- Do not print or paste full private transcript content while debugging.
- Preserve transcript content verbatim in raw files.
- Do not write to `wiki/` during capture.
- Run the normal wiki ingest workflow only after the user asks to ingest the
  created raw file.

## Current Limitations

- The conversations list scan reads only the first API page.
- `--limit` limits printed matches only; it does not page through older Otter
  conversations.
- Relative `--when` matching compares against the UTC date prefix returned by
  Otter, not a localized meeting timezone.
- Batch capture is not implemented.
- Local Otter export parsing is not implemented.
- The helper captures transcript text only; it does not download audio or
  attachment media.

## Development Checks

From the repository root:

```bash
python3 -m unittest discover scripts/optional-skills/ingest-otter-transcript/tests
python3 -m py_compile scripts/optional-skills/ingest-otter-transcript/otter_transcript.py
```
