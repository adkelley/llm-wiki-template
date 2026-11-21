# ingest-youtube

This directory contains a skill for capturing YouTube transcripts into the LLM
wiki workflow.

## Goal

The intended flow is:

1. Run `/ingest-youtube` with a YouTube URL.
2. Use `scripts/wiki/youtube_transcript.py` to fetch metadata and English
   auto-captions with `yt-dlp`.
3. Clean the WebVTT captions into readable transcript text.
4. Save the transcript as a metadata-rich Markdown file in `raw/`.
5. Stop before wiki synthesis.
6. Run the normal ingest workflow later only if the user asks to ingest the
   created raw file.

## Requirements

Before running this skill, the user needs:

- `python3`
- `yt-dlp` installed and available on `PATH`
- network access to YouTube
- a video with captions or auto-generated captions in the selected language

Install `yt-dlp` using the official instructions for your operating system,
then verify:

```bash
yt-dlp --version
```

## Shared Utility

The skill uses:

```bash
python3 scripts/wiki/youtube_transcript.py "{VIDEO_URL}"
```

Common options:

```bash
python3 scripts/wiki/youtube_transcript.py \
  --title "Readable title override" \
  --lang en \
  --output-dir raw \
  "{VIDEO_URL}"
```

Clean an existing local `.vtt` file instead of downloading captions:

```bash
python3 scripts/wiki/youtube_transcript.py \
  subtitles.en.vtt \
  --title "Readable title" \
  --url "{VIDEO_URL}" \
  --published "YYYY-MM-DD"
```

## Raw Output

The generated file is named:

```text
raw/{YYYY-MM-DD-or-undated}-{slugified-title}-{video_id}.md
```

It includes:

- title
- source
- URL
- video ID
- published date
- capture timestamp
- cleaned transcript text

The script refuses to overwrite existing raw files.

## Important Behavior

This skill does not auto-ingest the transcript into `wiki/`.

The capture step creates raw source material only. Once the user asks to ingest
the created file, use the standard wiki ingest guard and wiki update workflow.
