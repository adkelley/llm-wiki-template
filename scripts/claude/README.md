# Claude Code Setup

If you use Claude Code, this setup script helps configure the repository for a Claude-based LLM wiki workflow.

Run:

```bash
scripts/claude/setup.sh
```

## What the script does

The script can:

1. create `.claude/`
2. create `.claude/skills/`
3. create `.claude/memory/`
4. create `.claude/settings.local.json` with the following configuration:

```json
{
  "autoMemoryDirectory": ".claude/memory"
}
```

5. copy `scripts/claude/CLAUDE.md` to `CLAUDE.md` in the repository root if `CLAUDE.md` does not already exist
6. optionally install Claude-specific skills into `.claude/skills/`

The generated `.claude/settings.local.json` tells Claude Code to store repository-specific auto-memory in `.claude/memory` inside the project, rather than in Claude Code’s default global memory location.

The installer copies optional skills into your active Claude environment. It does not remove them from the source directory.

## Optional skills

Shared optional skills are available under `scripts/optional-skills/`.

During setup, you can choose to:

- install new optional skills into `.claude/skills/`
- update existing optional skills by replacing only their `SKILL.md`
- review all optional skills before deciding whether to install or update each one
- skip optional skill installation and updates entirely

When updating an existing skill, the setup script preserves files such as `config.md` and `processed.txt`.

## After setup

After running the script, review and customize `CLAUDE.md` for your workflow.

In particular, make sure to update the `Domain` section so it reflects the subject area of your wiki.

## Notes

- The repository should already be initialized as a Git repository.
- Existing files are preserved where possible.
- The setup script is meant to save time, but you should still review generated configuration files before committing them.
