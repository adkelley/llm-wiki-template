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

setup_codex() {
  local settings_file
  local codex_master_file
  local codex_template_file

  mkdir -p "$repo_root/skills"
  echo "Ensured ./skills directory exists (created if missing)"

  codex_master_file="$repo_root/AGENT.md"
  codex_template_file="$repo_root/scripts/codex/AGENT.md"

  if [ ! -f "$codex_master_file" ]; then
    cp "$codex_template_file" "$codex_master_file"
    echo "Copied AGENT.md to $codex_master_file"
  else
    echo "Skipped creating AGENT.md (already exists)"
  fi
}

install_optional_skills() {
  local source_skills_dir="$repo_root/scripts/optional-skills"
  local target_skills_dir="$repo_root/skills"
  local found_any=false
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

  read -r -p "Optional skills: [r]eview each, install [a]ll, or [s]kip? [r/a/S]: " install_mode

  case "$install_mode" in
    r|R|review|REVIEW)
      ;;
    a|A|all|ALL)
      install_mode="all"
      ;;
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
    skill_md="$skill_path/SKILL.md"
    metadata=$(read_skill_metadata "$skill_md")

    skill_display_name="$(printf '%s\n' "$metadata" | sed -n 's/^NAME=//p')"
    skill_description="$(printf '%s\n' "$metadata" | sed -n 's/^DESCRIPTION=//p')"

    if [ "$install_mode" = "all" ]; then
      if [ -e "$destination_path" ]; then
        echo "Skipping $skill_name because it already exists at $destination_path"
        continue
      fi

      cp -R "$skill_path" "$destination_path"
      echo "Installed $skill_name"
      continue
    fi

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
  setup_codex
  install_optional_skills
}

main "$@"
