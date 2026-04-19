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


## Obsidian
If you are using [Obsidian](https://obsidian.md/) as your IDE, you'll want to install additional obsidian related scripts that utilizes Obsidian's native CLI that provides programmatic access to Obsidian's internal caching database — bypassing OS-level filesystem searches entirely (see [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack?tab=readme-ov-file#8-the-obsidian-cli-advantage) for further information).

Copy the obsidian skills to your `/tmp` directory, then copy the pertinent files to your `/skills` directory

```bash
git clone https://github.com/kepano/obsidian-skills.git /tmp/kepano/obsidian-skills
git clone https://github.com/jackal092927/obsidian-official-cli-skills /tmp/jackal/obsidian-skills
# From your vault root
cp -r /tmp/kepano/obsidian-skills/skills/* .claude/skills/
cp -r /tmp/jackal/obsidian-skills/plugins/obsidian-cli/skills/obsidian-cli .claude/skills/
```
