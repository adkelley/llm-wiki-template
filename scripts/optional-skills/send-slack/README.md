# send-slack

Send a Slack message from an LLM Wiki using the existing Slackdump browser
session credentials. This optional skill is intentionally small: it resolves a
channel, sends one message, and can optionally reply in an existing thread.

It does not create Slack apps or use the Python Slack SDK. Slackdump's
`xoxc`/`xoxd` browser credentials are not the OAuth credentials expected by
that SDK, so the companion Python adapter uses a narrow HTTP client instead.

## Requirements

- Python 3.10 or newer
- Slackdump 4.4.4 or a compatible installation
- A readable credentials file at:

  ```text
  ~/.cache/slackdump/slackdump_garibaldi.env
  ```

  The file must define `SLACK_TOKEN` and `SLACK_COOKIE`, and should be mode
  `600`.

The adapter reads the credentials file itself. Never put either credential in a
command argument, shell history, log, exception, or output file.

## Usage

From the repository root, preview a send with no Slack write:

```bash
python3 scripts/optional-skills/send-slack/slack_send.py \
  --channel "#general" \
  --message "Hello from the LLM Wiki" \
  --dry-run
```

After the user has explicitly confirmed the exact channel and message, perform
the send with `--confirm`:

```bash
python3 scripts/optional-skills/send-slack/slack_send.py \
  --channel "#general" \
  --message "Hello from the LLM Wiki" \
  --confirm
```

Reply to an existing thread by adding its Slack timestamp:

```bash
python3 scripts/optional-skills/send-slack/slack_send.py \
  --channel "C0123456789" \
  --message "Following up here" \
  --thread-ts "1712345678.123456" \
  --confirm
```

The command emits one sanitized structured JSON object on stdout. A dry-run
preview includes the resolved channel ID/name, exact message, optional thread
timestamp, and `dry_run: true`:

```json
{
  "ok": true,
  "operation": "send_message",
  "dry_run": true,
  "channel_id": "C0123456789",
  "channel_name": "general",
  "message": "Hello from the LLM Wiki",
  "thread_ts": null
}
```

A successful confirmed send additionally includes `message_ts` and sets
`dry_run` to `false`. Output must never include `SLACK_TOKEN`,
`SLACK_COOKIE`, raw authorization headers, cookies, or full exception
tracebacks.

The command rejects empty or whitespace-only channel and message values. A
thread timestamp must use Slack's format, such as `1712345678.123456`.

Invalid command-line input returns exit code `2`. Credential, channel, Slack
API, and network failures return exit code `1`. Failures use sanitized error
codes including `invalid_arguments`, `credentials_error`, `channel_error`,
`slack_api_error`, and `network_error`.

## Safety boundaries

- Dry-run is the default behavior unless `--confirm` is supplied.
- A real send requires both an explicit user confirmation in the conversation
  and the command's `--confirm` flag.
- Resolve the channel before attempting to send. Do not guess when a name maps
  to multiple channels.
- Do not modify Slackdump archives or files under `~/.cache/slackdump`.
- This MVP does not upload files, add reactions, delete or edit messages,
  schedule messages, administer workspaces, or search broad message history.

## Testing

Run the unit tests from the repository root:

```bash
python3 -m unittest discover -s scripts/optional-skills/send-slack/tests
```

Tests must mock HTTP requests and must not contact Slack or read the real
credentials file.
