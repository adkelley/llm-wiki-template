#!/usr/bin/env bash
set -euo pipefail

repo_root=""

yes_no_prompt() {
  local prompt="$1"
  local response

  while true; do
    read -r -p "$prompt (y/N): " response

    case "$response" in
      y|Y|yes|YES)
        return 0
        ;;
      ""|n|N|no|NO)
        return 1
        ;;
      *)
        echo "Please answer yes or no."
        ;;
    esac
  done
}

prompt_for_domain() {
  local domain

  read -r -p "Wiki domain or project name (leave blank to configure later): " domain

  # Trim leading/trailing whitespace
  domain="${domain#"${domain%%[![:space:]]*}"}"
  domain="${domain%"${domain##*[![:space:]]}"}"

  if [ -z "$domain" ]; then
    return 0
  fi

  printf '%s\n' "$domain"
}

apply_domain() {
  local target_file="$1"
  local domain="$2"

  python3 - "$target_file" "$domain" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
domain = sys.argv[2]
text = path.read_text()

heading = "## Domain\n"
placeholder = '[Enter your wiki subject here example - "AI LLM Research, May 2026 -"]'

if heading not in text:
    raise SystemExit(f"Domain heading not found in {path}")

before, after = text.split(heading, 1)

if placeholder not in after:
    raise SystemExit(f"Domain placeholder not found in {path}")

after = after.replace(placeholder, domain, 1)
path.write_text(before + heading + after)
PY
}

configure_domain() {
  local target_file="$1"
  local domain

  domain="$(prompt_for_domain)"

  if [ -n "$domain" ]; then
    apply_domain "$target_file" "$domain"
    echo "Set wiki domain to: $domain"
  else
    echo "Left the Domain placeholder unchanged"
  fi
}

install_raw_protection_hook() {
  local hook_file="$repo_root/.git/hooks/pre-commit"

  if ! yes_no_prompt \
    "Install a pre-commit hook that makes committed raw/ files read-only?"; then
    echo "Skipped installing the raw/ protection hook"
    return 0
  fi

  if [ -e "$hook_file" ]; then
    echo "Skipped installing the raw/ protection hook"
    echo "A pre-commit hook already exists at $hook_file"
    return 0
  fi

  cat > "$hook_file" <<'HOOK'
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
HOOK

  chmod +x "$hook_file"
  echo "Installed the raw/ protection hook at $hook_file"
}

is_valid_skill_dir() {
  local dir="$1"
  [ -d "$dir" ] && [ -f "$dir/SKILL.md" ]
}

read_skill_metadata() {
  local skill_md="$1"

  awk '
    BEGIN {
      in_frontmatter=0
      frontmatter_started=0
      in_description=0
      description=""
    }
    /^---[[:space:]]*$/ {
      if (frontmatter_started == 0) {
        frontmatter_started=1
        in_frontmatter=1
        next
      } else if (in_frontmatter == 1) {
        in_frontmatter=0
        in_description=0
        exit
      }
    }
    in_frontmatter == 1 {
      if ($0 ~ /^name:[[:space:]]*/) {
        sub(/^name:[[:space:]]*/, "", $0)
        name=$0
        in_description=0
      } else if ($0 ~ /^description:[[:space:]]*/) {
        sub(/^description:[[:space:]]*/, "", $0)
        description=$0
        in_description=1
      } else if (in_description == 1 && $0 ~ /^[[:space:]]+/) {
        line=$0
        sub(/^[[:space:]]+/, "", line)
        if (description != "" && line != "") {
          description=description " " line
        } else if (line != "") {
          description=line
        }
      } else if ($0 ~ /^[^[:space:]][^:]*:[[:space:]]*/) {
        in_description=0
      } else {
        in_description=0
      }
    }
    END {
      printf "NAME=%s\nDESCRIPTION=%s\n", name, description
    }
  ' "$skill_md"
}

install_new_skill() {
  local skill_path="$1"
  local destination_path="$2"
  local skill_name="$3"

  sync_skill_files "$skill_path" "$destination_path"
  echo "Installed $skill_name"
}

update_existing_skill() {
  local skill_path="$1"
  local destination_path="$2"
  local skill_name="$3"

  sync_skill_files "$skill_path" "$destination_path"
  echo "Updated $skill_name files"
}

sync_skill_files() {
  local skill_path="$1"
  local destination_path="$2"

  mkdir -p "$destination_path"
  rsync -a --delete \
    --exclude 'config.toml' \
    --exclude 'state.jsonl' \
    --exclude 'last_scan.txt' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$skill_path/" "$destination_path/"
}

template_status() {
  local template_file="$1"
  local target_file="$2"

  (cd "$repo_root" && python3 scripts/wiki/template_guard.py status \
    --template "$template_file" \
    --target "$target_file") \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["status"])'
}

record_installed_template() {
  local template_file="$1"
  local target_file="$2"

  (cd "$repo_root" && python3 scripts/wiki/template_guard.py record \
    --template "$template_file" \
    --target "$target_file") \
    >/dev/null
}

install_managed_template() {
  local template_file="$1"
  local target_file="$2"
  local target_name="$3"
  local status
  local backup_file

  status="$(template_status "$template_file" "$target_file")"

  case "$status" in
    missing)
      cp "$template_file" "$target_file"
      configure_domain "$target_file"
      record_installed_template "$template_file" "$target_file"
      echo "Copied $target_name to $target_file"
      ;;
    replace)
      cp "$template_file" "$target_file"
      configure_domain "$target_file"
      record_installed_template "$template_file" "$target_file"
      echo "Updated $target_name from the latest template"
      ;;
    record)
      record_installed_template "$template_file" "$target_file"
      echo "Recorded current $target_name template hash"
      ;;
    current)
      echo "Skipped updating $target_name (already current)"
      ;;
    preserve)
      if yes_no_prompt "$target_name has local changes. Replace it with the latest template?"; then
        backup_file="$target_file.backup-$(date +%Y%m%d-%H%M%S)"
        cp "$target_file" "$backup_file"
        echo "Backed up $target_name to $backup_file"
        cp "$template_file" "$target_file"
        configure_domain "$target_file"
        record_installed_template "$template_file" "$target_file"
        echo "Updated $target_name from the latest template; backup saved to $backup_file"
      else
        echo "Skipped updating $target_name (local changes detected)"
      fi
      ;;
    *)
      echo "Skipped updating $target_name (unrecognized template status: $status)"
      ;;
  esac
}

setup_claude() {
  local settings_file
  local claude_master_file
  local claude_template_file

  mkdir -p "$repo_root/.claude/skills"
  echo "Ensured .claude/skills directory exists (created if missing)"

  mkdir -p "$repo_root/.claude/memory"
  echo "Ensured .claude/memory directory exists (created if missing)"

  settings_file="$repo_root/.claude/settings.local.json"

  if [ ! -f "$settings_file" ]; then
    cat > "$settings_file" <<EOF
{
  "autoMemoryDirectory": ".claude/memory"
}
EOF
    echo "Created .claude/settings.local.json"
  else
    echo "Skipped creating .claude/settings.local.json (already exists)"
  fi

  claude_master_file="$repo_root/CLAUDE.md"
  claude_template_file="$repo_root/scripts/claude/CLAUDE.md"

  install_managed_template \
    "$claude_template_file" \
    "$claude_master_file" \
    "CLAUDE.md"
}

install_optional_skills() {
  local source_skills_dir="$repo_root/scripts/optional-skills"
  local target_skills_dir="$repo_root/.claude/skills"
  local found_any=false
  local shown_any=false
  local install_mode
  local skill_path
  local skill_name
  local destination_path
  local answer
  local metadata
  local skill_display_name
  local skill_description

  mkdir -p "$target_skills_dir"

  if [ ! -d "$source_skills_dir" ]; then
    echo "No optional skills directory found at $source_skills_dir"
    return 0
  fi

  read -r -p "Optional skills: [i]nstall new, [u]pdate existing, [r]eview all, or [s]kip? [i/u/r/S]: " install_mode

  case "$install_mode" in
    i|I|install|INSTALL|install-new|INSTALL-NEW)
      install_mode="install"
      ;;
    u|U|update|UPDATE|update-existing|UPDATE-EXISTING)
      install_mode="update"
      ;;
    r|R|review|REVIEW|review-all|REVIEW-ALL)
      install_mode="review"
      ;;
    ""|s|S|skip|SKIP)
      echo "Skipping optional skill installation."
      return 0
      ;;
    *)
      echo "Unrecognized choice. Skipping optional skill installation."
      return 0
      ;;
  esac

  for skill_path in "$source_skills_dir"/*; do
    is_valid_skill_dir "$skill_path" || continue
    found_any=true

    skill_name="$(basename "$skill_path")"
    destination_path="$target_skills_dir/$skill_name"
    skill_md="$skill_path/SKILL.md"
    metadata=$(read_skill_metadata "$skill_md")

    skill_display_name="$(printf '%s\n' "$metadata" | sed -n 's/^NAME=//p')"
    skill_description="$(printf '%s\n' "$metadata" | sed -n 's/^DESCRIPTION=//p')"

    if [ "$install_mode" = "install" ] && [ -e "$destination_path" ]; then
      continue
    fi

    if [ "$install_mode" = "update" ] && [ ! -e "$destination_path" ]; then
      continue
    fi

    shown_any=true

    echo
    echo "Optional skill: $skill_display_name"
    echo "Directory: $skill_name"
    if [ -n "$skill_description" ]; then
      echo "Description: $skill_description"
      echo
    else
      echo "Description: (none found in SKILL.md)"
    fi

    if [ -e "$destination_path" ]; then
      read -r -p "Update optional skill '$skill_name' files, preserving local config/state? [y/N/q]: " answer

      case "$answer" in
        y|Y|yes|YES)
          update_existing_skill "$skill_path" "$destination_path" "$skill_name"
          ;;
        q|Q|quit|QUIT)
          echo "Stopped installing optional skills."
          break
          ;;
        *)
          echo "Skipped $skill_name"
          ;;
      esac
    else
      read -r -p "Install optional skill '$skill_name'? [y/N/q]: " answer

      case "$answer" in
        y|Y|yes|YES)
          install_new_skill "$skill_path" "$destination_path" "$skill_name"
          ;;
        q|Q|quit|QUIT)
          echo "Stopped installing optional skills."
          break
          ;;
        *)
          echo "Skipped $skill_name"
          ;;
      esac
    fi
  done

  if [ "$found_any" = false ]; then
    echo "No top-level optional skills with SKILL.md were found in $source_skills_dir"
  elif [ "$shown_any" = false ]; then
    case "$install_mode" in
      install)
        echo "No new optional skills are available to install."
        ;;
      update)
        echo "No installed optional skills are available to update."
        ;;
    esac
  fi
}

main() {
  repo_root="$(git rev-parse --show-toplevel)"
  setup_claude
  install_raw_protection_hook
  install_optional_skills
}

main "$@"
