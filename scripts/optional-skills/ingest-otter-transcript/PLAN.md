# Otter API Transcript Helper Script

## Summary

Build a v1 Python helper for `ingest-otter-transcript` that uses the Otter
Public API to capture one conversation transcript as immutable raw Markdown.
The helper creates source material only; wiki synthesis remains a separate,
explicit ingest step.

This started as a learning exercise around the Otter API and standard-library
Python. The implemented flow now supports both exact conversation IDs and
search-style narrowing by title, date, and participant email.

## Implemented Behavior

- Script: `otter_transcript.py`.
- API key source: `OTTER_API_KEY` environment variable only.
- Direct fetch:

```bash
python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --conversation-id CONVERSATION_ID \
  --raw-output-dir raw
```

- Search then fetch:

```bash
python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --title "meeting title text" \
  --date YYYY-MM-DD \
  --email-address person@example.com \
  --raw-output-dir raw
```

- Search uses `GET /v1/conversations` and filters locally.
- Transcript capture uses:

```text
GET /v1/conversations/{id}?include=transcript
```

- Raw filename:

```text
{raw_output_dir}/{YYYY-MM-DD-or-undated}-otter-{slugified-title}-{conversation_id}.md
```

- Raw metadata includes title, source, URL, conversation ID, created timestamp,
  participant emails, transcript format, and capture timestamp.
- Transcript content is preserved verbatim.
- Existing raw files are never overwritten.

## Notes And Follow-Ups

- V1 fetches one conversation per run.
- The list endpoint is currently first-page only; pagination via
  `meta.next_cursor` is a future enhancement.
- The script uses only the Python standard library.
- No local export parsing, batch mode, channel scan, webhook handling, or audio
  download is included in v1.
- The skill docs should treat Otter API capture as the primary workflow and
  local exported transcript files as a future or fallback path.

## Test Plan

Run syntax checks:

```bash
python3 -m py_compile scripts/optional-skills/ingest-otter-transcript/otter_transcript.py
```

Run unit tests:

```bash
python3 -m unittest discover scripts/optional-skills/ingest-otter-transcript/tests
```

Exercise success paths:

```bash
OTTER_API_KEY=... python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --conversation-id CONVERSATION_ID \
  --raw-output-dir /tmp/otter-raw-test

OTTER_API_KEY=... python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --title "title text" \
  --date YYYY-MM-DD \
  --email-address person@example.com \
  --raw-output-dir /tmp/otter-raw-test
```

Exercise failure paths:

- Missing `OTTER_API_KEY`.
- Missing locator arguments.
- No matching conversations.
- Multiple matching conversations.
- Bad or inaccessible conversation ID.
- Existing output file.
