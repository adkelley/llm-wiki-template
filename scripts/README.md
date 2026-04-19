# Scripts

This directory contains setup and integration guides for the supported LLM workflows in this repository.

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