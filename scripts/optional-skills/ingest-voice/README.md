# ingest-voice

This directory contains a skill for ingesting JustRecord voice memos into
the LLM wiki workflow.

## Platform

This skill is intended for macOS only.

It depends on:

- the macOS iCloud Drive filesystem layout under `~/Library/Mobile Documents/`
- a local Python virtual environment
- `mlx-whisper`, which is intended here for local execution on a Mac

## Goal

The intended flow is:

1. Sync `.m4a` voice memos from JustRecord into iCloud Drive.
2. Detect new files in the JustRecord iCloud directory.
3. Transcribe them with a repo-local `mlx-whisper` install.
4. Save relevant transcripts into `raw/transcripts/`.
5. Run the normal wiki ingest workflow.
6. Record processed filenames so the same memo is not handled twice.

## Prerequisites

Before running this skill, the user needs:

- macOS
- JustRecord installed on iPhone.
- JustRecord iCloud sync enabled.
- iCloud Drive enabled on the Mac.
- `python3` installed.
- Standard shell tools available: `find`, `sort`, `head`, `git`.
- This repository checked out locally.

## Local Python Environment

This skill should use a repo-local Python environment rather than a global
install.

Create the virtual environment from the repository root:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install `mlx-whisper` into the local environment:

```bash
pip install mlx-whisper
```

Verify the package is available in the local environment:

```bash
./.venv/bin/mlx_whisper --help
```

## Recommended Invocation Model

Do not rely on whichever `python3` or `pip` happens to be active globally.
Prefer calling the virtualenv binaries explicitly.

Example transcription command:

```bash
./.venv/bin/mlx_whisper "{filepath}" \
  --model mlx-community/whisper-large-v3-mlx \
  --output-format txt
```

`mlx-whisper` is installed as a console script. Do not use
`python -m mlx_whisper`; that package does not expose `mlx_whisper.__main__`.

If the skill checks whether `mlx-whisper` is installed, it should also use the
same local environment:

```bash
./.venv/bin/python -m pip show mlx-whisper
```

This avoids a mismatch where `pip show` succeeds in one Python environment but
`python3 -m mlx_whisper` runs in another.

## First Run Behavior

The first transcription run can be slow because `mlx-whisper` may need to
download the selected model before transcription starts.

Expected behavior on first run:

- The command pauses while model files download.
- The model is cached locally after the download completes.
- Later runs with the same model should be faster.

By default, the model cache is typically stored under:

```text
~/.cache/huggingface/hub/
```

If you delete the cached model directory, the next run will download it again.

## Config

The skill expects a config file that stores the JustRecord directory and the
speaker name.

Before running the skill, set these two values in `config.md`:

- `justrecord_dir`
- `speaker_name`

Recommended value format:

```yaml
justrecord_dir: "/Users/your-username/Library/Mobile Documents/iCloud~com~vendor~app/Documents"
speaker_name: "Your Name"
```

Notes:

- Use plain YAML-style strings, not Markdown backticks.
- Use a concrete absolute path, not shell syntax like `$HOME`.
- Quote the path because it contains spaces.
- Do not use shell escaping like `Mobile\ Documents` in the config value.
- The config should contain the real path the agent can read directly.

## Testing the JustRecord Directory

In the terminal, assign the path to a shell variable and then run `find`:

```bash
justrecord_dir="$HOME/Library/Mobile Documents/iCloud~com~openplanetsoftware~just-press-record/Documents"
find "$justrecord_dir" -name "*.m4a" | sort
```

Important:

- Use `$justrecord_dir`, not `{justrecord_dir}`.
- `{justrecord_dir}` is a placeholder for documentation, not shell syntax.
- Quote the variable expansion because the path contains spaces.

## Processed Manifest

The processed manifest can be a plain newline-delimited text file:

```text
20260423-14-32-00.m4a
20260423-16-15-44.m4a
meeting-idea-2026-04-23.m4a
```

Recommended behavior:

- One bare filename per line.
- No paths.
- No quotes.
- Append entries after each file is evaluated.
- Treat the file as the deduplication source of truth.

## What the User Must Do Before Running the Skill

Before the first run, the user should:

1. Install and configure JustRecord with iCloud sync.
2. Confirm `.m4a` files are appearing in the JustRecord iCloud directory.
3. Create the repo-local virtualenv with `python3 -m venv .venv`.
4. Install `mlx-whisper` into `.venv`.
5. Create or update the config file with the correct JustRecord path and
   speaker name.
6. Create an empty `processed.txt` file if the manifest does not exist yet.

## Optional Fallback

The skill also mentions the OpenAI Whisper API as a fallback, but that is
not required if local transcription via `mlx-whisper` is set up correctly.
