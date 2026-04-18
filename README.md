# LLM Wiki Template

This repository is intentionally left unconfigured for any specific LLM workflow or IDE (e.g., Obsidian). To configure your wiki, refer to the sources below, especially [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack).

## Protecting Raw Files and Committing Changes Regularly

After each ingest, you can instruct your LLM to commit changes to Git automatically by adding a section to your `CLAUDE.md` or `AGENT.md` file. You can also add a Git `pre-commit` hook that changes newly ingested raw files to read-only. This helps prevent either the LLM or a user from accidentally modifying or deleting source files.

Add the following section to your `CLAUDE.md` or `AGENT.md` file:

## Installation

Clone this repository:

```bash
$ git clone https://github.com/adkelley/llm-wiki-template
```

## Git Commit Procedure
After every ingest, lint, or wiki update operation, commit the changes
as a normal part of the workflow. Do not wait for the user to ask.
- Stage only wiki/, todos/, scripts/, and raw/ files. Never stage .obsidian/, .claude/, or .DS_Store.
- Write a concise commit message summarizing what was ingested or updated.
- End every commit message with: Co-Authored-By: <Enter your LLM info here>
- Do NOT push to remote unless explicitly asked.

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

## Claude Code Setup

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

- The script expects the repository to already be initialized as a Git repo.
- Existing files and directories are preserved where possible. For example, existing optional skills are skipped rather than overwritten.
- If you want to customize Claude behavior further, edit `CLAUDE.md` after setup.
- Be sure to **set the Domain section in `CLAUDE.md`** with your topic.  


## Codex Setup

A setup script is provided to configure Codex for this repository.

Run:

```bash
scripts/codex/setup.sh
```

The script will:

- create `./skills/`
- copy `scripts/codex/AGENT.md` to `AGENT.md` in the repository root if `AGENT.md` does not already exist
- optionally prompt you to install additional skills from `scripts/optional-skills/` into `./skills/`

The installer copies optional skills; it does not remove them from the source directory.

A setup script is provided to configure Codex for this repository.

### Notes

- The script expects the repository to already be initialized as a Git repo.
- Existing files and directories are preserved where possible. For example, existing optional skills are skipped rather than overwritten.
- If you want to customize Codix behavior further, edit `AGENT.md` after setup.
- Be sure to **set the Domain section in `AGENT.md`** with your topic.  



## Obsidian
If you are using [Obsidian](https://obsidian.md/) as your IDE, you'll want to install additional obsidian related scripts that utilizes Obsidian's native CLI that provides programmatic access to Obsidian's internal caching database — bypassing OS-level filesystem searches entirely (see [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack?tab=readme-ov-file#8-the-obsidian-cli-advantage) for further information).


### Claude Code

```bash
# From your vault root
$ git clone https://github.com/kepano/obsidian-skills.git /tmp/obsidian-skills
$ cp -r /tmp/obsidian-skills/skills .claude/skills/obsidian-cli/

# Then, replace the obsidean-cli skill with a patch from @jackal092927
# From your vault root
$ git clone https://github.com/jackal092927/obsidian-official-cli-skills /tmp/obsidean-skills
$ cp -r /tmp/obsidean-skills/plugins/obsidian-cli/skills .claude/skills/
```

### Codex

```bash
# From your vault root
$ git clone https://github.com/kepano/obsidian-skills.git /tmp/obsidian-skills
$ cp -r /tmp/obsidian-skills/skills ./skills/obsidian-cli/

# Then, replace the obsidean-cli skill with a patch from @jackal092927
# From your vault root
$ git clone https://github.com/jackal092927/obsidian-official-cli-skills /tmp/obsidean-skills
$ cp -r /tmp/obsidean-skills/plugins/obsidian-cli/skills ./skills/
```

## Sources

- [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack)
- [The Complete Guide to Karpathy's LLM Wiki Workflow](https://proudfrog.com/en/insights/karpathy-llm-wiki-complete-workflow-guide)
