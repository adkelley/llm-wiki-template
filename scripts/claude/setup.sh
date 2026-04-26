#!/usr/bin/env bash
set -euo pipefail

repo_root=""

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

  cp -R "$skill_path" "$destination_path"
  echo "Installed $skill_name"
}

update_existing_skill() {
  local skill_path="$1"
  local destination_path="$2"
  local skill_name="$3"

  cp "$skill_path/SKILL.md" "$destination_path/SKILL.md"
  echo "Updated $skill_name SKILL.md"
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

  if [ ! -f "$claude_master_file" ]; then
    cp "$claude_template_file" "$claude_master_file"
    echo "Copied CLAUDE.md to $claude_master_file"
  else
    echo "Skipped creating CLAUDE.md (already exists)"
  fi
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
      read -r -p "Update optional skill '$skill_name' SKILL.md only? [y/N/q]: " answer

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
  install_optional_skills
}

main "$@"
