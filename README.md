# LLM Wiki Template

This repository is a starting point for building an LLM-maintained wiki. It is intentionally left mostly unconfigured so you can adapt it to your preferred agent, editor, and workflow.

The default structure follows the general LLM wiki pattern popularized by Andrej Karpathy and related community tooling:

- `raw/` stores source material and other inputs
- `wiki/` stores LLM-maintained notes, summaries, and syntheses
- `scripts/` contains setup helpers for supported tools and environments

For background, see the sources listed at the end of this README, especially [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack).

## Installation

Clone the repository:

```bash
git clone https://github.com/adkelley/llm-wiki-template
cd llm-wiki-template
```

## Repository Layout

```text
raw/       immutable source files and inputs
wiki/      generated and maintained wiki content
scripts/   setup scripts and integration guides
```

### `raw/`

Use `raw/` for source documents such as:

- articles
- papers
- PDFs
- transcripts
- datasets
- assets

As a rule, files in `raw/` should be treated as immutable inputs.

### `wiki/`

Use `wiki/` for the LLM-maintained knowledge layer, such as:

- source summaries
- concept pages
- entity pages
- comparisons
- syntheses
- logs
- overviews

### `scripts/`

The `scripts/` directory contains setup and integration helpers for:

- Claude Code
- Codex
- Obsidian
- shared optional skills

See `scripts/README.md` for an overview.

## Recommended Workflow

A typical workflow looks like this:

1. add source material to `raw/`
2. ask your LLM to ingest it into `wiki/`
3. keep `wiki/index.md`, `wiki/log.md`, and related pages updated
4. commit changes regularly
5. optionally use Obsidian as the front-end for browsing and editing the wiki

## Git Safety for `raw/`

Because `raw/` is intended to hold immutable source material, it is a good idea to protect those files from accidental modification.

You can do that in two complementary ways:

1. instruct your LLM to treat `raw/` as read-only in `CLAUDE.md` or `AGENT.md`
2. add a Git `pre-commit` hook that marks newly added or modified files under `raw/` as read-only

### Suggested Git procedure for your agent instructions

Add a section like this to your `CLAUDE.md` or `AGENT.md`:

```md
## Git Procedure
After every ingest, lint, or wiki update operation, commit the changes
as a normal part of the workflow. Do not wait for the user to ask.
- Stage only wiki/, todos/, scripts/, and raw/ files. Never stage .obsidian/, .claude/, or .DS_Store.
- Write a concise commit message summarizing what was ingested or updated.
- End every commit message with: Co-Authored-By: <Enter your LLM info here>
- Do NOT push to remote unless explicitly asked.
```

### Suggested `pre-commit` hook

Create `.git/hooks/pre-commit` with the following contents:

```bash
#!/usr/bin/env bash
set -euo pipefail

git diff --cached --name-only --diff-filter=ACM -z |
while IFS= read -r -d '' file; do
  case "$file" in
    raw/*)
      if [ -f "$file" ]; then
        chmod a-w "$file"
        echo "Set read-only: $file"
      fi
      ;;
  esac
done
```

This hook will affect files such as:

```text
raw/x.md
raw/y.pdf
raw/z.csv
```

## Tool Setup

This repository includes setup scripts for supported LLM environments.

## Claude Code

If you use Claude Code, run:

```bash
scripts/claude/setup.sh
```

This setup script can:

- create `.claude/`
- create `.claude/skills/`
- create `.claude/memory/`
- create `.claude/settings.local.json`
- copy `scripts/claude/CLAUDE.md` to `CLAUDE.md`, or update it when the
  installed file still matches the last template hash
- optionally install Claude-related skills

The generated `.claude/settings.local.json` config stores Claude Code auto-memory inside the repository at `.claude/memory` instead of using Claude Code's default global location.

### Notes

- the repository should already be initialized as a Git repository
- existing files are preserved where possible
- existing optional skills can be updated by replacing only `SKILL.md`
- after setup, review and customize `CLAUDE.md`
- be sure to set the `Domain` section in `CLAUDE.md`

For more details, see `scripts/claude/README.md`.

## Codex

If you use Codex, run:

```bash
scripts/codex/setup.sh
```

This setup script can:

- create `./skills/`
- copy `scripts/codex/AGENT.md` to `AGENT.md`, or update it when the installed
  file still matches the last template hash
- optionally install shared optional skills

### Notes

- the repository should already be initialized as a Git repository
- existing files are preserved where possible
- existing optional skills can be updated by replacing only `SKILL.md`
- after setup, review and customize `AGENT.md`
- be sure to set the `Domain` section in `AGENT.md`

For more details, see `scripts/codex/README.md`.

## Obsidian

If you use [Obsidian](https://obsidian.md/) as your IDE, you may also want to configure the repository for an Obsidian-based wiki workflow.

Run:

```bash
scripts/obsidian/setup.sh
```

The Obsidian setup script can help:

- configure `.obsidian/app.json`
- install Obsidian-related skills for Claude Code or Codex
- improve compatibility with Obsidian-specific file formats and workflows

These integrations can provide more reliable access to Obsidian metadata and cache behavior than plain filesystem search alone in some workflows.

### Why this matters

Obsidian-related skills can help agents work more safely with:

- Obsidian-specific conventions
- vault metadata
- internal links
- attachments
- CLI-based lookups

For more details, see `scripts/obsidian/README.md`.

## Optional Skills

Shared optional skills live under `scripts/optional-skills/`.

Depending on the setup flow you choose, installer scripts may copy selected skills into:

- `.claude/skills/` for Claude Code
- `./skills/` for Codex

The installer copies skills into the active environment; it does not remove them from the source directory.

## Notes

- empty directories are tracked using `.gitkeep` placeholder files where needed
- `raw/` should be treated as immutable
- `wiki/` is the layer your LLM should actively maintain
- setup scripts are intended to save time, but you should still review generated config files before committing them
- if you use both an LLM agent and Obsidian, review `.obsidian/`, `.claude/`, `CLAUDE.md`, and `AGENT.md` to make sure they match your preferred workflow

## Sources

- [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack)
- [The Complete Guide to Karpathy's LLM Wiki Workflow](https://proudfrog.com/en/insights/karpathy-llm-wiki-complete-workflow-guide)
