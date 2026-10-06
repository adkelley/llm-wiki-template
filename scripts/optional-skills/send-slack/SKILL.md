---
name: send-slack
description: |
  Send a narrowly scoped Slack message using the existing Slackdump browser
  session. Trigger when the user asks to send or post a Slack message, or to
  reply in a Slack thread. Do not use this skill for Slack archive ingestion,
  administration, uploads, reactions, deletion, editing, or scheduling.
---

# /send-slack - Send a Slack Message

Requires Python 3.10 or newer.

## Purpose

Send one user-approved Slack message through the local Python adapter at:

```text
scripts/optional-skills/send-slack/slack_send.py
```

The adapter reuses the local Slackdump browser-session credentials (`xoxc`
token plus `xoxd` cookie) through a small HTTP client. Do not substitute the
Python Slack SDK: it expects OAuth bot/user tokens such as `xoxb` or `xoxp` and
does not natively support this credential model.

## Scope

Supported operations:

1. resolve a channel by exact name or channel ID;
2. send a message to that channel; and
3. optionally reply to an existing thread with `--thread-ts`.

Do not expand this skill to cover uploads, reactions, message edits or deletes,
workspace administration, broad search, or scheduled messages.

## Required confirmation

Sending is an external write. Before executing a real send:

1. Confirm the destination channel, exact message text, and thread timestamp if
   present with the user.
2. Run a dry-run and inspect its structured JSON result.
3. Ask for explicit confirmation if it has not already been given.
4. Only then rerun the same command with `--confirm`.

Never infer confirmation from the initial request alone when the exact message
or destination is still changing. If the user asks only for a preview, use
`--dry-run` and do not send.

## Invocation

Run commands from the repository root. Use `--channel` for an exact channel
name (with or without a leading `#`) or a Slack channel ID. Use `--message` for
the exact text. Add `--thread-ts` only when the user wants a reply to an
existing thread.

Preview:

```bash
python3 scripts/optional-skills/send-slack/slack_send.py \
  --channel "#general" \
  --message "MESSAGE TEXT" \
  --dry-run
```

Confirmed write:

```bash
python3 scripts/optional-skills/send-slack/slack_send.py \
  --channel "#general" \
  --message "MESSAGE TEXT" \
  --confirm
```

The adapter defaults to a dry-run when neither `--dry-run` nor `--confirm` is
provided, and rejects ambiguous or contradictory flags. It also rejects empty
or whitespace-only channel and message values. A `--thread-ts` value must use
Slack's timestamp format, such as `1712345678.123456`.

Treat a nonzero exit status as a failed send; do not claim that a message was
sent unless the adapter reports success. Invalid arguments return exit code
`2`; runtime failures return exit code `1`.

## Credentials and security

The adapter reads credentials from:

```text
~/.cache/slackdump/slackdump_garibaldi.env
```

It must require `SLACK_TOKEN` and `SLACK_COOKIE`, verify that the file is a
regular readable file, and avoid displaying the values. Do not pass them as
arguments or environment values created by the skill invocation. Do not print
request headers, cookies, response bodies containing credential material, or
tracebacks that might contain secrets.

Use the Slackdump-compatible browser-session request model: send the token in
the request form/body as required by Slack's web API and send the cookie in the
HTTP `Cookie` header. Keep the HTTP surface narrow and centralized in the
adapter so it can be mocked in tests. Do not persist credentials or alter
Slackdump's cache, archives, or browser state.

## Output and failure handling

Expect one sanitized JSON object on stdout. A dry-run response identifies the
operation, `dry_run` status, resolved channel ID/name, exact message, and
optional thread timestamp. After a successful write, the response also
includes the new message timestamp. It must not include credentials, cookies,
raw headers, or full response payloads.

Runtime failures use these safe error codes:

- `credentials_error` — credentials could not be loaded;
- `channel_error` — the channel was not found or the name was ambiguous;
- `slack_api_error` — Slack rejected the request; and
- `network_error` — Slack could not be reached.

Report failures clearly using the adapter's safe error code/message. Important
cases include:

- missing, unreadable, or malformed credentials;
- authentication failure or an expired browser session;
- channel not found or ambiguous channel name;
- invalid thread timestamp;
- Slack HTTP/API errors; and
- transport timeout or other network failure.

Do not retry a write automatically after an ambiguous timeout: the message may
have been accepted by Slack. Ask the user whether to investigate before
attempting another send.

## No archive ingestion

This skill sends live Slack messages. It does not read or modify Slackdump
SQLite archives and must not be invoked as a substitute for `ingest-slack`.
