---
name: ingest-youtube
description: |
  YouTube transcript capture skill for LLM-wiki users. Trigger whenever the
  user types "/ingest-youtube", says "download YouTube transcript",
  "capture this YouTube video", "transcribe this YouTube video", or asks to
  turn a YouTube URL into raw wiki source material. Uses the shared
  `scripts/wiki/youtube_transcript.py` utility, which depends on a locally
  installed `yt-dlp`, to download English auto-captions, clean WebVTT text,
  and write a metadata-rich Markdown file into raw/. Stops after raw file
  creation; the normal wiki ingest workflow runs only when the user asks to
  ingest the created raw file.
---

# /ingest-youtube - YouTube Transcript Capture

## Purpose

Download a YouTube video's auto-generated captions, clean them into readable
transcript text, and save the result as immutable raw source material for the
LLM wiki.

This skill is for capture, not synthesis. It creates a `raw/*.md` source file
and then stops. The normal wiki ingest workflow should run only after the user
asks to ingest that file.

---

## Requirements

This skill depends on:

- `python3`
- `yt-dlp` available on `PATH`
- network access to YouTube
- a YouTube video with subtitles or auto-generated captions in the requested
  language

If `yt-dlp` is missing, tell the user to install it using the official
instructions for their operating system, then verify:

```bash
yt-dlp --version
```

---

## Step 1 - Get the Video URL

If the user did not provide a YouTube URL, ask for it.

If the user provided a preferred title, pass it with `--title`. Otherwise, rely
on `yt-dlp` metadata extraction.

Do not require the user to provide a title in v1; the shared script can derive
one from video metadata.

---

## Step 2 - Create the Raw Transcript

From the wiki root, run:

```bash
python3 scripts/wiki/youtube_transcript.py "{VIDEO_URL}"
```

If the user supplied a title override, run:

```bash
python3 scripts/wiki/youtube_transcript.py \
  --title "{VIDEO_TITLE}" \
  "{VIDEO_URL}"
```

The script writes a file named like:

```text
raw/{YYYY-MM-DD-or-undated}-{slugified-title}-{video_id}.md
```

It refuses to overwrite existing files.

---

## Step 3 - Report the Result

After successful capture, report:

- the created raw file path
- that the transcript has not yet been ingested into `wiki/`
- the ingest guard command to run before ingesting

Example:

```text
Created raw transcript: raw/2026-05-03-example-title-abc123.md
Not ingested yet. To continue, ask me to ingest that raw file.
```

---

## Step 4 - Ingest Only on Request

If the user explicitly asks to ingest the created transcript, run the standard
wiki ingest workflow for that raw file:

1. Run `python3 scripts/wiki/ingest_guard.py check raw/{filename}.md`
2. If the guard reports a duplicate, stop and report the matching source.
3. Read the raw transcript.
4. Present 3-5 key takeaways.
5. Create/update the appropriate wiki source summary, concept pages, entity
   pages, `wiki/index.md`, and `wiki/log.md`.
6. Record the successful ingest with
   `python3 scripts/wiki/ingest_guard.py record raw/{filename}.md`.

Do not silently ingest the transcript immediately after capture.

---

## Failure Modes

- **Missing `yt-dlp`:** tell the user to install it using the official
  instructions for their operating system.
- **No captions found:** report that the video may not have captions in the
  requested language.
- **Network or YouTube error:** show the `yt-dlp` error summary and stop.
- **Existing raw file:** do not overwrite; report the existing path.
- **Empty cleaned transcript:** stop and report that captions were downloaded
  but no transcript text remained after cleaning.

Do not write to `wiki/` during failure handling.

---

## Notes

Use `--lang` for non-English captions:

```bash
python3 scripts/wiki/youtube_transcript.py --lang es "{VIDEO_URL}"
```

To clean an existing local `.vtt` file instead of downloading from YouTube,
pass the file path and source metadata:

```bash
python3 scripts/wiki/youtube_transcript.py \
  "{SUBTITLES_FILE}.vtt" \
  --title "{VIDEO_TITLE}" \
  --url "{VIDEO_URL}" \
  --published "YYYY-MM-DD"
```

The raw transcript should preserve the downloaded transcript text as source
material. Do not paraphrase or correct it in `raw/`.
