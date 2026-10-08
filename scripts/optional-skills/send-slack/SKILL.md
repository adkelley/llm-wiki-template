---
name: send-slack
description: |
  Find unanswered Slack messages addressed to @dobby in the LLM Wiki's
  configured Slackdump channel, draft answers using the full thread context,
  and send user-approved answers through that channel's incoming webhook.
  Trigger when the user asks to check or answer Slack messages addressed to
  Dobby. Do not use this skill for Slack archive ingestion, administration,
  uploads, reactions, deletion, editing, or broad multi-channel messaging.
---

# /send-slack - Answer Slack Messages

## Purpose

Find messages addressed to Dobby in this wiki's Slackdump SQLite archive,
determine answers using the full Slack thread context, and send approved
answers through the configured channel webhook.

Slackdump archives are read-only source material. This skill does not use a
Slack browser session, Slack OAuth credentials, or the Slack Web API.

## Requirements

The wiki must have the `ingest-slack`, `slackdump`, `slackdump-source`, and
`slackdump-sqlite3` support bundle, a Slackdump SQLite archive under
`raw/Slack/`, and this user-managed configuration file:

`.llm-wiki/slack/send-slack.env`

The file must be mode `600` and contain the one Slack channel assigned to this
wiki and its incoming webhook:

```dotenv
SLACK_CHANNEL_ID=C0123456789
SLACK_CHANNEL_NAME=project-epiphan
SLACK_BOT_NAME=dobby
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Keep the webhook URL out of Git, chat messages, logs, command output, and
generated wiki pages. Never commit this file.

## Workflow

### 1. Discover and validate the archive

Use the existing Slackdump helper and read-only SQLite behavior. Discover the
database under `raw/Slack/`, validate its schema, and confirm that its
messages represent the configured channel.

Slackdump archive refresh is a separate user operation. If the user has added
new Slack messages, they must first run `slackdump resume` (optionally with
`-dedupe`) against the archive. This skill never fetches new Slack data.

Stop if configuration or the database is missing, the database contains an
ambiguous set of channels, or its channel does not match the configured ID or
name. Do not modify the SQLite database, WAL/SHM files, uploads, avatars, or
any other Slackdump archive content.

### 2. Find unanswered requests

Load canonical, deduplicated messages and identify messages addressed to the
configured bot through a real Slack user mention. Slack may store that mention
as `<@USER_ID>` while rendering it as `@dobby`. Resolve `SLACK_BOT_NAME`
against Slack usernames, display names, and real names, requiring exactly one
matching user. Do not treat ordinary text containing the bot name as a request.

Group each matching message with its full thread context, including parent and
replies. Resolve author and channel names when available.

Skip messages already recorded as successfully answered in
`.llm-wiki/slack/send-slack-manifest.jsonl`. Record only after the webhook
confirms successful delivery; failed or ambiguous sends remain eligible later.

### 3. Draft and preview answers

Prepare a concise answer for every unanswered candidate using the full thread
context. Present all candidates with channel, timestamp, author, relevant
thread text, and the exact proposed answer.

Ask which candidates to answer and obtain confirmation of the exact answer text
before sending. The initial request to check Slack is not confirmation for an
external write.

### 4. Send approved answers

For each approved candidate, send a JSON payload containing the answer text to
the configured webhook:

```bash
curl --fail-with-body --silent --show-error \
  -X POST \
  -H 'Content-type: application/json' \
  --data '{"text":"ANSWER TEXT"}' \
  "$SLACK_WEBHOOK_URL"
```

Construct JSON with a standard JSON encoder so quotes, newlines, Unicode,
Slack formatting, and backslashes are escaped correctly. Do not interpolate
untrusted answer text into shell source.

Treat a successful HTTP response as delivery confirmation. Do not retry an
ambiguous timeout automatically because Slack may already have accepted it.

### 5. Record successful delivery

After a successful send, append one JSONL record to the response manifest.
Identify the archive, channel, triggering message timestamp, thread timestamp
when present, answer identity, and send time. Never include the webhook URL.

If sending or manifest recording fails, report the failure and do not claim
that the answer was delivered or mark it successfully handled.

## Safety boundaries

- This is an explicit, on-demand workflow; it is not part of `/scan-raw`.
- Only the configured channel may be inspected or used for sending.
- Only real Slack user mentions targeting the configured bot trigger
  candidates; ordinary text containing the bot name does not.
- Every external send requires confirmation of the exact text.
- Send only candidates selected by the user.
- Never expose, print, persist, or commit webhook secrets.
- Never modify Slackdump archives or use Slack OAuth/browser-session credentials.
- Do not expand this skill to uploads, reactions, edits/deletes,
  administration, scheduling, or broad Slack search.

## Failure handling

Report actionable errors for missing, unreadable, malformed, or insecure
configuration; missing, invalid, locked, or ambiguous databases; channel
identity mismatch; malformed message data; webhook HTTP or network failure;
and manifest read/write failure. Do not include the webhook URL, request
headers, secret-bearing response payloads, or raw tracebacks in output.
