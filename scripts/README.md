# Scripts

This directory contains setup and integration guides for the supported LLM workflows in this repository.

## Shared Wiki Utilities

Reusable, agent-independent wiki utilities should live under `scripts/wiki/`.
These scripts are intended to be called by generated agent instructions such as
`AGENT.md` and `CLAUDE.md`, and should work across macOS, Windows, and Linux
where possible.

The first shared utility is an ingest guard:

```text
scripts/wiki/ingest_guard.py
```

The ingest guard helps prevent users from accidentally ingesting duplicate
material. It records successful ingests in a local JSON Lines manifest:

```text
.llm-wiki/ingest-manifest.jsonl
```

Each manifest line is one JSON object. Current records include:

- `schema_version`
- `source_path`
- `size_bytes`
- `byte_sha256`
- `text_sha256` for plain-text files
- `ingested_at` for recorded ingests

The current workflow is:

1. compute a SHA-256 hash of the source file bytes
2. extract and normalize text, then compute a SHA-256 hash of the normalized text
3. compare both hashes against an ingestion manifest
4. stop or proceed based on whether a byte or normalized-text duplicate exists
5. record successful ingests in `.llm-wiki/ingest-manifest.jsonl`

### Ingest Guard Usage

Compute hashes for one file without reading or writing the manifest:

```bash
python3 scripts/wiki/ingest_guard.py hash raw/README.md
```

Check whether a candidate file matches a prior ingest:

```bash
python3 scripts/wiki/ingest_guard.py check raw/README.md
```

Append a successful ingest record. This refuses byte-identical and
normalized-text duplicates:

```bash
python3 scripts/wiki/ingest_guard.py record raw/README.md
```

Inspect `raw/` against the manifest without writing:

```bash
python3 scripts/wiki/ingest_guard.py audit
```

Backfill the manifest from files already present under `raw/`:

```bash
python3 scripts/wiki/ingest_guard.py index-existing
```

The default manifest and raw directory can be overridden for testing or custom
layouts:

```bash
python3 scripts/wiki/ingest_guard.py \
  --manifest /tmp/ingest-test.jsonl \
  --raw-dir raw \
  audit
```

Global options such as `--manifest` and `--raw-dir` must appear before the
subcommand.

The first stdlib-only implementation computes normalized text hashes only for
plain-text file suffixes such as `.md`, `.txt`, `.csv`, `.json`, `.jsonl`,
`.html`, and `.htm`. Binary or container formats such as `.pdf`, `.docx`, and
`.pptx` currently receive only a byte hash. Future versions may add explicit
text extraction for those formats.

The generated `scripts/codex/AGENT.md` and `scripts/claude/CLAUDE.md` templates
should explicitly instruct agents to run this guard before ingesting raw
material once the utility exists.

## YouTube Transcript Capture

The YouTube transcript utility downloads auto-generated captions with `yt-dlp`,
cleans the WebVTT text, and writes a raw Markdown source file:

```text
scripts/wiki/youtube_transcript.py
```

It depends on `yt-dlp` being installed separately. Install `yt-dlp` using the
official instructions for your operating system, then confirm it works:

```bash
yt-dlp --version
```

Basic usage:

```bash
python3 scripts/wiki/youtube_transcript.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

If the video title should be overridden:

```bash
python3 scripts/wiki/youtube_transcript.py \
  --title "Readable title override" \
  "https://www.youtube.com/watch?v=VIDEO_ID"
```

The utility can also clean an existing local `.vtt` file. In local-file mode,
pass source metadata explicitly when available:

```bash
python3 scripts/wiki/youtube_transcript.py \
  subtitles.en.vtt \
  --title "Readable title" \
  --url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --published "YYYY-MM-DD"
```

The generated file is written under `raw/` by default:

```text
raw/{YYYY-MM-DD-or-undated}-{slugified-title}-{video_id}.md
```

After creation, run the ingest guard before asking an agent to ingest the raw
transcript:

```bash
python3 scripts/wiki/ingest_guard.py check raw/{filename}.md
```

## Managed Template Hashes

The setup scripts use a separate template guard to track hashes for installed
agent instruction templates:

```text
scripts/wiki/template_guard.py
```

```text
.llm-wiki/template-manifest.jsonl
```

This lets `scripts/codex/setup.sh` and `scripts/claude/setup.sh` distinguish an
old untouched template from a user-edited `AGENT.md` or `CLAUDE.md`.

Check the status of an installed template:

```bash
python3 scripts/wiki/template_guard.py status \
  --template scripts/codex/AGENT.md \
  --target AGENT.md
```

Record the template hash after copying or updating a managed template:

```bash
python3 scripts/wiki/template_guard.py record \
  --template scripts/codex/AGENT.md \
  --target AGENT.md
```

`status` returns one of these statuses:

- `missing` - the target file does not exist and can be created
- `replace` - the target still matches the last installed template and can be
  updated
- `record` - the target already matches the current template but needs a
  manifest entry
- `current` - the target matches the current template and manifest
- `preserve` - the target appears to have local changes and should not be
  overwritten automatically

## Claude Code

If you are using Claude Code, run:

```bash
scripts/claude/setup.sh
```

This setup script configures Claude Code for the repository and can optionally install Claude-specific skills.

For more details, see `scripts/claude/README.md`.

## Codex

If you are using Codex, run:

```bash
scripts/codex/setup.sh
```

This setup script configures Codex for the repository and can optionally install additional skills.

For more details, see `scripts/codex/README.md`.

## Obsidian

If you are using [Obsidian](https://obsidian.md/) as your IDE, you may also want to:

- update `.obsidian/app.json` for your local vault preferences
- install Obsidian-related skills that use Obsidian's native CLI

These skills can provide programmatic access to Obsidian's internal cache and metadata, which can be more reliable than plain filesystem search for some workflows.

For background, see the [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack?tab=readme-ov-file#8-the-obsidian-cli-advantage).

For installation steps, see `scripts/obsidian/README.md`.

## Optional Skills

Shared optional skills are located under `scripts/optional-skills/`.

Some setup scripts may copy selected skills from this repository into the tool-specific skills directory during installation.
