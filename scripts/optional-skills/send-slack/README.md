# send-slack

Answer Slack messages addressed to the configured bot by searching this LLM
Wiki's Slackdump archive and posting approved answers through the configured
Slack channel webhook.

This skill is scoped to one Slack channel per wiki. It does not use Slack
browser-session credentials, Slack OAuth tokens, or the Slack Web API.

## Requirements

- Python 3.10 or newer;
- the `ingest-slack`, `slackdump`, `slackdump-source`, and `slackdump-sqlite3`
  skills;
- a read-only Slackdump SQLite archive under `raw/Slack/`; and
- a mode-`600` configuration file at `.llm-wiki/slack/send-slack.env`.

Example configuration:

```dotenv
SLACK_CHANNEL_ID=C0123456789
SLACK_CHANNEL_NAME=project-epiphan
SLACK_BOT_NAME=my-bot
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

The user is responsible for creating and filling in this file. Skill
installation may create an empty starter template when the file does not yet
exist, but it never supplies a webhook URL or overwrites an existing file.

`SLACK_BOT_NAME` may optionally include a leading `@`. The skill resolves the
name case-insensitively against Slack usernames, display names, and real names
in the Slackdump archive and requires exactly one matching user.

The webhook URL is a secret. Keep the configuration file out of Git and do
not paste the URL into chat, logs, source pages, or shell history.

## Usage

Ask the LLM Wiki to check or answer Slack messages addressed to the configured
bot. The
workflow will:

1. locate and validate the Slackdump SQLite archive;
2. confirm that it represents the configured channel;
3. resolve `SLACK_BOT_NAME` to exactly one Slack user and find canonical
   messages containing a real mention targeting that user, such as Slack's
   stored `<@USER_ID>` form;
4. include the full parent thread and replies as context;
5. omit messages already recorded as successfully answered;
6. show candidates and exact proposed answers for review; and
7. send only user-selected, explicitly confirmed answers through the webhook.

After Slackdump has refreshed the archive, preview candidates explicitly with:

```bash
python3 scripts/optional-skills/send-slack/slack_send.py candidates \
  --database .llm-wiki/slack/slackdump_YYYYMMDD_HHMMSS/slackdump.sqlite
```

Refresh the archive separately with Slackdump, for example:

```bash
slackdump resume .llm-wiki/slack/slackdump_YYYYMMDD_HHMMSS
```

The responder does not run Slackdump or fetch new Slack messages itself.

The webhook request is equivalent to:

```bash
curl -X POST \
  -H 'Content-type: application/json' \
  --data '{"text":"Hello"}' \
  "$SLACK_WEBHOOK_URL"
```

The implementation must use a JSON encoder for the actual payload. Do not
construct JSON by unsafe shell interpolation.

## Response tracking

Successful responses are tracked at
`.llm-wiki/slack/send-slack-manifest.jsonl`.

Only a confirmed successful webhook delivery is recorded. A failed or
ambiguous send remains eligible for later investigation or retry. Do not
automatically retry an ambiguous timeout because the message may already have
been accepted by Slack.

The manifest is mutable LLM Wiki bookkeeping. Slackdump archives under
`raw/Slack/` remain immutable and must not be edited, deleted, or deduplicated
by this workflow.

## Safety boundaries

- The workflow is explicit and on demand; it is not part of `/scan-raw`.
- It reads only the one channel configured for this wiki.
- It matches real Slack user mentions targeting the configured bot, not
  incidental text containing the bot name.
- Every external post requires confirmation of the exact answer text.
- It does not support uploads, reactions, edits, deletes, administration,
  scheduling, or broad multi-channel messaging.

## Troubleshooting

Stop with a clear error if the configuration is missing, malformed, or more
permissive than mode `600`; the Slackdump archive cannot be found or opened
read-only; the archive channel does not match the configured channel; the
webhook rejects the request or cannot be reached; or the response manifest
cannot be read or written.

No matching messages means there is currently nothing new to answer; it is not
an error.
