---
name: ingest-slack
description: |
  Slack archive ingestion skill for LLM Wiki users. Trigger whenever the user
  says "ingest Slack", "ingest Slack messages", asks to process a Slackdump
  archive, or requests Slack messages be added to the wiki. Also use during
  /scan-raw when Slackdump SQLite archives are present under raw/Slack/.
  The user creates and updates Slackdump archives; the LLM discovers new
  messages, presents them for selection, creates one wiki source page per
  selected thread or standalone message, and records successful ingestion.
---

# /ingest-slack - Slack Message Ingest

## Purpose

Turn messages from Slackdump SQLite archives into durable LLM Wiki source
pages. Slackdump is responsible for creating and updating the archive. This
skill is responsible for the wiki-side discovery and ingestion workflow.

The user-facing entry points are natural-language requests such as:

- `ingest Slack`
- `ingest Slack messages`
- `process the new Slack messages`
- `ingest the Slack archive`

The general `/scan-raw` workflow also invokes this skill when it finds
Slackdump archives under `raw/Slack/`.

## Requirements

The Slackdump support bundle must be installed:

- `slackdump`
- `slackdump-source`
- `slackdump-sqlite3`

Use the repository's installed skill copies and the helper at:

```text
scripts/optional-skills/ingest-slack/slack_ingest.py
```

If the required Slackdump skills are unavailable, stop and report the missing
dependencies. Do not infer archive contents from filenames or fabricate Slack
messages.

## User responsibilities

The user creates and updates Slackdump archives and places the complete archive
under `raw/Slack/`, for example:

```text
raw/Slack/project-alpha/slackdump_20260912_110311/
├── __uploads/
└── slackdump.sqlite
```

The user may update an existing archive with Slackdump's normal resume workflow:

```bash
slackdump resume raw/Slack/project-alpha/slackdump_20260912_110311
```

Do not rename, edit, delete, or deduplicate archive files from the wiki
workflow. Slackdump archive contents—including SQLite, WAL/SHM files, uploads,
and avatars—are immutable source material.

The helper opens archives read-only. For a WAL-mode archive whose `-wal` sidecar
is absent or empty, it may use SQLite's immutable read-only mode so SQLite does
not try to create `-shm` files under `raw/`. If a non-empty `-wal` sidecar is
present and the normal read-only open fails, stop and ask the user to close
Slackdump or checkpoint the archive; do not ignore pending WAL changes.

## Step 1 - Discover Slack archives

Run the helper internally from the repository root:

```bash
python3 scripts/optional-skills/ingest-slack/slack_ingest.py inspect
```

The helper discovers `slackdump.sqlite` files recursively under `raw/Slack/`
and validates the required Slackdump schema. If the user refers to one
specific archive, pass its database with `--database`.

Do not ask the user to run the helper. The LLM owns this workflow.

## Step 2 - Find newly ingestible messages

Run the helper's thread-discovery operation internally for each relevant
archive. It:

1. loads canonical messages from the SQLite archive;
2. deduplicates repeated Slackdump session and chunk records;
3. resolves channel and user names from the database;
4. groups parent messages and replies into thread candidates; and
5. omits message identities already recorded for that archive.

Present the resulting thread candidates to the user in a readable form and ask
which candidates to ingest. Accept selections such as individual candidates,
several candidates, all candidates, or none. A selection is only a conversational
handoff; it is not successful ingestion.

If no candidates remain, report that the archive has no new Slack messages to
ingest. Do not create or modify a manifest in that case.

## Step 3 - Read wiki instructions

Before creating source pages, read the active agent instructions:

1. In a Codex installation, read `AGENT.md`.
2. In a Claude installation, read `CLAUDE.md`.
3. If both exist, prefer the instructions for the active agent.

Follow the repository's source-page schema, YAML frontmatter, naming, linking,
index, and log requirements. Each Slack thread group normally gets one source
page containing the parent and replies. Standalone messages remain separate
unless adjacent messages clearly form one coherent conversation and the user
has explicitly approved combining them.

## Step 4 - Create source pages

For every selected thread group, create one Markdown page under `wiki/sources/`.
For a standalone message, create one page for that message.
Name the page `{title-slug}-slack-{YYYY-MM-DD}-{parent-message-ts}.md`.
All messages in one thread group must use the same source path.
Include enough provenance to identify the original Slack message, including:

- archive path;
- channel name and channel ID;
- Slack message timestamp;
- author name and user ID;
- thread timestamp, when applicable;
- message text with Slack user mentions resolved when possible; and
- relevant attachment metadata.

Include the parent and replies together when the selected item is a Slack
thread. Keep separate non-threaded messages separate by default. If several
appear to form one coherent conversation, ask the user to approve combining
them before creating one source page. Do not combine unrelated Slack messages
into one page. Do not mark any message in a group ingested until the shared
source page has been created successfully.

For an approved combination of separate non-threaded messages, place this
audit block at the very top of the Markdown body, immediately after YAML
frontmatter and before the narrative:

```markdown
- Channel: `channel-name` (`CHANNEL_ID`)
- Message range: FIRST_TIMESTAMP–LAST_TIMESTAMP
- Messages: N standalone messages combined with user approval
```

Use the actual channel, first and last message timestamps, count, and approval
status. This makes the grouping decision visible and auditable.

## Step 5 - Record successful pages

After each source page is successfully created, record every message in the
thread group internally. All messages in one group may point to the same source
path:

```bash
python3 scripts/optional-skills/ingest-slack/slack_ingest.py record \
  --database raw/Slack/project-alpha/slackdump_20260912_110311/slackdump.sqlite \
  --channel-id C0BR0JL2ML2 \
  --message-ts MESSAGE_TIMESTAMP \
  --source-path wiki/sources/slack-C0BR0JL2ML2-MESSAGE_TIMESTAMP.md
```

Call `record` only after the source file exists. It validates the source path,
channel, message timestamp, and duplicate metadata. Repeating an identical
recording is idempotent. If page creation or recording fails, report the
failure and leave that message available for a later scan.

## Ingestion state

The successful-ingestion manifest is maintained separately for each archive:

```text
.llm-wiki/slack/{archive-directory-name}/slack-ingest-manifest.jsonl
```

For example:

```text
.llm-wiki/slack/slackdump_20260912_110311/slack-ingest-manifest.jsonl
```

The manifest is mutable LLM Wiki bookkeeping outside `raw/`. It records the
archive path, channel ID, message timestamp, payload hash, source path, and
ingestion time. The same archive directory may also contain `decisions.jsonl`
for explicit permanent message exclusions and `rules.jsonl` for reusable
message filters such as `channel_join`. A permanent thread skip is expanded to
messages currently in that thread; future replies remain discoverable.

The per-archive state directory does not need to exist before the first
ingestion. The `record` command creates it automatically. If the LLM needs to
write `rules.jsonl` or `decisions.jsonl` first, create
`.llm-wiki/slack/{archive-directory-name}/` before writing those files.

Do not create a temporary selection manifest for this MVP. Ordinary declines
mean “defer for now”; only explicit requests such as “don't show this again”
create exclusions. If a new reply appears in a previously skipped thread, ask
whether to ingest the full current thread for context.

## Attachments

Slackdump archives may include uploaded files. Preserve relevant attachment
metadata in the message source page, including file ID, filename, type or mode,
and whether a local archive copy is available. Do not download or alter
attachments as part of this skill unless the user explicitly requests a
separately scoped operation.

## Completion report

After processing the selection, report:

- how many messages were selected;
- how many source pages were created;
- how many messages were recorded successfully; and
- any failures or messages left for a later scan.

If all selected messages were processed, a later scan should omit them. If the
archive has no remaining unrecorded messages, report that clearly.
