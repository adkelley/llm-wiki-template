# Scripts

## Claude Code
If you are using the Claude Code LLM, then run `scripts/claude/setup.sh` to setup Claude Code and install optional skills.  The Obsidian Skills are not included in the optional skills installation.  Instructions for installing these skills below.

## Obsidian
If you are using [Obsidian](https://obsidian.md/) as your IDE, you'll want to install additional obsidian related scripts that utilizes Obsidian's native CLI that provides programmatic access to Obsidian's internal caching database — bypassing OS-level filesystem searches entirely (see [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack?tab=readme-ov-file#8-the-obsidian-cli-advantage) for further information).

Copy the obsidian skills to your `/tmp` directory

```bash
git clone https://github.com/kepano/obsidian-skills.git /tmp/kepano/obsidian-skills
git clone https://github.com/jackal092927/obsidian-official-cli-skills /tmp/jackal/obsidian-skills
```

Then, depending on whether you're using Claude Code or Codex, finish installing by following the directions below:

### Claude Code

```bash
# From your vault root
cp -r /tmp/kepano/obsidian-skills/skills/* .claude/skills/
cp -r /tmp/jackal/obsidian-skills/plugins/obsidian-cli/skills/obsidian-cli .claude/skills/
```

### Codex

```bash
# From your vault root
cp -r /tmp/kepano/obsidian-skills/skills/* ./skills/
cp -r /tmp/jackal/obsidian-skills/plugins/obsidian-cli/skills/obsidian-cli ./skills/
```
