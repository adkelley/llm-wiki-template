---
name: ingest-voice
description: |
  Voice memo ingest skill for LLM-wiki users. Trigger whenever the user
  types "/ingest-voice", says "process my voice memos", "transcribe my
  recordings", "ingest audio", or asks to pull in new JustPressRecord memos.
  Scans the JustPressRecord iCloud directory for unprocessed .m4a files,
  transcribes each using mlx-whisper (local) or OpenAI Whisper API
  (fallback), evaluates wiki relevance, saves qualifying transcripts to
  raw/, and runs the standard wiki ingest workflow. Marks all
  evaluated files in a manifest so they are not re-processed on future
  runs. Updates wiki/log.md on completion.
  Always read config.md and processed.txt before scanning. If config.md
  does not exist, run first-time setup to discover the JustPressRecord path.
---

# /ingest-voice — Voice Memo Ingest

## Purpose

Scan the JustPressRecord iCloud directory for new voice memos, transcribe them
with a local or API-backed Whisper model, evaluate each transcript for wiki
relevance, and feed qualifying transcripts into the standard wiki ingest
workflow. Marks all evaluated files so they are not re-processed on future
runs.

This skill is the audio equivalent of dropping a file into raw/ and running
`ingest` — it handles the transcription and routing so the only required
action is to speak.

This skill is the wiki-local implementation of the Event Watcher / Router
concept in [[wiki-orchestration-architecture]]. It evaluates relevance
against *this wiki's domain only* — multi-wiki routing is a future concern
handled at the supervisor agent layer.

---

## Configuration Files

This skill requires two files in its own directory. The exact path depends on
how the skill is installed:

- Codex repo-local install:
  - `./skills/ingest-voice/config.md` — JustPressRecord path and speaker name
  - `./skills/ingest-voice/processed.txt` — append-only manifest of evaluated filenames
- Claude Code-style install:
  - `.claude/skills/ingest-voice/config.md` — JustPressRecord path and speaker name
  - `.claude/skills/ingest-voice/processed.txt` — append-only manifest of evaluated filenames

If either is missing, run first-time setup (Step 1).

---

## Step 1 — Read Config and Manifest (or First-Time Setup)

### If config.md exists:

Read it and extract:
- `justpressrecord_dir` — absolute path to the JustPressRecord iCloud directory
- `speaker_name` — used in transcript headers (default: Alex Kelley)

Read `processed.txt`. If it doesn't exist, treat it as empty.

### If config.md does not exist (first run):

Run a scan to find .m4a files in iCloud:

```bash
find "$HOME/Library/Mobile Documents" -maxdepth 6 -name "*.m4a" 2>/dev/null | head -20
```

Show the results to the user and ask them to confirm the correct JustPressRecord
directory. A typical path looks like:

```
/Users/{user}/Library/Mobile Documents/iCloud~com~{developer}~JustPressRecord/Documents/
```

Once confirmed, write `config.md` in the skill's own directory
(`./skills/ingest-voice/` or `.claude/skills/ingest-voice/`, depending on
the installation):

```
# ingest-voice config

justpressrecord_dir: /Users/alexkelley/Library/Mobile\ Documents/iCloud~com~openplanetsoftware~just-press-record/Documents 
speaker_name: Alex Kelley
wiki: llm-wiki-research
```

Create an empty `processed.txt` in that same skill directory.

Confirm setup is complete, then continue to Step 2.

---

## Step 2 — Scan for New Audio Files

List all .m4a files in the JustPressRecord directory:

```bash
find "{justpressrecord_dir}" -name "*.m4a" | sort
```

Load `processed.txt` and subtract the already-processed filenames. The
result is the **new files list**.

If the new files list is empty:

```
No new voice memos found in {justpressrecord_dir}.
Manifest: {N} files previously processed.
```

Stop here.

If new files exist, report them before proceeding:

```
Found {N} new voice memo(s):
  - {filename1}
  - {filename2}
Proceeding to transcribe...
```

---

## Step 3 — Transcribe Each File

Use auto-detection to select the transcription method.

### Check 1: mlx-whisper 

```bash
mlx_whisper --help
```

If installed, transcribe:

```bash
mlx_whisper "{filepath}" \
  --model mlx-community/whisper-large-v3-mlx \
  --output-format txt
```

Read the resulting `.txt` file for the transcript text.

Note: the first run may be slow because the selected model may need to be
downloaded and cached before transcription begins.

### Check 2: OpenAI Whisper API (fallback)

If mlx-whisper is not installed and `$OPENAI_API_KEY` is set:

```bash
curl https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file="@{filepath}" \
  -F model="whisper-1"
```

Parse the JSON response `text` field for the transcript.

### If neither method is available:

To use local transcription (recommended for Apple Silicon Mac):
```bash
uv tool install mlx-whisper
```

To use the OpenAI API:
  export OPENAI_API_KEY=sk-...
  (Update config.md transcription_method to: openai-api)

Run /ingest-voice again after setup.
```

Stop without updating processed.txt — unprocessed files will be retried
on the next run.

---

## Step 4 — Evaluate Each Transcript for Wiki Relevance

For each transcript, answer two questions.

**Q1: Is this wiki-relevant?**

Relevant if it contains any of:
- A hypothesis, observation, or claim about any topic in `wiki/concepts/`
  or `wiki/entities/`
- A design idea, product concept, or open question the user wants to track
- A reference to a person, company, or product already in the wiki
- Anything framed as "I want to remember this" or "note to self"

Not relevant if it is:
- A grocery list, scheduling note, or logistical reminder
- Personal content unrelated to this wiki's domain
- Under ~20 meaningful words

**Q2: Which wiki?**

Currently: this wiki only. Route all relevant memos here.

Future hook: when cross-wiki federation is implemented, evaluate memo
content against each wiki's domain and route accordingly. The `wiki:`
field in config.md anticipates this.

Show the evaluation summary before proceeding:

```
Evaluation results:
  ✓ {filename1} — relevant: {one-sentence reason}
  ✗ {filename2} — skipped: logistical content
```

If any routing decision is ambiguous, show the transcript and ask — never
silently skip a memo the user might want ingested.

---

## Step 5 — Save Transcripts and Run Ingest

For each memo marked relevant:

### 5a. Write the raw transcript

Create `raw/{stem}.md` where `{stem}` is the audio filename
without extension (e.g., `20260423-14-32-00.m4a` becomes
`20260423-14-32-00.md`).

Format:

```
Speaker: {speaker_name}
Date: {YYYY-MM-DD derived from filename or file mtime}
Source: {original filename}
Transcription method: {mlx-whisper model name or openai-api}

{verbatim transcript — no editing, no paraphrasing}
```

Do not correct the transcript. Do not paraphrase. Raw transcripts in
`raw/` are immutable once written.

### 5b. Run the standard ingest workflow

Per CLAUDE.md, the ingest workflow for `raw/{stem}.md`:

1. Read the transcript
2. Present 3–5 key takeaways to the user
3. Create `wiki/sources/summary-{slug}.md`
4. Update `wiki/index.md`
5. Update all relevant concept and entity pages
6. Flag any contradictions with existing pages
7. Create new concept/entity pages if introduced
8. Append to `wiki/log.md`

Log entry format for voice memos:

```
## [YYYY-MM-DD] ingest | {first meaningful phrase} (voice memo)
Source: raw/{stem}.md
Original audio: {original filename}
Transcription: {method and model}
Pages created: ...
Pages updated: ...
Contradictions flagged: ...
Notes: {topic summary}
```

---

## Step 6 — Update the Processed Manifest

After all files are evaluated (whether ingested or skipped), append their
bare filenames to `processed.txt` in the skill's own directory:

```
20260423-14-32-00.m4a
20260423-16-15-44.m4a
```

One filename per line, no path, no quotes. Skipped files are recorded too
— if the user wants to force re-evaluation, they remove the line manually.

---

## Step 7 — Commit

Per CLAUDE.md git procedure:

```bash
git add raw/ wiki/
```

Do not stage `.claude/`. Do not push.

Commit message format:

```
ingest: voice memo(s) {stem1}, {stem2}

Co-Authored-By: {active_llm_model_and_effort} <{llm_company_email}>
```

Use the **actual LLM identity for the current session**, not a fixed placeholder.
Examples:

```text
Co-Authored-By: gpt-5.4 medium <noreply@openai.com>
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

If the current session exposes both model and reasoning effort, include both
in the co-author name (`gpt-5.4 medium`). If only the model name is available,
use just the model name. The email should be the noreply address for the LLM
provider's company.

---

## Step 8 — Report Completion

```
Voice memo ingest complete.

Processed: {N} file(s)
  ✓ Ingested: {list of stems}
  ✗ Skipped:  {list of stems with reason}

Wiki pages touched: {count}
Manifest updated: {skill_dir}/processed.txt
Log updated: wiki/log.md
```

---

## Behavior Guidelines

- **Read config before scanning.** Never hardcode a JustPressRecord path — the
  iCloud bundle ID varies by JustPressRecord version and macOS account.
- **Manifest is append-only.** Never remove entries. Manual removal is the
  only way to force re-processing.
- **raw/ is immutable.** Once a transcript is written to raw/,
  never modify it. The verbatim text is the permanent record.
- **Do not correct transcripts.** Whisper produces imperfect output for
  conversational speech. Preserve it — the ingest workflow synthesizes;
  raw/ does not.
- **Evaluate before ingesting.** Never ingest without the relevance check.
  Logistical content degrades wiki quality over time.
- **Ambiguous relevance: ask.** Show the transcript and ask if uncertain.
  Do not guess.
- **One commit per batch.** If multiple memos are ingested in one run,
  commit them together.
- **Schedulable.** This skill is designed for manual invocation but works
  unattended if scheduled (via the schedule skill). In scheduled mode,
  Step 8 output should flow into the next session's hot.md context.

---

## Fallback: No .m4a Files Found

If the `find` scan returns nothing and no JustPressRecord directory can be
identified:

```
Could not find a JustPressRecord iCloud directory on this machine.

To set up voice memo ingest:
1. Install JustPressRecord on iPhone and enable iCloud sync.
2. Confirm iCloud Drive is enabled on this Mac (System Settings → iCloud).
3. Run /ingest-voice again — it will scan for the directory automatically.

If JustPressRecord syncs to a non-standard path, run:
  find ~/Library/Mobile\ Documents -name "*.m4a" | head -20
and share the path it shows.
```

---

## Notes

This skill closes the gap identified in [[meeting-to-wiki-gap]]: audio
tools capture brilliantly but do not compile. The pipeline is:

**speak → JustPressRecord → iCloud sync → /ingest-voice → raw/ →
standard ingest → wiki**

Existing raw transcripts (e.g., `raw/LLM-Wiki combined with
Code project.md`) established the convention this skill follows. The
`.pdf` originals in raw/ were Apple-transcribed exports;
this skill produces higher-quality `.md` equivalents using Whisper.
