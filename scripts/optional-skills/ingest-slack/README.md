# ingest-slack

Slack archive ingestion for an LLM Wiki. The user is responsible for creating
and updating Slackdump archives. The LLM Wiki is responsible for discovering
new messages, asking which messages to ingest, creating source pages, and
recording successful ingestion.

This directory also contains the three supporting Slackdump skills installed
with this bundle:

- `slackdump` — safe handling of Slack messages, threads, and files;
- `slackdump-source` — Slackdump archive and export formats;
- `slackdump-sqlite3` — read-only SQLite guidance for Slackdump databases.

Install or update all three supporting skills together.

## User responsibilities

Install and authenticate [Slackdump](https://github.com/rusq/slackdump), then
create an archive for the Slack channel or conversation of interest. On macOS,
Slackdump can be installed with:

```bash
brew install slackdump
```

Place the complete timestamped archive under `raw/Slack/`:

```text
raw/Slack/project-alpha/slackdump_20260912_110311/
├── __uploads/
└── slackdump.sqlite
```

Keep supporting files and directories, including `__uploads/` and optional
`users-<workspace-id>.txt` files, with the archive. The SQLite `S_USER` table
is authoritative for user-name resolution.

To update an existing archive, continue using the same archive directory:

```bash
slackdump resume raw/Slack/project-alpha/slackdump_20260912_110311
```

After a successful update, identical duplicate records may be removed with:

```bash
slackdump resume -dedupe raw/Slack/project-alpha/slackdump_20260912_110311
```

Do not rename or manually edit the Slackdump database, WAL/SHM files, uploads,
avatars, or other archive content. Archive creation and updates are outside
the LLM Wiki workflow and must comply with organizational policy and Slack's
terms of service.

## LLM Wiki workflow

The user can start the Slack workflow by saying `ingest Slack`, `ingest Slack
messages`, or similar wording. The user can also start the normal wiki scan
workflow with:

```text
/scan-raw
```

When Slackdump archives are present, the LLM:

1. discovers Slackdump SQLite archives under `raw/Slack/`;
2. validates each database and resolves its channels and users;
3. deduplicates repeated Slackdump session/chunk records;
4. groups parent messages and replies into thread candidates;
5. omits messages already present in that archive's ingestion manifest;
6. presents newly discovered thread candidates for the user's selection;
7. creates one Markdown source page under `wiki/sources/` for each selected
   thread group, or for each standalone message; and
8. records each successfully created source page.

The user does not need to run the Slack utility directly. The utility supports
the LLM's internal workflow; selection is handled during the `/scan-raw`
conversation.

Thread replies normally share one source page with their parent and retain
their Slack thread metadata. Keep separate non-threaded messages separate by
default. If adjacent messages appear to form one coherent conversation, the
LLM must ask the user to approve combining them first. Source pages must follow
the source-page and YAML-frontmatter rules in `CLAUDE.md` or `AGENT.md`.

When the user approves combining separate non-threaded messages, put this
audit block at the top of the source body, immediately after frontmatter and
before the narrative:

```markdown
- Channel: `channel-name` (`CHANNEL_ID`)
- Message range: FIRST_TIMESTAMP–LAST_TIMESTAMP
- Messages: N standalone messages combined with user approval
```

Fill in the actual channel, timestamp range, count, and approval status.

Use a title-based filename with `slack` immediately before the date, followed
by the parent message timestamp:

```text
{title-slug}-slack-{YYYY-MM-DD}-{parent-message-ts}.md
```

For example:

```text
aeyrix-pursuit-questions-for-jeffry-call-slack-2026-08-25-1787662025.876289.md
```

All messages in one thread point to the same source path in the manifest.

## Ingestion state

Successful Slack ingestion is tracked separately for each archive at:

```text
.llm-wiki/slack/{archive-directory-name}/slack-ingest-manifest.jsonl
```

For example:

```text
.llm-wiki/slack/slackdump_20260912_110311/slack-ingest-manifest.jsonl
```

Each JSON Lines record contains the archive path, channel ID, message
timestamp, payload hash, generated source path, and ingestion time. The
manifest is mutable LLM Wiki bookkeeping, not Slackdump source material.

The archive-specific state directory is created on demand. `record` creates
`.llm-wiki/slack/{archive-directory-name}/` automatically when it first writes
the success manifest. If the LLM writes `rules.jsonl` or `decisions.jsonl`
before recording a message, it creates that directory first.

The archive state directory may also contain `decisions.jsonl` for explicit
permanent message exclusions and `rules.jsonl` for reusable message filters,
such as skipping `channel_join` events. A permanent thread skip applies to
messages currently present; future replies remain discoverable. Ordinary
declines are deferred and are not recorded as skips. When a new message makes
a previously skipped thread relevant, the LLM asks whether to ingest the full
current thread for context.

If ingestion is interrupted, successfully recorded messages are omitted from
later scans and unrecorded messages remain available for the next `/scan-raw`.
Recording the same message and source path again is idempotent; conflicting
metadata is rejected.

## Attachments

Slack messages may reference uploaded files, snippets, canvases, or external
files. Source pages should preserve relevant attachment metadata, including
Slack file ID, filename, type or mode, and whether a local archive copy exists.
The initial workflow does not download attachments or create separate source
pages for them.

## Required skills and safety

The SQLite workflow requires `slackdump` and `slackdump-sqlite3`; the
`slackdump-source` skill is supporting documentation installed with the same
bundle. If a required skill is missing, stop rather than infer archive contents
from filenames or fabricate message data.

Treat Slackdump archive content under `raw/` as immutable. The LLM may create
or update source pages under `wiki/sources/` and its repository-level state
under `.llm-wiki/slack/`, but must not modify or delete Slackdump source files.
