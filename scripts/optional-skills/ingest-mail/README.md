# ingest-mail

Himalaya-backed mail ingest for LLM Wiki.

This optional skill scans a user-authorized mailbox with the
[`himalaya`](https://github.com/pimalaya/himalaya) CLI, returns candidate email
messages for wiki relevance review, and records evaluated envelope IDs so the
same messages are not reviewed repeatedly.

The skill is read-only with respect to mail. It uses Himalaya commands for
account listing, folder listing, envelope listing, and preview-only message
reads. It must not send, delete, move, flag, mark read, or download
attachments.

## Requirements

- Himalaya installed and available on `PATH`
- Himalaya configured with at least one readable account
- A `config.toml` file in the installed skill directory
- Python 3.11+ for `tomllib`

Install Himalaya from the upstream project:

- <https://github.com/pimalaya/himalaya>

Note, as mentioned in the Himalaya installation instructions, Homebrew installs a prebuilt package that 
cannot customize Cargo features. If your account setup requires optional Himalaya features such as OAuth 2.0 or
keyring support, use an installation method that supports the needed feature
set, such as Cargo, Nix, or a source build.

## Runtime Files

In a Codex install, runtime files live in:

```text
./skills/ingest-mail/
```

In a Claude install, runtime files live in:

```text
.claude/skills/ingest-mail/
```

The user-managed runtime files are:

```text
config.toml
state.jsonl
last_scan.txt
```

Do not commit real mailbox config or scan state to the template repository.

## Setup

Copy the example config in the installed skill directory:

```bash
cp config.example.toml config.toml
```

Edit `config.toml`:

```toml
lookback_days = 14
raw_output_dir = "raw/"
accounts = ["personal"]
folders = ["INBOX"]
max_messages_per_folder = 25
max_thread_context_messages = 5
wiki = "your-wiki-name"
```

`accounts` and `folders` must match Himalaya names exactly.
`lookback_days` is the maximum scan window. `scan` combines it with
`last_scan.txt` to compute `scan_window_days`.

Useful discovery commands:

```bash
himalaya account list --output json
himalaya folder list --account personal --output json
```

## Common Commands

Run preflight:

```bash
python3 scan_mail.py preflight --skill-dir .
```

Preflight verifies that Himalaya is available, the configured account names
exist, and the configured folders can be listed without reading message bodies.

Scan envelope candidates only:

```bash
python3 scan_mail.py scan --skill-dir . --limit 25
```

The scan output includes `candidate_count` / `candidates` for new messages,
`scan_window_days`, `thread_context` envelope context on each candidate, and
`excluded_count` / `excluded` for deterministic skips such as messages already
recorded in `state.jsonl`.

The `scan` command applies the computed window through Himalaya's query syntax:

```text
after YYYY-MM-DD order by date desc
```

`state.jsonl` remains the durable dedupe layer. The date window is an
optimization.

List envelopes for diagnostics without applying the scan window:

```bash
python3 scan_mail.py envelope-list --skill-dir .
```

Thread context in v1 is subject-based envelope context. It strips common
reply/forward prefixes and is capped by `max_thread_context_messages`; it is
not full header-based thread reconstruction.

Scan candidates with preview-only message bodies:

```bash
python3 scan_mail.py scan --skill-dir . --include-messages --limit 10
```

Generate a fail-closed decisions template:

```bash
python3 scan_mail.py decisions-template --skill-dir . --limit 10
```

The template contains one row per new candidate and defaults every `decision`
to `"ambiguous"`.

Read one message without marking it seen:

```bash
python3 scan_mail.py message-read --skill-dir . --message-id 123
```

Export approved messages to raw files:

```bash
python3 scan_mail.py export-approved --skill-dir . --decisions /path/to/decisions.json
```

Raw export writes the approved message body plus a labeled thread-context
section. In v1, that context is related envelope metadata only: envelope IDs,
subjects, senders, recipients, and dates.

Finalize evaluated decisions:

```bash
python3 scan_mail.py finalize --skill-dir . --decisions /path/to/decisions.json
```

Decision files are normal JSON arrays:

```json
[
  {
    "account": "personal",
    "folder": "INBOX",
    "envelope_id": "123",
    "decision": "no"
  }
]
```

`export-approved` writes raw files only for `decision: "yes"`.
`finalize` appends every supplied decision to `state.jsonl` and writes
`last_scan.txt`. In the normal skill workflow, run `export-approved`, ingest the
raw files into the wiki, and only then run `finalize`.

Exit-code categories:

- `2`: config or CLI argument error
- `3`: Himalaya command error
- `4`: Himalaya JSON parse error
- `5`: state or decisions-file error
- `6`: raw-file write error

## Development

Run tests from the repository root:

```bash
python3 -m unittest discover scripts/optional-skills/ingest-mail/tests
python3 -m py_compile scripts/optional-skills/ingest-mail/scan_mail.py
```
