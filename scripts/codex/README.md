# Codex Setup

If you use Codex, this setup script helps configure the repository for a Codex-based LLM wiki workflow.

Run:

```bash
scripts/codex/setup.sh
```

## What the script does

The script can:

1. create `./skills/`
2. copy `scripts/codex/AGENT.md` to `AGENT.md` in the repository root, or
   update it when `AGENT.md` still matches the last installed template hash
3. optionally install shared optional skills into `./skills/`

The installer copies optional skills into your active Codex environment. It does not remove them from the source directory.
Template hashes are tracked in `.llm-wiki/template-manifest.jsonl` so local
edits to `AGENT.md` are preserved.

## Optional skills

Shared optional skills are available under `scripts/optional-skills/`.

During setup, you can choose to:

- install new optional skills into `./skills/`
- update existing optional skills by replacing only their `SKILL.md`
- review all optional skills before deciding whether to install or update each one
- skip optional skill installation and updates entirely

When updating an existing skill, the setup script preserves files such as `config.md` and `processed.txt`.

## After setup

After running the script, review and customize `AGENT.md` for your workflow.

In particular, make sure to update the `Domain` section so it reflects the subject area of your wiki.

## Obsidian

If you also use [Obsidian](https://obsidian.md/) as your IDE, you may want to install Obsidian-related skills and configure `.obsidian/app.json` for an Obsidian-based wiki workflow.

For that setup flow, see `scripts/obsidian/README.md`.

## Notes

- The repository should already be initialized as a Git repository.
- Existing files are preserved where possible.
- The setup script is meant to save time, but you should still review generated configuration files before committing them.
