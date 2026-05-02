# ingest-mail

This directory contains a skill for ingesting selected Apple Mail messages into
the LLM wiki workflow.

## Platform

This skill is intended for macOS only.

It depends on:

- the Apple Mail app
- `osascript`
- a GUI session where Mail automation is allowed
- configured Mail accounts and mailboxes

## Goal

The intended flow is:

1. Configure the Apple Mail accounts and mailboxes to scan.
2. Run `/ingest-mail`.
3. Scan recent messages in those configured accounts and mailboxes.
4. Use semantic reasoning to decide which emails belong to the current wiki.
5. Show one batch review and wait for approval.
6. Save approved emails into `raw/`.
7. Run the normal wiki ingest workflow.
8. Record processed message IDs and dates so unchanged emails are not handled
   twice.

## Mail Automation

This skill reads Apple Mail through AppleScript executed with `osascript`.
Apple Mail is a GUI automation source. Always run a minimal preflight before
the full scan.

Simple connectivity test:

```bash
osascript -e 'tell application "Mail" to count accounts'
```

Mailbox-level message count test:

```bash
osascript <<'APPLESCRIPT'
tell application "Mail"
	set outputLines to {}
	repeat with a in accounts
		try
			set accountName to name of a
			repeat with m in mailboxes of a
				set mailboxName to name of m
				set messageCount to count of messages of m
				set end of outputLines to accountName & " | " & mailboxName & " | " & messageCount
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

List available account names:

```bash
osascript <<'APPLESCRIPT'
tell application "Mail"
	set outputLines to {}
	repeat with a in accounts
		set end of outputLines to name of a
	end repeat
	set AppleScript's text item delimiters to linefeed
	return outputLines as string
end tell
APPLESCRIPT
```

List account and mailbox names:

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

If these commands fail, check:

- you are running in a normal macOS GUI session
- Terminal or your agent has permission to control Mail
- Mail is available and configured on this machine
- your agent is not blocked by a sandbox from talking to GUI apps

Observed failure modes can include `Connection invalid`, Automation permission
denials, or empty results caused by the execution environment rather than by
Mail itself. Do not update `processed.txt` or `last_scan.txt` if preflight fails.

## Config

The skill expects a config file that stores the lookback window, raw output
directory, account allowlist, and mailbox allowlist.

Before running the skill, set these values in `config.md`:

- `lookback_days`
- `raw_output_dir`
- `accounts`
- `mailboxes`
- `folders`
- `wiki`

Recommended value format:

```yaml
lookback_days: 14
raw_output_dir: "raw/"
accounts:
  - "Google"
mailboxes:
  - "INBOX"
folders:
  # User-created folder/label names to scan in addition to mailboxes above.
  # Use exact names from the account (run discovery to list them).
  # - "code"
  # - "market-research"
wiki: "Your Wiki Name"
```

Notes:

- `lookback_days` is the maximum number of days to scan. The actual scan
  window may be shorter — see **Scan Window Optimization** below.
- `raw_output_dir` should be a writable raw source directory.
- `accounts` must match Apple Mail account display names.
- `mailboxes` is for standard Apple Mail mailboxes (INBOX, Sent Mail, etc.).
- `folders` is for user-created folder/label names. If absent or empty, only
  `mailboxes` are scanned. Both lists are merged into a single allowlist before
  the scan runs — Apple Mail's object model treats both as mailboxes under an
  account.
- `wiki` is optional but useful when you maintain multiple wikis.

## Scan Window Optimization

Each successful scan writes the current UTC time to `last_scan.txt` as a
single ISO-8601 line (e.g. `2026-04-27T14:32:05Z`). On the next run, the
skill reads this timestamp and computes an effective lookback window:

```
effective_lookback = min(lookback_days, ceil(days_since_last_scan) + 1)
```

The `+1` day buffer covers Apple Mail sync delays and minor clock skew. If
`last_scan.txt` is missing, unparseable, or contains a future timestamp
(negative diff), the skill falls back to `lookback_days` in full.

The effective window is reported before the scan runs:

```text
Scan window: last {N} day(s)
  (lookback_days=14, last_scan=2026-04-27T14:32:05Z)
```

`last_scan.txt` is written after the osascript output is successfully parsed,
even when the scan returns zero messages. It is not staged in git commits.

## Candidate Selection

This skill uses explicit account and mailbox allowlists.

It:

1. scans only configured accounts
2. scans only configured mailboxes within those accounts
3. filters messages by the lookback window
4. checks `processed.txt` to skip already evaluated message versions
5. uses semantic reasoning to decide if each message belongs to the current
   wiki
6. waits for batch approval before writing raw files

The Apple Mail message ID is the durable identity. Do not key processing logic
off subjects, because subjects can repeat, change by thread, or be empty.
Subjects are for display and filename slugs only.

## Processed Manifest

The processed manifest is a plain text file. Each line represents one
processed version of an email:

```text
{message_id}\t{date_received_or_sent_text}
```

Recommended behavior:

- one processed email version per line
- append new lines instead of rewriting history
- the latest line for a message ID is the current processed state
- skipped messages are recorded too
- manual removal of a line allows reprocessing
- keep the original Apple date text for human debugging

## Raw Output

Each approved Apple Mail message should become one raw markdown file in
`raw/` or the configured raw output directory.

Recommended filename format:

```text
{YYYY-MM-DD}-email-{slug}-{short_message_id}.md
```

Include a short message-ID hash or suffix so duplicate subjects do not collide.
Never overwrite an existing raw file; if a collision still happens, add a
deterministic numeric suffix or use a longer message-ID hash.

Recommended structure:

```text
Subject: {subject}
Message ID: {message_id}
Source: Apple Mail
Account: {account}
Mailbox: {mailbox}
From: {sender}
To: {recipients}
Sent: {sent_date}
Received: {received_date}
Capture method: Apple Mail via osascript

{verbatim plain text body}
```

The raw file is the immutable source record. The wiki ingest flow does the
synthesis afterward.

## What The User Must Do Before Running The Skill

Before the first run, the user should:

1. Confirm Apple Mail can be queried from Terminal with `osascript`.
2. Run the account/mailbox listing command above.
3. Create or update `config.md` with the desired accounts and mailboxes.
4. Create an empty `processed.txt` file if it does not already exist.
5. Make sure the selected mailbox scope is narrow enough for review.

`last_scan.txt` is created automatically after the first successful scan; no
manual setup is needed.

## Robustness Notes

- Run the `count accounts` preflight before the full scan.
- Count messages through `mailboxes of account`; root-level `count messages`
  can fail with `Can't get every message. (-1728)`, and root-level
  `mailboxes` can include special mailboxes that do not expose `account`.
- If preflight fails, stop without updating `processed.txt`.
- Retry with approved elevated permissions when the failure is caused by
  sandboxed GUI automation access.
- Guard per-message extraction so one malformed message does not abort the
  batch.
- Use full plain text body content in v1; do not preserve attachments or HTML.
- Use message IDs for dedupe and routing state; do not depend on exact subject
  matching.
- Batch approval is required before writing raw files or updating the wiki.

## Notes

Apple Mail can be a useful review inbox for durable source material, but email
often contains sensitive or logistical content. This skill keeps v1 narrow:
configured accounts, configured mailboxes, explicit batch approval, and
immutable raw files for approved messages only.
