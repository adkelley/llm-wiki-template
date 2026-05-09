---
name: ingest-mail
description: |
  Himalaya-backed mail ingest skill for LLM Wiki users. Trigger whenever the
  user types "/ingest-mail", says "ingest email", "scan mail", "review
  mailbox", "process my email", or asks to find mailbox messages that may be
  relevant to the wiki. Uses the Himalaya CLI only. Does not use Apple Mail,
  direct provider APIs, or mailbox mutation commands. Reads config and state
  before scanning, evaluates new messages against the wiki topic, uses thread
  context for judgment, asks for approval, then saves approved messages into
  raw/ and runs the standard wiki ingest workflow.
---

# /ingest-mail - Himalaya Mail Ingest

## Purpose

Scan a user's previously authorized mailbox through the `himalaya` CLI, find
messages that might belong in the current wiki, ask for approval, and preserve
approved messages as immutable raw sources for the normal wiki ingest workflow.

This skill is intentionally read-only with respect to mail. It may list
accounts, list folders, list envelopes, and read messages. It must not mark
messages read, move, delete, reply, flag, send, or download attachments.

Use Himalaya only. Do not use Apple Mail, `osascript`, Gmail APIs, Microsoft
Graph, direct IMAP libraries, or provider-specific APIs in this skill.

## Required Local Files

This skill is intended to work for both Codex and Claude installs. The
installed skill directory is usually one of:

- Codex: `./skills/ingest-mail/`
- Claude: `.claude/skills/ingest-mail/`

Use whichever directory contains the currently loaded `ingest-mail` skill.
Read and write state only inside that installed skill directory.

Required user-managed files:

- `config.toml` - account and folder scope, scan window, raw output directory,
  and optional limits.
- `state.jsonl` - append-only records for evaluated message versions.
- `last_scan.txt` - UTC ISO-8601 timestamp for the last successful scan.

Required helper files:

- `scan_mail.py` - orchestrates Himalaya preflight, scanning, candidate
  extraction, preview-only message reads, state filtering, approved raw-source
  export, and finalize.
- Sibling Python modules such as `config.py`, `state.py`, `parsers.py`,
  `himalaya_client.py`, `raw_export.py`, `thread_context.py`, `models.py`, and
  `errors.py` - support the scanner and must remain installed with
  `scan_mail.py`.

If `scan_mail.py` is missing, stop and say it needs to be implemented before
the skill can scan mail. If sibling helper modules are missing, stop and ask
the user to reinstall or update the skill files. Do not recreate the Python
logic inline in the agent response.

## Configuration

If `config.toml` is missing, stop and ask the user to create it in the installed
skill directory. The template includes `config.example.toml`; copy that file to
`config.toml` in the installed skill directory and edit it for the user's
Himalaya account and folder names. Use this minimal shape:

```toml
lookback_days = 14
raw_output_dir = "raw/"
accounts = ["personal"]
folders = ["INBOX"]
max_messages_per_folder = 100
max_thread_context_messages = 8
wiki = "your-wiki-name"
```

Rules:

- `accounts` must contain explicit Himalaya account names.
- `folders` must contain explicit Himalaya folder names or aliases.
- Never scan all accounts or all folders by default.
- `lookback_days` is the maximum scan window. The scanner combines it with
  `last_scan.txt` to compute `scan_window_days`.
- `raw_output_dir` should normally be `raw/`.

If the user is unsure about account or folder names, prefer the helper script's
read-only commands:

```bash
python3 {skill_dir}/scan_mail.py preflight --skill-dir {skill_dir}
python3 {skill_dir}/scan_mail.py folder-list --skill-dir {skill_dir}
```

The underlying safe Himalaya discovery commands are:

```bash
himalaya account list --output json
himalaya folder list --account {account} --output json
```

## Himalaya Installation Notes

The user must configure and authorize Himalaya before this skill scans mail.
This skill does not manage OAuth, app passwords, keyrings, or provider-specific
credential setup.

Homebrew installs a prebuilt Himalaya package. Cargo features cannot be chosen
through Homebrew, so `brew install himalaya` may not be sufficient for setups
that require optional features such as OAuth 2.0 or keyring support. If a
configured account needs those features, the user should install Himalaya with a
method that supports the required feature set, such as Cargo, Nix, or a source
build.

Preflight failures that look like missing authentication support should be
reported as Himalaya setup issues. Do not work around them in Python and do not
ask the user for mailbox credentials.

## Step 1 - Read Wiki Topic

Read the user's active wiki instructions before scanning. Use the instruction
file for the current environment when it is present:

1. In Codex-oriented installs, read `AGENT.md`.
2. In Claude-oriented installs, read `CLAUDE.md`.
3. If both files exist, read both and prefer the one matching the active agent;
   their `## Domain` sections should normally agree.
4. Extract the `## Domain` section and use it as the primary topic.
5. If the domain is still the placeholder text, also inspect `wiki/index.md`,
   `wiki/overview.md`, and existing `wiki/concepts/` or `wiki/entities/` pages
   to infer the wiki's current topic.

Do not evaluate messages against generic interests. Evaluate them against this
wiki's actual topic and existing wiki pages.

## Step 2 - Read State

Before scanning, read:

- `config.toml`
- `state.jsonl` if present
- `last_scan.txt` if present

Treat `state.jsonl` as append-only. The latest record for a message identity
and version is the current decision. Do not rewrite, sort, deduplicate, or
compact it during normal ingest.

Expected JSONL record shape:

```json
{"account":"personal","folder":"INBOX","envelope_id":"143950","decision":"no","evaluated_at":"2026-05-07T23:42:56Z"}
```

The Python helper is responsible for parsing this file and deciding which
envelope IDs are new for each account and folder. If `state.jsonl` is
malformed, stop and report the problem rather than skipping state.

## Step 3 - Preflight Himalaya

Run the Python scanner in preflight mode. It should verify at least:

- `himalaya --version`
- `himalaya account list --output json`
- each configured account exists
- each configured folder can be listed or read for envelopes

If preflight fails, stop. Do not treat failure as "no mail found." Do not write
raw files, update wiki pages, append `state.jsonl`, or update `last_scan.txt`.

The preflight should use read-only Himalaya commands such as:

```bash
himalaya --version
himalaya account list --output json
himalaya folder list --account {account} --output json
```

## Current Command Sequence

For normal review, use the helper commands in this order:

```bash
python3 {skill_dir}/scan_mail.py preflight --skill-dir {skill_dir}
python3 {skill_dir}/scan_mail.py scan --skill-dir {skill_dir} --include-messages --limit 10
python3 {skill_dir}/scan_mail.py decisions-template --skill-dir {skill_dir} --limit 10
python3 {skill_dir}/scan_mail.py export-approved --skill-dir {skill_dir} --decisions {path_to_decisions_json}
python3 {skill_dir}/scan_mail.py finalize --skill-dir {skill_dir} --decisions {path_to_decisions_json}
```

Only run `export-approved` after the user approves the relevant `yes` rows.
Only run `finalize` after approved raw files and wiki updates are complete.

## Step 4 - Scan Candidates

Run the scanner to collect candidate messages:

```bash
python3 {skill_dir}/scan_mail.py scan --skill-dir {skill_dir}
```

The scanner should return structured JSON containing:

- `ok`
- configured `accounts` and `folders`
- `last_scan` if present
- `scan_window_days`
- `candidate_count`
- `candidates`, each containing an `envelope`, optional `message`, and
  `thread_context`
- `excluded_count`
- `excluded`, each containing a deterministic skip reason such as
  `already evaluated in state.jsonl`

Use the lightweight scan by default:

```bash
python3 {skill_dir}/scan_mail.py scan --skill-dir {skill_dir} --limit 25
```

Use message-body mode only when the agent is ready to evaluate email content:

```bash
python3 {skill_dir}/scan_mail.py scan --skill-dir {skill_dir} --include-messages --limit 10
```

When preparing the approval file, generate a fail-closed decisions template:

```bash
python3 {skill_dir}/scan_mail.py decisions-template --skill-dir {skill_dir} --limit 10
```

This command outputs one JSON decision object for each new candidate, with
`decision` set to `ambiguous`. Edit that template after review so relevant
approved messages are `yes`, clear non-matches are `no`, and unresolved items
remain `ambiguous` or `context_only`.

Message reads must use Himalaya's `--preview` flag so scanning does not mark
mail as seen. The scanner uses `last_scan.txt` and `lookback_days` to compute
`scan_window_days`, then asks Himalaya for envelopes with:

```text
after YYYY-MM-DD order by date desc
```

This window is an optimization, not the durable dedupe mechanism. The scanner
still uses `state.jsonl` to avoid repeatedly returning already evaluated
envelope IDs. Already-evaluated messages should be reported in `excluded` so
the user can see that they were skipped intentionally. `last_scan.txt` is
updated by `finalize` after the approved batch is handled.

The `envelope-list` command is diagnostic and does not apply the scan window.
Use `scan` for normal ingest review.

`thread_context` is v1 envelope context, not full thread reconstruction. The
helper groups nearby listed envelopes by normalized subject, strips common
reply/forward prefixes such as `Re:`, `Fw:`, and `Fwd:`, excludes the candidate
itself, and caps context with `max_thread_context_messages`. Use this context
to improve routing and judgment, but do not treat subject matches as proof that
messages belong to the same conversation.

## Step 5 - Evaluate Relevance

For each new candidate, decide:

**Relevant (`yes`)** if the message contains durable wiki value, such as:

- a claim, observation, source, link, quote, or reference related to the wiki
  topic
- a research lead, technical detail, announcement, or decision worth preserving
- a person, organization, product, or concept already tracked by the wiki
- a substantive discussion that could become a source summary, concept update,
  entity update, comparison, or synthesis

**Not relevant (`no`)** if it is:

- routine logistics, receipts, alerts, support boilerplate, or calendar noise
- a newsletter with no durable topic value
- personal or sensitive content unrelated to the wiki
- too short, vague, or attachment-dependent to evaluate

**Ambiguous (`?`)** if:

- it may belong to another wiki
- thread context is insufficient
- relevance depends on user intent
- it contains sensitive material and the value is not clear

Never silently ingest an ambiguous message.

Sender and recipient matches against `wiki/entities/` are useful review
signals, but they are not sufficient for relevance by themselves. Treat entity
matches as a boost only when the message body also contains durable wiki value.
Skip pure logistics even when the sender or recipient is documented in the
wiki.

## Step 6 - Present Review

Before writing anything, show a compact review:

```text
Mail scan complete.
Last scan: {last_scan or "none"}
Scan window: last {scan_window_days} day(s)
Candidates evaluated: {N}
Mechanically excluded: {M}

[yes] {subject} - {one-sentence reason}
[no]  {subject} - {one-sentence reason}
[?]   {subject} - needs user routing/approval: {reason}

Excluded:
- {subject or envelope_id} - {reason}
```

Then ask for approval:

```text
Approve ingest of the {N} relevant email(s) listed above? [y/N]
```

If the user does not approve, stop without writing raw files, updating wiki
pages, appending `state.jsonl`, or updating `last_scan.txt`.

For approved and skipped candidates, create a decisions JSON file by running
`decisions-template` and editing each `decision` value after review:

```json
[
  {
    "account": "personal",
    "folder": "INBOX",
    "envelope_id": "143950",
    "decision": "no"
  }
]
```

Use `yes` for messages approved for raw export, `no` for reviewed non-matches,
`ambiguous` when the user has not resolved routing or sensitivity, and
`context_only` when a message is useful only as context for another approved
email.

## Step 7 - Save Approved Raw Sources

After approval, write raw files through the helper script:

```bash
python3 {skill_dir}/scan_mail.py export-approved --skill-dir {skill_dir} --decisions {path_to_decisions_json}
```

The command must export only decisions marked `yes`. It must skip `no`,
`ambiguous`, and `context_only` decisions. For each approved relevant new
message, it creates one raw markdown file:

```text
{raw_output_dir}/{YYYY-MM-DD}-email-{slug}-{short_message_id}.md
```

Include a stable short hash or suffix derived from the message ID. Never
overwrite an existing raw file.

Raw file format:

```text
Subject: {subject}
Envelope ID: {envelope_id}
Source: Himalaya
Account: {account}
Folder: {folder}
From: {from}
To: {to}
Date: {date}
Capture method: Himalaya CLI

{verbatim plain text message body}

---

Thread context used for evaluation:

{clearly labeled envelope metadata or "None captured"}
```

Do not paraphrase or clean the approved message body. Do not include
attachments in v1. If the email is mostly attachment or image content, skip it
unless the user explicitly asks for future attachment support.

Raw export preserves the v1 subject-based thread context as labeled envelope
metadata. It includes related envelope IDs, subjects, senders, recipients, and
dates. It does not include full related message bodies in v1.

If raw export fails, stop before wiki ingest and before finalizing state.

## Step 8 - Run Standard Wiki Ingest

After raw files are written, run the repository's standard ingest workflow for
each approved raw email source:

1. Run the ingest guard when available.
2. Read the raw email source.
3. Present 3-5 key takeaways.
4. Create or update the relevant `wiki/sources/summary-{slug}.md` page.
5. Update `wiki/index.md`.
6. Update relevant concept and entity pages.
7. Flag contradictions.
8. Append a structured entry to `wiki/log.md`.
9. Record the successful ingest in the ingest guard when available.

Suggested log entry:

```text
## [YYYY-MM-DD] ingest | {subject} (email)
Source: raw/{filename}.md
Original envelope ID: {envelope_id}
Account: {account}
Folder: {folder}
Pages created: ...
Pages updated: ...
Contradictions flagged: ...
Notes: {topic summary}
```

## Step 9 - Update State

Only after approved raw files and wiki updates complete, append state records
for the evaluated batch by running the helper script's finalize command:

```bash
python3 {skill_dir}/scan_mail.py finalize --skill-dir {skill_dir} --decisions {path_to_decisions_json}
```

The finalize step should:

- append `yes`, `no`, `ambiguous`, and `context_only` decisions supplied in the
  decisions JSON file
- write the current UTC timestamp to `last_scan.txt` after the scan and state
  update succeed
- fail closed if state cannot be appended

Do not stage or commit installed skill state files unless the user explicitly
asks.

The helper uses these exit-code categories: `2` for config or CLI argument
errors, `3` for Himalaya command failures, `4` for Himalaya JSON parse errors,
`5` for state or decisions-file errors, and `6` for raw-file write errors.

## Step 10 - Commit Wiki Changes

If raw or wiki files changed, follow the local repository's git procedure.
Stage only allowed source/wiki files. Do not stage skill state, Himalaya config,
mailbox data, `.claude/`, `.codex/`, or downloaded attachments.

## Python Tutor Workflow

The Python scripts for this skill are intentionally developed separately.
When asked to build them, work incrementally and explain each step.

Recommended order:

1. Parse `config.toml`.
2. Wrap read-only Himalaya commands.
3. Build fixture-based JSON parsers for account, folder, envelope, and message
   output.
4. Read and write `last_scan.txt`.
5. Read and append JSONL state.
6. Model candidates and optional message bodies.
7. Add tests before running against a real mailbox.

Do not replace this learning workflow by dumping a full Python implementation
unless the user explicitly asks for that.

## Safety Rules

- Never scan all accounts or folders by default.
- Never mutate mailbox state.
- Never write raw files, update wiki pages, append `state.jsonl`, or update
  `last_scan.txt` before approval.
- Never treat Himalaya or parser failure as an empty mailbox.
- Never ingest ambiguous messages silently.
- Never include attachments, binary content, or HTML preservation in v1.
- Never expose secrets from Himalaya config or environment variables in status
  output.
- Keep raw email sources immutable after creation.
