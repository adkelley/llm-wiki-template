# Codex Setup

If you use Codex, this setup script helps configure the repository for a Codex-based LLM wiki workflow.

Run:

```bash
scripts/codex/setup.sh
```

## What the script does

The script can:

1. create `./skills/`
2. copy `scripts/codex/AGENT.md` to `AGENT.md` in the repository root if `AGENT.md` does not already exist
3. optionally install shared optional skills into `./skills/`

The installer copies optional skills into your active Codex environment. It does not remove them from the source directory.

## Optional skills

Shared optional skills are available under `scripts/optional-skills/`.

During setup, you can choose whether to install optional skills into `./skills/`.

Existing installed skills are preserved and skipped rather than overwritten.

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