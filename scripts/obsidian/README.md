# Obsidian Setup

If you use [Obsidian](https://obsidian.md/) as your IDE, this setup script helps configure the repository for an Obsidian-based LLM wiki workflow.

Run:

```bash
scripts/obsidian/setup.sh
```

## What the script does

The script can help with three tasks:

1. setup the `.obsidian` directory if it doesn't already exist
2. configure `.obsidian/app.json` for this repository
3. optionally install Obsidian-related skills for your LLM environment

Notably, task 1 can bootstrap the `.obsidian` configuration when the directory does not already exist, avoiding the need to open Obsidian just to initialize the vault. Obsidian will create other files and folders lazily as needed. We also highly recommend installing the community plugin [terminal](https://github.com/polyipseity/obsidian-terminal) so you can interact with your LLM directly from within Obsidian.


## Obsidian configuration

The setup script can replace `.obsidian/app.json` with the following configuration:

```json
{
  "userIgnoreFilters": [
    "node_modules/",
    ".git/",
    ".claude/"
  ],
  "newFileLocation": "folder",
  "newFileFolderPath": "raw/articles",
  "attachmentFolderPath": "raw/assets"
}
```

### Why ignore `.claude/`?

`.claude/` contains operational files such as skills, plans, and agent memory. These are part of the LLM tooling layer, not the human-facing knowledge base. Excluding `.claude/` from Obsidian helps avoid:

- graph pollution
- noisy search results
- accidental edits to tool state

## Optional Obsidian skills

The script will also prompt you to install Obsidian-related skills from these repositories:

- `https://github.com/kepano/obsidian-skills.git`
- `https://github.com/jackal092927/obsidian-official-cli-skills.git`

Depending on your LLM environment, the skills are installed into:

- `.claude/skills/` for Claude Code
- `./skills/` for Codex

## Why these skills matter

The official skills repository from Steph Ango (`@kepano`) provides guidance for working correctly with Obsidian-specific formats and workflows.

The patch repository from `@jackal092927` addresses documented issues in the Obsidian CLI integration, including cases where commands may appear to succeed while returning incomplete or incorrect data. For an automated wiki workflow, that kind of silent failure is especially risky because the agent may continue operating on bad information.

## Notes

- Review the generated `.obsidian/app.json` before committing if you maintain custom local Obsidian settings.
- If you do not use Obsidian, you can skip this setup entirely.
- If you use Claude Code or Codex with Obsidian, these skills can make the wiki workflow much more reliable.
- The setup script is meant to save time, but you should still review generated configuration files before committing them.
