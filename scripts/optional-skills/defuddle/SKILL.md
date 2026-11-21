---
name: defuddle
description: |
  Clean web-page capture for LLM Wiki users. Trigger when the user invokes
  "/defuddle", asks to capture, clip, scrape, or save a web article as clean
  Markdown, provides a URL for wiki ingestion, or wants page chrome removed
  before adding a source to raw/. Uses an existing Defuddle CLI without
  installing it implicitly, extracts article content and metadata, and writes
  a provenance-rich Markdown file to raw/. Stops after capture unless
  the user explicitly asks to run the standard wiki ingest workflow.
---

# /defuddle - Clean Web Capture

## Purpose

Use Defuddle to remove navigation, ads, sidebars, comments, cookie banners,
and other page chrome before saving a page's primary content as immutable wiki
source material.

This skill captures a source; it does not synthesize it. Write the cleaned
article to `raw/`, then stop unless the user explicitly asks to ingest
the new file.

## Requirements

Require:

- Node.js and npm
- an already accessible `defuddle` package/CLI
- network access when parsing a URL
- `raw/` in the current wiki

Do not install or update Defuddle merely because `defuddle` is not on `PATH`.
Do not use plain `npx defuddle` as an availability probe because `npx` may
download the package.

## Step 1 - Resolve an Existing CLI

Try these options in order and retain the first command that succeeds:

```bash
command -v defuddle
defuddle --help
```

```bash
test -x ./node_modules/.bin/defuddle
./node_modules/.bin/defuddle --help
```

```bash
npx --no-install defuddle --help
```

If those checks fail, inspect the global npm installation:

```bash
npm ls -g --depth=0 defuddle
npm prefix -g
```

If `defuddle` is listed globally, try its executable under the reported global
prefix, commonly:

```bash
"$(npm prefix -g)/bin/defuddle" --help
```

Treat any working option as installed. Use that option for the rest of the
workflow. In particular, if `npx --no-install defuddle` works, use it; do not
replace it with a global installation.

Only when every non-installing check fails:

1. Report that Defuddle is absent or inaccessible.
2. Ask the user whether to install it.
3. Install only after explicit approval, using the user's preferred scope.

Suggested commands after approval:

```bash
npm install defuddle
```

Or, only when the user specifically wants a global command:

```bash
npm install -g defuddle
```

## Step 2 - Parse the Page

If no URL or local HTML path was supplied, ask for one. Run from the wiki root
with the resolved command:

```bash
{DEFUDDLE_COMMAND} parse "{URL_OR_HTML_PATH}" --markdown --json
```

The JSON result contains cleaned Markdown in `content` plus metadata such as
`title`, `author`, `published`, `domain`, `description`, `language`, and
`wordCount`.

Do not scrape authenticated, private, paywalled, or access-controlled content
without the user's authorization. Do not bypass access controls.

## Step 3 - Write the Raw Source

Create `raw/articles/` if needed. Build a lowercase ASCII slug from the title,
falling back to the domain or local filename. Use:

```text
raw/articles/{YYYY-MM-DD}-{slug}.md
```

Use today's date as the capture date. Refuse to overwrite an existing file;
append a short stable discriminator or ask the user how to proceed.

Write YAML frontmatter followed by the cleaned Markdown:

```yaml
---
source_url: "{original URL or local path}"
title: "{title}"
author: "{author, if present}"
date_published: "{published, if present}"
date_clipped: "{YYYY-MM-DD}"
domain: "{domain, if present}"
language: "{language, if present}"
word_count: {wordCount, if present}
capture_tool: defuddle
---
```

Quote and escape YAML string values correctly. Omit unavailable optional
fields rather than inventing them. Preserve Defuddle's cleaned article body;
do not summarize, correct, or editorialize it in `raw/`.

## Step 4 - Report and Optionally Ingest

Report:

- the created raw file path
- the extracted title and author when available
- the cleaned word count when available
- that the source has not yet been ingested into `wiki/`

If the user explicitly asks to ingest the captured source, run the standard
wiki ingest workflow:

1. Run `python3 scripts/wiki/ingest_guard.py check raw/articles/{filename}.md`.
2. Stop and report any duplicate identified by the guard.
3. Present 3-5 key takeaways.
4. Create or update the source summary, concepts, entities, `wiki/index.md`,
   and `wiki/log.md`.
5. Record success with
   `python3 scripts/wiki/ingest_guard.py record raw/articles/{filename}.md`.

Never silently ingest immediately after capture.

## Useful Options

Use these current Defuddle CLI options when requested:

```bash
# Extract one metadata property
{DEFUDDLE_COMMAND} parse "{URL}" --property title

# Prefer a language
{DEFUDDLE_COMMAND} parse "{URL}" --markdown --json --lang en

# Diagnose poor extraction
{DEFUDDLE_COMMAND} parse "{URL}" --markdown --json --debug
```

## Failure Modes

- **CLI inaccessible:** complete all non-installing checks, then request
  approval before any installation.
- **Parse or network error:** report the concise error and do not create a raw
  file from partial output.
- **Empty content:** stop and report that Defuddle found no usable primary
  content.
- **Poor extraction:** retry with `--debug`; do not silently substitute raw
  page HTML.
- **Existing destination:** never overwrite it.
- **Malformed metadata:** preserve valid content, omit invalid optional fields,
  and report the omission.

Do not write to `wiki/` during capture or failure handling.
