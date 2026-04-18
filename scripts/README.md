# Scripts

## Claude Code
If you are using the Claude Code LLM, then run `scripts/claude/setup.sh` to setup Claude Code and install optional skills.  The Obsidian Skills are not included in the optional skills installation.  See the install the skills related to Obsidian see []()

## Obsidian
If you are using [Obsidian](https://obsidian.md/) as your IDE, you'll want to install additional obsidian related scripts that utilizes Obsidian's native CLI that provides programmatic access to Obsidian's internal caching database — bypassing OS-level filesystem searches entirely (see [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack?tab=readme-ov-file#8-the-obsidian-cli-advantage) for further information).

### Claude
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
