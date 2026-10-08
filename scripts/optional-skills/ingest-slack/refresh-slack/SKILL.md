---
name: refresh-slack
description: Refresh a Slackdump archive before Slack ingestion or outbound Slack work.
---

# /refresh-slack - Refresh Slackdump Archives

This skill refreshes one or more Slackdump archives before another Slack
workflow reads or sends against them.

Use `refresh_slack.sh` with one or more Slackdump archive directories. With no
arguments, it discovers archives below `raw/Slack/` that contain
`slackdump.sqlite`. The script runs both refresh phases for each selected
archive:

1. `slackdump resume <archive>`
2. `slackdump resume --dedupe <archive>`

The script streams command output for immediate agent feedback and retains a
timestamped log plus a machine-readable `latest.json` summary for each archive
under `.llm-wiki/slack/<archive-directory-name>/refresh/`.

Do not continue to `ingest-slack` or `send-slack` when either phase fails.

The script returns a nonzero status if any archive fails. Do not continue to
`ingest-slack` or `send-slack` when refresh fails.
