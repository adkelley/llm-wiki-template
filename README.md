# LLM Wiki Template

This repository is intentionally left unconfigured for any specific LLM workflow or IDE (e.g., Obsidian). To configure your wiki, refer to the sources below, especially [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack).

Once your wiki is configured, remove this README from the wiki so your LLM does not ingest it as part of the knowledge base.

## Protecting Raw Files and Committing Changes Regularly

After each ingest, you can instruct your LLM to commit changes to Git automatically by adding a section to your `CLAUDE.md` or `AGENT.md` file. You can also add a Git `pre-commit` hook that changes newly ingested raw files to read-only. This helps prevent either the LLM or a user from accidentally modifying or deleting source files.

Add the following section to your `CLAUDE.md` or `AGENT.md` file:

```markdown
## Git Procedure
After every ingest, lint, or wiki update operation, commit the changes
as a normal part of the workflow. Do not wait for the user to ask.
- Stage only wiki/, todos/, scripts/, and raw/ files. Never stage .obsidian/, .claude/, or .DS_Store.
- Write a concise commit message summarizing what was ingested or updated.
- End every commit message with: Co-Authored-By: <Enter your LLM info here>
- Do NOT push to remote unless explicitly asked.
```

Create a file named `pre-commit` in `.git/hooks/` with the following contents:

```bash
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

```bash
raw/articles/x.md
raw/papers/y.pdf
raw/data/z.csv
```

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

### Notes

- Run the script from anywhere inside the Git repository.
- The script expects the repository to already be initialized as a Git repo.
- Existing files and directories are preserved where possible. For example, existing optional skills are skipped rather than overwritten.
- If you want to customize Claude behavior further, edit `CLAUDE.md` after setup.

## Sources

- [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack)
