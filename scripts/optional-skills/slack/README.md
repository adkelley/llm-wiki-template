# Slack skills

This directory contains three related skills for working with Slack data
archived by [Slackdump](https://github.com/rusq/slackdump):

- `slackdump` — explains how to inspect Slackdump archives and safely work with
  Slack messages, threads, and files.
- `slackdump-source` — documents Slackdump archive, export, dump, and chunk
  formats.
- `slackdump-sqlite3` — provides read-only SQLite guidance for Slackdump
  databases when the Slackdump MCP and SQLite MCP are unavailable.

The skills are installed as one bundle. If you install or update Slack support,
all three skills should be installed or updated together.

## Scope

The first version of the LLM Wiki Slack workflow uses Slackdump's SQLite archive
format.

The workflow is:

1. Install Slackdump.
2. Authenticate Slackdump with the Slack workspace.
3. Download or update an archive for the channel or conversation of interest.
4. Place the archive under `raw/Slack/`.
5. Run `/scan-raw`.
6. Select which newly discovered Slack threads should be ingested.
7. The selected messages are written as Markdown source files under
   `wiki/sources/`.

Archive creation and updating are performed outside the LLM Wiki. They may be
done manually or scheduled with `cron`; the wiki only detects and processes
changes that are already present in `raw/Slack/`.

## Install and authenticate Slackdump

Follow Slackdump's
[Installation and Quickstart](https://github.com/rusq/slackdump/tree/master#installation-and-quickstart)
instructions for the current installation and authentication procedure.

On macOS, Slackdump can be installed with Homebrew:

```bash
brew install slackdump
```

After installation, run Slackdump's setup or quickstart flow and authenticate
it with the workspace you want to archive. Slackdump's authentication and
workspace configuration are managed by Slackdump, not by this repository.

Slackdump may access Slack data in ways that trigger workspace security alerts.
Make sure your use complies with your organization's policies and Slack's terms
of service.

## Create the archive

Use Slackdump to archive the particular channel or conversation you want to
make available to the wiki. Consult Slackdump's current quickstart and command
help for the exact command and options.

Slackdump creates a timestamped archive directory containing a file named
`slackdump.sqlite`. Place that entire archive directory under `raw/Slack/`.
For example:

```text
raw/Slack/project-alpha/
└── slackdump_20260912_110311/
    ├── __uploads/
    └── slackdump.sqlite
```

A Slackdump archive may also contain supporting directories such as
`__uploads/` for uploaded files or directories containing avatars. Keep those
files with the archive when they are available.

Slackdump may also create companion files such as
`users-<workspace-id>.txt`. These files are optional for this workflow because
the SQLite archive contains user metadata in its `S_USER` table. The ingestion
process uses the database as the authoritative source and falls back to the
Slack user ID if a matching user record is unavailable.

The repository treats `raw/` as source input. Do not edit the SQLite database
from the wiki workflow.

## Update an existing archive

Slackdump archives are designed to be updated incrementally.

The timestamp in a Slackdump archive directory identifies when the archive was
created. Keep using that same directory when updating the archive; do not
create a new archive for each update.

For example, a typical project archive might look like:

```text
raw/Slack/project-alpha/
└── slackdump_20260912_110311/
    ├── __uploads/
    └── slackdump.sqlite
```

Update the existing archive with:

```bash
slackdump resume raw/Slack/project-alpha/slackdump_20260912_110311
```

The argument is the Slackdump archive directory, not the SQLite file itself.
This updates the existing `slackdump.sqlite` in place; the archive directory
name does not change.

To remove identical duplicate records after a successful resume, use:

```bash
slackdump resume -dedupe raw/Slack/project-alpha/slackdump_20260912_110311
```

After Slackdump updates the archive, run `/scan-raw`. The Slack ingestion
workflow compares the updated database with its local Slack ingestion state and
presents newly discovered messages for selection. Updating the archive is
performed by Slackdump and is outside the scope of the LLM Wiki.

## Ingest Slack messages

Run:

```text
/scan-raw
```

The scan checks Slackdump SQLite archives under `raw/Slack/` and determines
whether they contain messages that have not yet been ingested.

Slack ingestion is tracked at the message level rather than only by the
database's file hash. This matters because Slackdump can update an existing
archive with new messages while retaining messages that have already been
processed.

New messages are grouped by Slack thread. The scan presents numbered thread
candidates, and you can choose:

```text
1,3,5
```

to ingest selected threads, or:

```text
all
```

to ingest every newly discovered thread, or:

```text
none
```

to defer ingestion.

Each selected message is written as its own Markdown source file under
`wiki/sources/`. Thread replies are separate files and are connected using
their Slack channel and thread metadata.

The ingestion process records successfully created message files in local
state under:

```text
.llm-wiki/slack-ingest-manifest.jsonl
```

If an ingestion is interrupted, messages that were not successfully written
remain available during the next scan.

## Attachments

Slack messages may reference uploaded files, snippets, canvases, or external
files.

The initial workflow records attachment metadata in the message source file,
including information such as:

- Slack file ID;
- filename;
- file type or mode;
- whether a local archive copy is available.

The initial workflow does not download attachments or create separate source
files for them. It also does not duplicate attachments that may already have
been ingested elsewhere in the wiki.

## Required skills

The SQLite ingestion workflow requires these skills to be installed:

- `slackdump`
- `slackdump-sqlite3`

`slackdump-source` is installed with the bundle as supporting documentation and
is useful when identifying or troubleshooting Slackdump archive formats.

If a Slack ingestion is requested while either required skill is missing, the
workflow stops before reading or modifying the archive. It reports the missing
skill and instructs you to rerun the relevant setup script and approve the
grouped Slack skill installation.

## Read-only behavior

The Slack skills and ingestion workflow must not modify:

- the Slackdump SQLite database;
- Slackdump archive directories;
- uploaded files or avatars stored with the archive.

They may create:

- Markdown source files under `wiki/sources/`;
- local ingestion state under `.llm-wiki/`.
