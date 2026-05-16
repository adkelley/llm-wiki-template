---
name: ingest-otter-transcript
description: |
  Otter transcript ingest skill for LLM Wiki users. Trigger whenever the user
  types "/ingest-otter-transcript", says "ingest Otter transcript",
  "process this Otter export", "import this Otter meeting", or asks to turn an
  Otter.ai conversation into raw wiki source material. Uses the Otter Public
  API helper script with `OTTER_API_KEY` to list matching conversations or
  fetch one conversation transcript by ID or by title/date/email matching.
  Preserves the transcript as immutable raw source material, then runs the
  standard wiki ingest workflow only when the user explicitly asks to ingest it.
---

# /ingest-otter-transcript - Otter Transcript Ingest

## Purpose

Turn an Otter.ai conversation transcript into durable LLM Wiki source material.

This skill uses the Otter Public API, not web scraping or browser automation.
The safe v1 path is:

1. Confirm the user has `OTTER_API_KEY` set.
2. Identify candidate conversations with `--list` when the user is unsure.
3. Identify a single Otter conversation by ID or by title/date/email matching.
4. Fetch the conversation with transcript content included.
5. Preserve the transcript text verbatim in `raw/`.
6. Run the normal wiki ingest workflow only if the user asks to continue.

## Requirements

This skill depends on:

- Python 3.11+
- Otter Public API access
- `OTTER_API_KEY` in the environment
- network access to `https://api.otter.ai`

Use the repository virtual environment when working in this template repository:

```bash
.venv/bin/python scripts/optional-skills/ingest-otter-transcript/otter_transcript.py --help
```

## Step 1 - Identify The Conversation

If the user provides a conversation ID, use it directly:

```bash
python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --conversation-id "{CONVERSATION_ID}"
```

If the user does not know the conversation ID, ask for any useful narrowing
details:

- title text
- conversation date as `YYYY-MM-DD`
- participant email address

Then run:

```bash
python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --list \
  --title "{TITLE_TEXT}" \
  --date "{YYYY-MM-DD}" \
  --email-address "{EMAIL_ADDRESS}" \
  --limit 10
```

The helper scans the first page of `GET /v1/conversations` and filters locally.
`--list` prints matching conversations without fetching transcript content or
writing raw files. `--limit` controls how many matching conversations are
printed after filtering; it does not page through older Otter conversations.

If the user identifies the desired row, rerun with its conversation ID:

```bash
python3 scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --conversation-id "{CONVERSATION_ID}"
```

If the user skips `--list` and multiple conversations match, report the printed
candidates and ask the user which conversation ID to capture.

## Step 2 - Read Wiki Topic

Before deciding whether to ingest the created raw file into `wiki/`, read the
active wiki instructions:

1. In Codex-oriented installs, read `AGENT.md`.
2. In Claude-oriented installs, read `CLAUDE.md`.
3. If both files exist, prefer the one matching the active agent.
4. Extract the `## Domain` section and use it as the primary topic.
5. If the domain is placeholder text, inspect `wiki/index.md`,
   `wiki/overview.md`, and existing `wiki/concepts/` or `wiki/entities/` pages
   to infer the wiki topic.

Evaluate the transcript against the current wiki's actual topic, not generic
meeting value. This affects only the later wiki ingest step, not raw capture.

## Step 3 - Create The Raw Transcript

Run the helper from the wiki root. In the template repository, use:

```bash
.venv/bin/python scripts/optional-skills/ingest-otter-transcript/otter_transcript.py \
  --title "{TITLE_TEXT}" \
  --date "{YYYY-MM-DD}" \
  --email-address "{EMAIL_ADDRESS}" \
  --raw-output-dir raw
```

Any one of `--title`, `--date`, or `--email-address` may be enough if it
matches exactly one conversation. Use more filters when the first search returns
multiple candidates.

In an installed wiki, use the Python interpreter appropriate for that wiki.

The helper writes a raw Markdown file named like:

```text
raw/{YYYY-MM-DD-or-undated}-otter-{slugified-title}-{conversation_id}.md
```

It refuses to overwrite existing files.

The raw file uses this format:

```markdown
Title: {title}
Source: Otter.ai Public API
URL: {url}
Conversation ID: {conversation_id}
Created: {created_at}
Participant emails: {emails}
Transcript format: {format}
Captured: {captured_at}

{verbatim transcript text}
```

Rules:

- Preserve the transcript text verbatim after the metadata block.
- Do not correct transcription errors in `raw/`.
- Do not summarize, rewrite, redact, or reorder transcript content in `raw/`.
- If the transcript is empty after extraction, stop without writing raw.

## Step 4 - Check For Duplicate Raw Sources

Before ingesting the raw file into `wiki/`, run the standard ingest guard when
available:

```bash
python3 scripts/wiki/ingest_guard.py check raw/{filename}.md
```

If the guard reports a duplicate, stop and report the matching source. Do not
write wiki updates for duplicate content.

If `scripts/wiki/ingest_guard.py` is missing, continue only after noting that
duplicate detection is unavailable in this wiki.

## Step 5 - Report Raw Capture

After creating the raw file, report:

- created raw file path
- inferred title and date
- whether the transcript has been ingested into `wiki/`
- the next command or user request needed to continue

Example:

```text
Created: raw/2026-05-15-otter-product-review-abc123.md
Not ingested yet. To continue, ask me to ingest that raw file.
```

## Step 6 - Ingest Only On Request

If the user explicitly asks to ingest the created raw transcript, run the
standard wiki ingest workflow for that raw file:

1. Run `python3 scripts/wiki/ingest_guard.py check raw/{filename}.md` when the
   guard exists.
2. If the guard reports a duplicate, stop and report the matching source.
3. Read the raw transcript.
4. Present 3-5 key takeaways.
5. Create or update the appropriate wiki source summary, concept pages, entity
   pages, `wiki/index.md`, and `wiki/log.md`.
6. Flag contradictions or uncertain claims rather than smoothing them over.
7. Record the successful ingest with
   `python3 scripts/wiki/ingest_guard.py record raw/{filename}.md` when the
   guard exists.

Do not silently ingest into `wiki/` immediately after raw capture.

## Failure Modes

- **Missing `OTTER_API_KEY`:** ask the user to set the environment variable.
- **No locator provided:** ask for conversation ID, title, date, or participant
  email.
- **No matching conversation:** report that no matching conversations were
  found.
- **Multiple matches:** report the candidate list and ask the user which
  conversation ID to capture.
- **HTTP 401/403:** report missing, invalid, or unauthorized API access.
- **HTTP 404:** report that the conversation was not found or inaccessible.
- **HTTP 429:** report rate limiting and ask the user to retry later.
- **Empty transcript:** stop without writing raw.
- **Existing raw file:** do not overwrite; report the conflict.
- **Duplicate detected:** do not update `wiki/`; report the existing source.
- **Sensitive or private meeting content:** ask for confirmation before
  preserving it in `raw/` if the user's intent is unclear.

Do not write to `wiki/` during failure handling.

## Notes

This skill is intentionally API-first. A future helper can add pagination,
batch processing, local Otter export parsing, and richer participant metadata.
Do not add web automation or credential storage to the skill unless the user
explicitly designs and approves that scope.
