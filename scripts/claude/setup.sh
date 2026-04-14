#!/usr/bin/env bash
set -euo pipefail

repo_root=""

is_valid_skill_dir() {
  local dir="$1"
  [ -d "$dir" ] && [ -f "$dir/SKILL.md" ]
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
  local source_skills_dir="$repo_root/scripts/claude/optional-skills"
  local target_skills_dir="$repo_root/.claude/skills"
  local found_any=false
  local install_skills
  local skill_path
  local skill_name
  local destination_path
  local answer

  mkdir -p "$target_skills_dir"

  if [ ! -d "$source_skills_dir" ]; then
    echo "No optional skills directory found at $source_skills_dir"
    return 0
  fi

  read -r -p "Do you want to review optional skills for installation? [y/N]: " install_skills

  case "$install_skills" in
    y|Y|yes|YES) ;;
    *)
      echo "Skipping optional skill installation."
      return 0
      ;;
  esac

  for skill_path in "$source_skills_dir"/*; do
    is_valid_skill_dir "$skill_path" || continue
    found_any=true

    skill_name="$(basename "$skill_path")"
    destination_path="$target_skills_dir/$skill_name"

    if [ -e "$destination_path" ]; then
      echo "Skipping $skill_name because it already exists at $destination_path"
      continue
    fi

    read -r -p "Install optional skill '$skill_name'? [y/N/q]: " answer

    case "$answer" in
      y|Y|yes|YES)
        cp -R "$skill_path" "$destination_path"
        echo "Installed $skill_name"
        ;;
      q|Q|quit|QUIT)
        echo "Stopped installing optional skills."
        break
        ;;
      *)
        echo "Skipped $skill_name"
        ;;
    esac
  done

  if [ "$found_any" = false ]; then
    echo "No top-level optional skills with SKILL.md were found in $source_skills_dir"
  fi
}

main() {
  repo_root="$(git rev-parse --show-toplevel)"
  setup_claude
  install_optional_skills
}

main "$@"
