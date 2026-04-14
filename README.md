# LLM Wiki Template

This repository is intentionally left unconfigured for any specific LLM workflow or for Obsidian. To configure your wiki, refer to the sources below, especially [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack).

Once your wiki is configured, remove this README from the wiki so your LLM does not ingest it as part of the knowledge base.

## Protecting Raw (Source) Files

After each ingest, you can instruct the LLM to commit the change to Git. You can also add a Git pre-commit hook that changes the permissions of newly ingested raw files to read-only. This helps prevent either the LLM or a user from accidentally modifying or deleting source files.

Add the following section to your `CLAUDE.md` or `AGENT.md` file:

```markdown
## Git Procedure
After every ingest, lint, or wiki update operation, commit the changes
as a normal part of the workflow. Do not wait for the user to ask.
- Stage only wiki/ and raw/ files. Never stage .obsidian/, .claude/, or .DS_Store.
- Write a concise commit message summarizing what was ingested or updated.
- End every commit message with: Co-Authored-By: <Enter your LLM info here>
- Do NOT push to remote unless explicitly asked.
```

Add this hook `pre-commit` to your `.git/hooks/` directory:

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

This will affect files such as:

```bash
raw/articles/x.md
raw/papers/y.pdf
raw/data/z.csv
```

## Sources

- [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack)
