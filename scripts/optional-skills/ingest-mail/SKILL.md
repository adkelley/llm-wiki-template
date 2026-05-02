---
name: ingest-mail
description: |
  Apple Mail ingest skill for LLM-wiki users. Trigger whenever the user
  types "/ingest-mail", says "ingest email", "review Apple Mail", "process
  my email", or asks to pull in relevant Mail messages. Scans Apple Mail on
  macOS via osascript, limited to configured accounts and mailboxes, selects
  recent messages, evaluates each message for wiki relevance, asks for batch
  approval, saves approved emails into raw/, and runs the
  standard wiki ingest workflow. Tracks message IDs and date strings in a
  manifest so unchanged messages are skipped on future runs. Always read
  config.md and processed.txt before scanning.
---

# /ingest-mail - Apple Mail Ingest

## Purpose

Scan Apple Mail on macOS for recent messages in configured accounts and
mailboxes, evaluate which messages belong in the current wiki, ask for batch
approval, and feed approved messages into the standard wiki ingest workflow.

This skill is for turning selected email conversations into wiki source
material. Email often contains sensitive or logistical content, so v1 requires
explicit account/mailbox scoping and a batch approval gate before writing raw
files.

This skill uses Apple Mail via `osascript` directly. It does not use Mail
rules, tags, attachments, direct database access, or background scheduling in
v1.

---

## Configuration Files

This skill requires two files in its own directory. The exact path depends on
how the skill is installed:

- Codex repo-local install:
  - `./skills/ingest-mail/config.md` - account/mailbox scope and raw output directory
  - `./skills/ingest-mail/processed.txt` - append-only manifest of processed message IDs
  - `./skills/ingest-mail/last_scan.txt` - UTC ISO-8601 timestamp of the last successful scan
- Claude Code-style install:
  - `.claude/skills/ingest-mail/config.md` - account/mailbox scope and raw output directory
  - `.claude/skills/ingest-mail/processed.txt` - append-only manifest of processed message IDs
  - `.claude/skills/ingest-mail/last_scan.txt` - UTC ISO-8601 timestamp of the last successful scan

If either is missing, run first-time setup (Step 1).

---

## Step 1 - Read Config and Manifest (or First-Time Setup)

### If config.md exists:

Read it and extract:

- `lookback_days` - number of days back to consider messages
- `raw_output_dir` - directory to write raw email files into
- `accounts` - Apple Mail account display names to scan
- `mailboxes` - standard Apple Mail mailbox names to scan (INBOX, Sent Mail, etc.)
- `folders` - user-created folder/label names to scan in addition to `mailboxes`.
  If absent or empty, only `mailboxes` are scanned. Both lists are merged into a
  single allowlist before the AppleScript scan runs.
- `wiki` - optional wiki identifier for reporting and routing context

The combined scan target is `mailboxes + folders`. In AppleScript, both map to
the same `mailboxes of account` property — the distinction in config is only for
human clarity when editing. Merge them into one allowlist before building the
AppleScript filter.

Read `processed.txt`. If it does not exist, treat it as empty.

Read `last_scan.txt`. If it exists, parse its single line as a UTC ISO-8601
timestamp (e.g. `2026-04-27T14:32:05Z`) and compute:

```
days_since_last_scan = (now_utc - last_scan_utc).total_seconds() / 86400
effective_lookback   = min(lookback_days, ceil(days_since_last_scan) + 1)
```

The `+1` day buffer catches Apple Mail sync delays and clock skew across
devices. If `days_since_last_scan` is negative (clock was adjusted forward,
file was manually edited with a future date, or NTP correction), discard the
timestamp and fall back to `effective_lookback = lookback_days` — do not
clamp to 1, as that would silently produce a near-empty scan.

If `last_scan.txt` does not exist or cannot be parsed, fall back to
`effective_lookback = lookback_days`.

Report the computed window before scanning:

```text
Scan window: last {effective_lookback} day(s)
  (lookback_days={lookback_days}, last_scan={last_scan_timestamp or "none"})
```

### If config.md does not exist (first run):

Tell the user to create `config.md` in the skill's own directory
(`./skills/ingest-mail/` or `.claude/skills/ingest-mail/`, depending on the
installation) with at least:

```text
# ingest-mail config

lookback_days: 14
raw_output_dir: "raw/"
accounts:
  - "Google"
mailboxes:
  - "INBOX"
folders:
  # Add user-created folder/label names here, e.g.:
  # - "code"
  # - "market-research"
wiki: "your-wiki-name"
```

Tell the user to run the account/mailbox listing command in Step 2b if they
are unsure of Apple Mail's exact account names. Create an empty
`processed.txt` in that same skill directory.

Do not try to auto-configure Apple Mail access in v1. Stop after explaining
the required config.

---

## Step 2 - Scan Apple Mail

Apple Mail is a GUI automation source, so treat it as flaky until proven
available in the current execution environment.

### 2a. Preflight Mail automation

Before the full scan, run a minimal connectivity check:

```bash
osascript -e 'tell application "Mail" to count accounts'
```

If this fails with errors such as:

- `Connection invalid`
- Automation permission prompts or denials
- Apple event or scripting errors that indicate Mail cannot be controlled

then do **not** continue to the full scan. Report that the skill requires:

- macOS
- Apple Mail available in a normal GUI session
- user-granted Automation permission for the terminal/agent process
- an execution context allowed to talk to GUI apps

In sandboxed agent environments, the same command may fail in the sandbox but
work when run with approved elevated permissions. If the agent has an
escalation mechanism, retry the preflight and full scan with permission instead
of treating the mail corpus as empty.

Do not update `processed.txt` if preflight fails.

Do not use root-level `count messages` as the preflight. On some Apple Mail
setups it fails with `Can't get every message. (-1728)`. Count accounts for
connectivity, then count messages through mailbox objects when validating
message access. Also avoid root-level `mailboxes` for account-scoped scans;
some special mailboxes do not expose `account`. Iterate `accounts`, then
`mailboxes of account`.

### 2b. Optional account and mailbox discovery

If the configured account or mailbox names do not match anything, or if the
user asks what names Apple Mail exposes, run:

```bash
osascript <<'APPLESCRIPT'
tell application "Mail"
	set outputLines to {}
	repeat with a in accounts
		try
			set accountName to name of a
			repeat with m in mailboxes of a
				set end of outputLines to accountName & " | " & name of m
			end repeat
		on error errMsg number errNum
			set end of outputLines to "ERROR | " & accountName & " | " & errNum & " | " & errMsg
		end try
	end repeat
	set AppleScript's text item delimiters to linefeed
	return outputLines as string
end tell
APPLESCRIPT
```

Use the returned account and mailbox names exactly in `config.md`.

### 2c. Full scan

Run `osascript` to retrieve Apple Mail metadata and message content from
configured accounts and mailboxes. Use `effective_lookback` (computed in
Step 1) as the date cutoff — not the raw `lookback_days` value.

Before building the AppleScript, merge `mailboxes` and `folders` from config
into a single `allowedMailboxes` list. In Apple Mail's object model, both
standard mailboxes and user folders appear as mailboxes under an account —
the split in config is for human readability only.

Use this AppleScript pattern:

```bash
osascript <<'APPLESCRIPT'
set recordSep to character id 30
set fieldSep to character id 31
set outputRecords to {}
set allowedAccounts to {"Google"}
-- Merge mailboxes + folders from config into one list:
set allowedMailboxes to {"INBOX", "code", "market-research"}

tell application "Mail"
	repeat with a in accounts
		try
			set accountName to name of a
			if allowedAccounts contains accountName then
				repeat with mb in mailboxes of a
					try
						set mailboxName to name of mb
						if allowedMailboxes contains mailboxName then
							repeat with msg in messages of mb
								try
									set messageID to message id of msg
									set messageSubject to subject of msg
									set senderText to sender of msg
									set sentAt to date sent of msg as text
									set receivedAt to date received of msg as text
									set readStatus to read status of msg as text
									set flaggedStatus to flagged status of msg as text
									set messageContent to content of msg
									set recordFields to {messageID, messageSubject, senderText, sentAt, receivedAt, accountName, mailboxName, readStatus, flaggedStatus, messageContent}
									set AppleScript's text item delimiters to fieldSep
									set recordText to recordFields as text
									set end of outputRecords to recordText
								end try
							end repeat
						end if
					end try
				end repeat
			end if
		end try
	end repeat
end tell

set AppleScript's text item delimiters to recordSep
return outputRecords as text
APPLESCRIPT
```

Before running the full scan, adapt `allowedAccounts` and `allowedMailboxes`
from `config.md`. Do not hardcode the example values.

Interpret the output as:

- records separated by ASCII record separator (`character id 30`)
- fields inside each record separated by ASCII unit separator (`character id 31`)

Each record is:

```text
message_id <US> subject <US> sender <US> date_sent <US> date_received <US> account <US> mailbox <US> read_status <US> flagged_status <US> content
```

Immediately parse the scan into structured records keyed by `message_id`. Do
not use subjects as internal identifiers; subjects are mutable, may be empty,
may contain punctuation, and are not unique. Use subjects only for display,
slugs, and human-facing summaries.

Once the scan output is successfully parsed, write the current UTC time to
`last_scan.txt` (overwriting any previous value):

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" > {skill_dir}/last_scan.txt
```

Write this file even when the scan returns zero messages. Do **not** write it
if the preflight check failed or if the osascript call itself errored — the
point is to record when a real scan completed, so the next run's effective
window is accurate.

If Apple Mail access fails, report that the skill requires:

- macOS
- Apple Mail available in a GUI session
- user-granted Automation permission for terminal/agent access to Mail

Stop without updating `processed.txt`.

---

## Step 3 - Select Candidate Messages

From the scanned message set:

1. Filter to messages whose received date or sent date is within `lookback_days`
2. Ignore messages with empty or near-empty body content
3. If a message is unreadable, skip it and report it

Load `processed.txt` and interpret it as an append-only manifest with one
entry per processed version of a message:

```text
{message_id}\t{date_received_or_sent_text}
```

Example:

```text
ABCDEF123456@mail.gmail.com	Thursday, April 23, 2026 at 4:14:18 PM
111122223333@mail.gmail.com	Friday, April 24, 2026 at 9:02:11 AM
```

Manifest rules:

- Latest entry for a given message ID wins
- If message ID is absent: message is new and eligible
- If message ID exists and date text matches: skip as already processed
- If message ID exists and date text is newer/different: re-evaluate

Parsing guidance:

- Treat Apple date strings as localized display text, not as durable timestamps.
- When possible, normalize dates to ISO-8601 or epoch seconds in any temporary
  parsed representation used during the run.
- Keep the original Apple date text in `processed.txt` because it is what
  AppleScript returns and is useful for human debugging.
- Compare processed versions by exact message ID plus exact date text unless a
  normalized timestamp is also stored by a future manifest version.

If no candidate messages remain, report:

```text
No new Apple Mail messages found within the last {lookback_days} day(s).
Manifest: {N} processed message version(s).
```

Stop here.

---

## Step 4 - Evaluate Each Message for Wiki Relevance

For each candidate message, answer two questions.

**Q1: Is this wiki-relevant?**

Relevant if it contains any of:

- A hypothesis, observation, or claim about any topic in `wiki/concepts/`
  or `wiki/entities/`
- A research lead, reference, link, quote, or source worth preserving
- A newsletter or digest containing durable announcements, technical details,
  links, or summaries that clearly fit the current wiki
- A design idea, product concept, or open question the user wants to track
- A reference to a person, company, product, or term already in the wiki
- Anything that clearly belongs to the current wiki's domain

Not relevant if it is:

- Routine logistics, receipts, support messages, or newsletters with no durable
  wiki value
- Calendar invites, meeting cadence messages, Teams/Zoom boilerplate, and
  scheduling-only threads, even when the company or person is wiki-relevant
- Sensitive personal content unrelated to this wiki's domain
- Too vague or too short to route confidently
- Mostly attachments, images, or HTML layout with little usable body text

Meeting-related email is relevant only when it contains substantive agenda,
decisions, notes, analysis, or source material. Pure meeting logistics belong
to a future calendar ingest skill, not `ingest-mail`.

**Q2: Which wiki?**

Currently: evaluate against this wiki first.

If a message clearly belongs to another wiki or could plausibly belong to more
than one wiki, ask the user before ingesting it.

Show the evaluation summary before proceeding:

```text
Evaluation results:
  [yes] {subject} - relevant: {one-sentence reason}
  [no]  {subject} - skipped: {reason}
  [?]   {subject} - ambiguous: needs routing confirmation
```

Then ask for batch approval before writing any raw files:

```text
Approve ingest of the {N} relevant email(s) listed above? [y/N]
```

If the user does not approve, stop without writing raw files and without
updating `processed.txt`.

Never silently ingest an ambiguous message into the current wiki.

---

## Step 5 - Save Messages and Run Ingest

For each approved relevant message:

### 5a. Write the raw email file

Create `{raw_output_dir}/{date}-email-{slug}-{short_message_id}.md` where:

- `date` is derived from received date when possible, otherwise sent date
- `slug` is a filesystem-safe form of the message subject
- `short_message_id` is a short stable hash or suffix derived from `message_id`

The message-ID suffix prevents collisions from duplicate subjects and repeated
versions of the same message.

Format:

```text
Subject: {subject}
Message ID: {message_id}
Source: Apple Mail
Account: {account}
Mailbox: {mailbox}
From: {sender}
To: {recipients if available}
Sent: {date_sent_text}
Received: {date_received_text}
Read: {read_status}
Flagged: {flagged_status}
Capture method: Apple Mail via osascript

{verbatim plain text content}
```

Do not paraphrase or clean the message body. `raw/` is immutable.

Do not include attachments in v1. If the email is mostly an attachment or
image, report it as skipped unless the user explicitly asks for attachment
handling in a future version.

Before writing, check whether the target path already exists. If it does, do
not overwrite it; add a deterministic numeric suffix or use a longer
message-ID hash.

### 5b. Run the standard ingest workflow

Per CLAUDE.md, the ingest workflow for `{raw_output_dir}/{filename}.md`:

1. Read the email
2. Present 3-5 key takeaways to the user
3. Create `wiki/sources/summary-{slug}.md`
4. Update `wiki/index.md`
5. Update all relevant concept and entity pages
6. Flag any contradictions with existing pages
7. Create new concept/entity pages if introduced
8. Append to `wiki/log.md`

Suggested log entry format:

```text
## [YYYY-MM-DD] ingest | {subject} (email)
Source: {raw_output_dir}/{filename}.md
Original message ID: {message_id}
Account: {account}
Mailbox: {mailbox}
Pages created: ...
Pages updated: ...
Contradictions flagged: ...
Notes: {topic summary}
```

---

## Step 6 - Update the Processed Manifest

After the batch is approved and all relevant raw files and wiki updates are
complete, append entries for every evaluated message version in this run:

```text
{message_id}\t{date_received_or_sent_text}
```

Rules:

- One processed message version per line
- No paths
- No quotes
- Skipped messages that were evaluated should also be recorded
- If a message changes later, append a new line with the same message ID and
  new date text
- The latest line for a message ID is the source of truth

This keeps the manifest append-only while still allowing manual reprocessing.

---

## Step 7 - Commit

Per CLAUDE.md git procedure:

```bash
git add raw/ wiki/
```

Do not stage `.claude/` or `last_scan.txt`. Do not push.

Commit message format:

```text
ingest: email(s) {slug1}, {slug2}

Co-Authored-By: {active_llm_model_and_effort} <{llm_company_email}>
```

Use the **actual LLM identity for the current session**, not a fixed
placeholder.

---

## Step 8 - Report Completion

```text
Apple Mail ingest complete.

Processed: {N} email(s)
  [yes] Ingested: {list of subjects}
  [no]  Skipped:  {list of subjects with reason}
  [?]   Asked:    {list of ambiguous subjects}

Wiki pages touched: {count}
Manifest updated: {skill_dir}/processed.txt
Log updated: wiki/log.md
```

---

## Behavior Guidelines

- **Use Apple Mail directly.** Do not route through Gmail APIs, IMAP, or a
  direct Mail database reader in v1.
- **Read config before scanning.** The account list, mailbox list, lookback
  window, and output directory are configurable. Do not hardcode them.
- **Preflight Apple Mail automation.** Always run the minimal `count accounts`
  check before the full scan. Sandbox/GUI permission failures are common; stop
  cleanly without touching the manifest if Mail cannot be reached.
- **Use account and mailbox allowlists.** Never scan all mailboxes by default.
- **Use message IDs internally.** Never key processing logic off exact
  subjects. Subjects can repeat, change by thread, and contain punctuation.
- **Manifest is append-only.** Never rewrite or deduplicate the manifest file.
  Use the most recent line for a message ID when deciding whether a message is
  new.
- **raw/ is immutable.** Once an email is written to `raw/`, never
  modify it in place.
- **Evaluate before ingesting.** Never ingest every recent message blindly.
- **Batch approval is required.** Do not write raw files or update the
  manifest until the user approves the evaluated batch.
- **Ambiguous relevance: ask.** Do not guess when multiple wikis are plausible.
- **Skip unreadable messages.** Unreadable or unsupported messages must be
  reported and skipped.
- **Generate collision-resistant filenames.** Include date, slug, and a short
  message-ID hash or suffix. Never overwrite an existing raw email file.
- **One commit per batch.** If multiple emails are ingested in one run, commit
  them together.

## Known Edge Cases

- Apple Mail automation may fail in sandboxed or headless contexts even when
  it works in Terminal. Retry with approved GUI/Automation permissions when
  available.
- Apple Mail account display names may differ from email addresses. Use the
  discovery command to populate `accounts`.
- Root-level `mailboxes` may include special mailboxes such as Outbox or
  Deleted Messages that do not expose `account`. Iterate `accounts`, then
  `mailboxes of account`.
- Mailbox names may repeat across accounts. Filter by account and mailbox
  together.
- Apple date strings are localized and may include non-breaking spaces or
  locale-specific punctuation. Normalize for in-run comparisons when possible.
- Attachments and image-only messages are out of scope for v1.
- Duplicate or empty subjects are legal. The message ID is the durable
  identity.

---

## Notes

This skill makes Apple Mail a controlled wiki source inbox:

**email -> /ingest-mail -> batch approval -> raw/ -> standard ingest -> wiki**

The core idea is to preserve only durable, approved email content as immutable
raw source material and let the normal wiki ingest flow do the synthesis and
cross-linking.
