# LLM Wiki Template

This repo has been intentially unconfigured for an LLM or Obsidean.  For instructions on configuring your Wiki, please refer to the sources below. Particularly  [Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack).  Remove this README file from the Wiki once you have your Wiki configured, to prevent the LLM from entering it into Wiki.

## Protecting Source Files
After each Injest, the LLM has been instructed to commit the change to 'git'.  There is a git commit pre-hook 'pre-commit' that changes the permissions of the file(s) that were injested into 'read-only'.  This ensures that the LLM or User doesn't accidently delete a source file.

This hook:
```bash
#!/usr/bin/env bash
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
will affect
```
raw/articles/x.md
raw/papers/y.pdf
raw/data/z.csv
```

## Sources
[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
[Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack)
