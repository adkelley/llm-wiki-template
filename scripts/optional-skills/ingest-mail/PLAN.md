# Apple Mail Ingest Skill

## Summary

Add a new optional skill, `ingest-mail`, for reviewing Apple Mail messages from
configured mail accounts and mailboxes, selecting wiki-relevant emails, saving
approved messages as immutable raw markdown sources, and running the standard
wiki ingest workflow.

## Key Changes

- Create a new optional skill directory:
  `scripts/optional-skills/ingest-mail/`
- Add:
  - `SKILL.md` with the executable agent workflow
  - `README.md` with user-facing setup and troubleshooting notes
  - `PLAN.md` containing this development plan
- Use the existing setup flow. No changes are needed to
  `scripts/codex/setup.sh` or `scripts/claude/setup.sh`.

## Configuration

The installed skill uses local state files in its own directory:

```text
config.md
processed.txt
```

Recommended `config.md`:

```yaml
lookback_days: 14
raw_output_dir: "raw/transcripts"
accounts:
  - "Google"
mailboxes:
  - "Inbox"
  - "Archive"
wiki: "Your Wiki Name"
```

Behavior:

- `accounts` limits scans to named Apple Mail accounts.
- `mailboxes` limits scans within those accounts.
- Account matching uses Apple Mail account display names.
- The skill documents setup/debug commands to list available accounts and
  mailboxes.

## Skill Behavior

- Trigger on `/ingest-mail`, "ingest email", "review Apple Mail", or similar
  requests.
- Preflight Apple Mail automation:

  ```bash
  osascript -e 'tell application "Mail" to count accounts'
  ```

- If preflight fails, stop without updating `processed.txt`.
- Scan only configured accounts and mailboxes.
- Filter candidates by `lookback_days`.
- Extract:
  - message id
  - subject
  - sender
  - recipients when available
  - sent and/or received date
  - mailbox
  - account
  - read/flagged status when available
  - full plain text body or raw source-derived body
- Evaluate candidates for wiki relevance.
- Present one batch review before writing files:

  ```text
  Evaluation results:
    [yes] Subject - relevant: reason
    [no]  Subject - skipped: reason
    [?]   Subject - ambiguous: needs routing confirmation
  ```

- Require batch approval before creating raw files or updating the wiki.

## Raw Output And Ingest

For each approved relevant email, create:

```text
{raw_output_dir}/{YYYY-MM-DD}-email-{slug}-{short_message_id}.md
```

Raw file format:

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

Rules:

- Save full plain text email content in `raw/`.
- Do not include attachments in v1.
- Do not overwrite existing raw files.
- Use message id plus date/version data for dedupe, not subject.
- Run the standard wiki ingest workflow after raw files are created.

Suggested log entry:

```text
## [YYYY-MM-DD] ingest | {subject} (email)
Source: raw/transcripts/{filename}.md
Original message ID: {message_id}
Account: {account}
Mailbox: {mailbox}
Pages created: ...
Pages updated: ...
Contradictions flagged: ...
Notes: {topic summary}
```

## Manifest

Use `processed.txt` as an append-only manifest.

Format:

```text
{message_id}\t{date_received_or_sent_text}
```

Rules:

- Record every evaluated email version, including skipped emails.
- Latest line for a message id wins.
- Manual removal of a line allows reprocessing.
- Do not update the manifest if Apple Mail preflight or scan fails.

## Test Plan

- Verify `SKILL.md` frontmatter is valid.
- Confirm the new skill is discoverable by the existing optional-skill setup
  scripts.
- Review AppleScript examples for:
  - listing accounts and mailboxes
  - counting messages through `mailboxes of account`
  - filtering mailboxes by account
  - guarded per-message extraction
- Manual macOS tests:
  - missing config stops with setup instructions
  - Mail automation failure does not update `processed.txt`
  - account/mailbox filtering limits candidates correctly
  - batch approval gates raw writes
  - skipped messages are recorded
  - approved messages become raw markdown
  - standard wiki ingest updates `wiki/index.md` and `wiki/log.md`

## Assumptions

- v1 supports macOS Apple Mail only.
- v1 uses `osascript`, not direct Mail database access.
- Configured Apple Mail account names are sufficient for account scoping.
- Attachments, HTML preservation, background scheduling, and Mail rule/tag
  integration are out of scope for v1.
