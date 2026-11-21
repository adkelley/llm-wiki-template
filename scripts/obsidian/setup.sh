#!/usr/bin/env bash
set -euo pipefail

repo_root=""

is_valid_skill_dir() {
  local dir="$1"
  [ -d "$dir" ] && [ -f "$dir/SKILL.md" ]
}

is_valid_obsidian_vault() {
  local dir="$1"
  [ -d "$dir/.obsidian/" ]
}

replace_obsidian_settings() {
  local repo_root="$1"
  local settings_dir="$repo_root/.obsidian/"
  local settings_app="$repo_root/scripts/obsidian/app.json"

  cp "$settings_app" "$settings_dir"
  echo "Settings created or replaced in $settings_dir"
}

which_llm() {
  local repo_root="$1"
  if [ -f "$repo_root/CLAUDE.md" ]; then
    echo "claude"
  elif [ -f "$repo_root/AGENT.md" ]; then
    echo "codex"
  else
    echo "LLM model not found. Supported models: claude, codex"
    exit 1
  fi
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

install_obsidean_skills() {
  local repo_root="$1"
  local llm=$(which_llm "$repo_root")
  local found_any=false
  local install_mode
  local skill_path
  local skill_name
  local destination_path
  local answer
  local metadata
  local skill_display_name
  local skill_description
  local kepano_clone_dir="/tmp/kepano"
  local jackal_clone_dir="/tmp/jackal"

  local kepano_repo="https://github.com/kepano/obsidian-skills.git"
  local source_kepano_skills_dir="$kepano_clone_dir/skills/"
  local source_jackal_skills_dir="$jackal_clone_dir/plugins/obsidian-cli/skills/obsidian-cli"
  local jackal_repo="https://github.com/jackal092927/obsidian-official-cli-skills.git"

  if [ "$llm" = "claude" ]; then
    echo "Adding Obsidian skills to Claude"
    local target_skills_dir="$repo_root/.claude/skills"
  else
    echo "Adding Obsidian skills to Codex"
    local target_skills_dir="$repo_root/skills"
  fi

  mkdir -p "$target_skills_dir"

  read -r -p "Optional Obsidian skills: [r]eview each, install [a]ll, or [s]kip? [r/a/S]: " install_mode

  case "$install_mode" in
    r|R|review|REVIEW)
      ;;
    a|A|all|ALL)
      install_mode="all"
      ;;
    *)
      echo "Skipping optional Obsidian skill installation."
      return 0
      ;;
  esac

  rm -rf /tmp/kepano /tmp/jackal
  mkdir -p /tmp/kepano /tmp/jackal

  echo "Cloning Obsidian skills repos to /tmp/.."
  if ! git clone --depth 1 "$kepano_repo" "$kepano_clone_dir"; then
      echo "Failed to clone $kepano_repo into $kepano_clone_dir"
      exit 1
  fi

  if ! git clone --depth 1 "$jackal_repo" "$jackal_clone_dir"; then
      echo "Failed to clone $jackal_repo into $jackal_clone_dir"
      exit 1
  fi

  if [ ! -d "$source_kepano_skills_dir" ] || [ ! -d "$source_jackal_skills_dir" ]; then
      echo "No skills directory found at $source_kepano_skills_dir or $source_jackal_skills_dir"
      exit 1
  fi

  if [ ! -d "$target_skills_dir" ]; then
      mkdir -p "$target_skills_dir"
  fi

  # Copy the patch from Jackal to Kepano's clone directory
  if ! cp -R "$source_jackal_skills_dir" "$source_kepano_skills_dir/obsidian-cli"; then
      echo "Failed to copy Jackal obsidian-cli skill patch to Kepano's clone directory"
      exit 1
  fi

  for skill_path in "$source_kepano_skills_dir"/*; do
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
    echo "No top-level skills with SKILL.md were found in $source_kepano_skills_dir"
   fi
}

main() {
  repo_root="$(git rev-parse --show-toplevel)"
  if is_valid_obsidian_vault "$repo_root"; then
    echo "Valid Obsidian vault found at $repo_root"
  else
    echo "No valid Obsidian vault found at $repo_root"
    echo "Creating $repo_root/.obsidian/"
    mkdir -p "$repo_root/.obsidian/"
  fi
  replace_obsidian_settings "$repo_root"
  install_obsidean_skills "$repo_root"
}

main "$@"
