# Claude Code Setup

A setup script is provided to configure Claude Code for this repository.

Run:

```bash
scripts/claude/setup.sh
```

The script will:

- create `.claude`
- create `.claude/skills/`
- create `.claude/memory/`
- create `.claude/settings.local.json` with the following configuration:

```json
{
  "autoMemoryDirectory": ".claude/memory"
}
```

- copy `scripts/claude/CLAUDE.md` to `CLAUDE.md` in the repository root if `CLAUDE.md` does not already exist
- optionally prompt you to install additional Claude skills from `scripts/claude/optional-skills/` into `.claude/skills/`
- `.claude/setting.local.json` config tells Claude Code to store this repository’s auto-memory files in `.claude/memory` inside the project, rather than in Claude Code’s default global memory location in your home directory.

The installer copies optional skills; it does not remove them from the source directory.
