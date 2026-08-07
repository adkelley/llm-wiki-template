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

yes_no_default_yes_prompt() {
  local prompt="$1"
  local response

  while true; do
    read -r -p "$prompt (Y/n): " response

    case "$response" in
      ""|y|Y|yes|YES)
        return 0
        ;;
      n|N|no|NO)
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

if heading not in text:
    raise SystemExit(f"Domain heading not found in {path}")

before, after = text.split(heading, 1)
section_end = after.find("\n## ")

if section_end == -1:
    raise SystemExit(f"End of Domain section not found in {path}")

after = domain + "\n" + after[section_end:]
path.write_text(before + heading + after)
PY
}

read_domain() {
  local target_file="$1"

  python3 - "$target_file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
heading = "## Domain\n"

if heading not in text:
    raise SystemExit(0)

after = text.split(heading, 1)[1]
section_end = after.find("\n## ")
if section_end == -1:
    raise SystemExit(0)

domain = after[:section_end].strip()
if domain.startswith("[Enter your wiki subject here"):
    raise SystemExit(0)

print(domain)
PY
}

normalize_domain() {
  local domain="$1"

  python3 - "$domain" <<'PY'
import re
import sys
import unicodedata

domain = sys.argv[1]
normalized_domain = unicodedata.normalize("NFKD", domain)
ascii_domain = normalized_domain.encode("ascii", "ignore").decode("ascii")
slug = re.sub(r'[^a-z0-9]+', '-', ascii_domain.lower()).strip("-")
print(slug)
PY
}

configure_domain() {
  local target_file="$1"
  local existing_domain="${2:-}"
  local target_name="${3:-$(basename "$target_file")}"
  local domain

  if [ -n "$existing_domain" ]; then
    echo "Existing wiki domain: $existing_domain"
    if yes_no_default_yes_prompt "Copy this domain into the new $target_name?"; then
      apply_domain "$target_file" "$existing_domain"
      echo "Copied existing wiki domain to the new $target_name"
      return 0
    fi
  fi

  domain="$(prompt_for_domain)"

  if [ -n "$domain" ]; then
    apply_domain "$target_file" "$domain"
    echo "Set wiki domain to: $domain"
  else
    echo "Left the Domain placeholder unchanged"
  fi
}

resolve_recall_collection_name() {
  local domain_file="$1"
  local domain
  local collection_name

  domain="$(read_domain "$domain_file")"
  if [ -z "$domain" ]; then
    printf 'No Domain is configured in %s. Configure ## Domain and rerun setup.sh\n' \
      "$(basename "$domain_file")" >&2
    return 1
  fi

  collection_name="$(normalize_domain "$domain")"
  if [ -z "$collection_name" ]; then
    printf 'The Domain in %s does not produce a usable collection name. Configure ## Domain and rerun setup.sh\n' \
      "$(basename "$domain_file")" >&2
    return 1
  fi

  printf '%s\n' "$collection_name"
}

prompt_for_recall_collection_name() {
  local default_name="$1"
  local collection_name

  while true; do
    if ! IFS= read -r -p \
      "qmd collection name [$default_name]: " collection_name; then
      printf '\nUnable to read the qmd collection name.\n' >&2
      return 1
    fi

    # Pressing Enter accepts the Domain-derived collection name
    if [ -z "$collection_name" ]; then
      printf '%s\n' "$default_name"
      return 0
    fi

    if [[ "$collection_name" =~ ^[A-Za-z0-9_-]+$ ]]; then
      printf '%s\n' "$collection_name"
      return 0
    fi

    printf 'Invalid qmd collection name: %s\n' "$collection_name" >&2
    printf 'Use only letters, digits, hyphens, and underscores.\n' >&2
  done
}

ensure_qmd_available() {
  if command -v qmd >/dev/null 2>&1; then
    return 0
  fi

  if ! yes_no_prompt \
    "This skill requires qmd to be installed. Install qmd?"; then
    echo "Skipped installing qmd"
    echo "Install it manually with: npm install -g @tobilu/qmd"
    return 1
  fi

  if ! npm install -g @tobilu/qmd; then
    echo "Failed to install qmd."
    echo "Retry manually with: npm install -g @tobilu/qmd"
    return 1
  fi

  if ! command -v qmd >/dev/null 2>&1; then
    echo "qmd was installed, but it is not available on PATH."
    echo "Verify the npm global bin directory, then rerun setup.sh."
    return 1
  fi

  echo "qmd installed successfully"
  return 0
}

canonicalize_directory() {
  local directory="$1"

  if [ ! -d "$directory" ]; then
    printf 'Directory not found: %s\n' "$directory" >&2
    return 1
  fi

  (cd "$directory" && pwd -P)
}

parse_qmd_collection_names() {
  local output="$1"

  python3 - "$output" <<'PY'
import re
import sys

output = sys.argv[1]
lines = output.splitlines()

if output.strip() == "No collections found. Run 'qmd collection add .' to create one.":
    raise SystemExit(0)

if not lines:
    print("Unable to parse qmd collection list: empty output", file=sys.stderr)
    raise SystemExit(1)

header_match = re.fullmatch(r"Collections \((\d+)\):", lines[0])

if not header_match:
    print("Unable to parse qmd collection list header", file=sys.stderr)
    raise SystemExit(1)

expected_count = int(header_match.group(1))
names = []
seen = set()
saw_collection = False

for line in lines[1:]:
    if not line:
        continue

    collection_match = re.fullmatch(
        r"(.+?) \(qmd://([^/]+)/\)(?: \[excluded\])?",
        line,
    )

    if collection_match:
        display_name = collection_match.group(1)
        uri_name = collection_match.group(2)

        if display_name != uri_name:
            print(
                f"Collection name mismatch: {display_name!r} != {uri_name!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)

        if display_name in seen:
            print(
                f"Duplicate collection name: {display_name!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        seen.add(display_name)
        names.append(display_name)
        saw_collection = True
        continue

    detail_match = re.fullmatch(
        r"  (?:Pattern|Ignore|Files|Updated):.*",
        line,
    )

    if detail_match:
        if not saw_collection:
            print(
                f"Expected collection name before details: {line!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)

        continue

    print(
        f"Unable to parse qmd collection list line: {line!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)

if len(names) != expected_count:
    print(
        f"Expected {expected_count} collections, but found {len(names)}",
        file=sys.stderr,
    )
    raise SystemExit(1)

for name in names:
    print(name)
PY
}

list_qmd_collection_names() {
  local output

  if ! output="$(NO_COLOR=1 qmd collection list)"; then
    printf 'Unable to inspect qmd collections.\n' >&2
    printf 'Run these diagnostic commands:\n' >&2
    printf '  qmd collection list\n' >&2
    printf '  qmd status\n' >&2
    return 1
  fi

  if ! parse_qmd_collection_names "$output"; then
    printf 'Unable to safely interpret qmd collection output.\n' >&2
    printf 'Run these diagnostic commands:\n' >&2
    printf '  NO_COLOR=1 qmd collection list\n' >&2
    printf '  qmd status\n' >&2
    return 1
  fi
}

parse_qmd_collection_path() {
  local output="$1"
  local expected_name="$2"

  python3 - "$output" "$expected_name" <<'PY'
import re
import sys

output = sys.argv[1]
expected_name = sys.argv[2]
lines = output.splitlines()

if not lines:
    print("Unable to parse qmd collection path: empty output", file=sys.stderr)
    raise SystemExit(1)

header_match = re.fullmatch(r"Collection: (.+)", lines[0])

if not header_match:
    print("Unable to parse qmd collection path header", file=sys.stderr)
    raise SystemExit(1)

actual_name = header_match.group(1).strip()
if actual_name != expected_name:
    print(
        f"qmd collection name mismatch: expected {expected_name!r}, "
        f"got {actual_name!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)

collection_path = None
for line in lines[1:]:
    if not line:
        continue

    path_match = re.fullmatch(r"  Path:\s+(.+)", line)
    if path_match:
        if collection_path is not None:
            print("Multiple path entries found for qmd collection", file=sys.stderr)
            raise SystemExit(1)

        collection_path = path_match.group(1).strip()

        if not collection_path:
            print("qmd collection path is empty", file=sys.stderr)
            raise SystemExit(1)

        continue

    detail_match = re.fullmatch(
        r"  (?:Pattern|Include|Update|Contexts):\s+.*",
        line,
    )

    if detail_match:
        continue

    print(
        f"Unable to parse qmd collection detail: {line!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)

if collection_path is None:
    print("Unable to parse qmd collection path", file=sys.stderr)
    raise SystemExit(1)

print(collection_path)
PY
}

get_qmd_collection_path() {
  local collection_name="$1"
  local output

  if ! output="$(NO_COLOR=1 qmd collection show "$collection_name")"; then
    printf 'Unable to inspect qmd collection %s.\n' \
      "$collection_name" >&2
    printf 'Run these diagnostic commands:\n' >&2
    printf '  qmd collection show %s\n' "$collection_name" >&2
    printf '  qmd collection list\n' >&2
    return 1
  fi

  if ! parse_qmd_collection_path "$output" "$collection_name"; then
    printf 'Unable to safely interpret qmd collection %s.\n' \
      "$collection_name" >&2
    printf 'Run these diagnostic commands:\n' >&2
    printf '  NO_COLOR=1 qmd collection show %s\n' \
      "$collection_name" >&2
    printf '  NO_COLOR=1 qmd collection list\n' >&2
    return 1
  fi
}

resolve_or_add_qmd_collection() {
  local wiki_path="$1"
  local derived_name="$2"
  local names_output
  local collection_name
  local registered_path
  local canonical_registered_path
  local matching_path_name=""
  local derived_name_path=""

  if ! names_output="$(list_qmd_collection_names)"; then
    return 1
  fi

  while IFS= read -r collection_name; do
    [ -z "$collection_name" ] && continue

    registered_path="$(get_qmd_collection_path "$collection_name")" || return 1

    if ! canonical_registered_path="$(canonicalize_directory "$registered_path")"; then
      printf 'Unable to canonicalize registered path for qmd collection %s\n' \
        "$collection_name" >&2
      return 1
    fi

    # Record same-path and derived-name matches here
    if [ "$canonical_registered_path" = "$wiki_path" ]; then
      if [ -n "$matching_path_name" ]; then
        printf 'Multiple qmd collections point to %s: %s and %s.\n' \
          "$wiki_path" "$matching_path_name" "$collection_name" >&2
          printf 'No qmd collections were modified.\n' >&2
          return 1
      fi
        matching_path_name="$collection_name"
    fi

    if [ "$derived_name" = "$collection_name" ]; then
      derived_name_path="$canonical_registered_path"
    fi
  done <<< "$names_output"

  if [ -n "$matching_path_name" ]; then
    printf '%s\n' "$matching_path_name"
    return 0
  fi

  if [ -n "$derived_name_path" ]; then
    printf 'qmd collection name %s already points to %s.\n' \
      "$derived_name" "$derived_name_path" >&2
    printf 'The current wiki path is %s. No collections were modified.\n' \
      "$wiki_path" >&2
    printf 'Inspect with: qmd collection show %s\n' \
      "$derived_name" >&2
    return 1
  fi

  if ! qmd collection add "$wiki_path" --name "$derived_name" >&2; then
    printf 'Failed to add qmd collection %s for %s.\n' \
      "$derived_name" "$wiki_path" >&2
    printf 'Inspect with: qmd collection list\n' >&2
    return 1
  fi

  printf '%s\n' "$derived_name"
  return 0
}

prepare_qmd_collection() {
  local collection_name="$1"
  local domain="$2"
  local context

  context="Curated wiki about ${domain}, containing maintained knowledge pages and durable analysis."

  # context, update, embed
  if ! qmd context add "qmd://$collection_name" "$context"; then
    printf 'Failed to add context for qmd collection %s\n' \
      "$collection_name" >&2
    printf 'Retry with: qmd context add %q %q\n' \
      "qmd://$collection_name" "$context" >&2
    return 1
  fi

  if ! qmd update; then
    printf 'Failed to update qmd collections.\n' >&2
    printf 'Retry with: qmd update\n' >&2
    return 1
  fi

  if ! qmd embed --collection "$collection_name"; then
    printf 'Failed to embed qmd collection %s.\n' \
      "$collection_name" >&2
    printf 'Retry with: qmd embed --collection %q\n' \
      "$collection_name" >&2
    return 1
  fi

  return 0
}

initialize_recall_skill() {
  local destination_path="$1"
  local domain_file="$2"
  local config_file="$destination_path/config.md"
  local domain
  local derived_name
  local wiki_path
  local collection_name
  local selected_name

  if [ -f "$config_file" ]; then
    printf 'Preserved existing recall configuration: %s\n' "$config_file"
    return 0
  fi

  if ! derived_name="$(resolve_recall_collection_name "$domain_file")"; then
    return 1
  fi

  if ! selected_name="$(prompt_for_recall_collection_name "$derived_name")"; then
    return 1
  fi

  domain="$(read_domain "$domain_file")"

  if ! ensure_qmd_available; then
    return 1
  fi

  if ! wiki_path="$(canonicalize_directory "$repo_root/wiki")"; then
    return 1
  fi

  if ! collection_name="$(
    resolve_or_add_qmd_collection "$wiki_path" "$selected_name"
  )"; then
    return 1
  fi

  if ! prepare_qmd_collection "$collection_name" "$domain"; then
    return 1
  fi

  write_recall_config "$destination_path" "$collection_name"
}

write_recall_config() {
  local destination_path="$1"
  local collection_name="$2"
  local config_file="$destination_path/config.md"

  printf '# Recall configuration\n\nqmd_collection: %s\n' \
    "$collection_name" > "$config_file"

  printf 'Configured recall to use qmd collection: %s\n' \
    "$collection_name"
}

initialize_optional_skill() {
  local skill_name="$1"
  local destination_path="$2"
  local domain_file="$3"

  if [ "$skill_name" != "recall" ]; then
    return 0
  fi

  if ! initialize_recall_skill "$destination_path" "$domain_file"; then
    printf 'Recall was installed, but qmd initialization did not complete.\n'
    printf 'Review the diagnostics above, then rerun setup.sh.\n'
  fi

  return 0
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

  sync_skill_files "$skill_path" "$destination_path" true
  echo "Updated $skill_name files"
}

sync_skill_files() {
  local skill_path="$1"
  local destination_path="$2"
  local preserve_config="${3:-false}"

  mkdir -p "$destination_path"
  local -a rsync_args=(
    -a
    --delete
    --exclude 'config.toml'
    --exclude 'state.jsonl'
    --exclude 'last_scan.txt'
    --exclude '__pycache__/'
    --exclude '*.pyc'
  )

  if [[ "$preserve_config" == "true" ]]; then
    rsync_args+=(--exclude 'config.md')
  fi

  rsync "${rsync_args[@]}" \
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
  local existing_domain

  status="$(template_status "$template_file" "$target_file")"

  case "$status" in
    missing)
      cp "$template_file" "$target_file"
      configure_domain "$target_file"
      record_installed_template "$template_file" "$target_file"
      echo "Copied $target_name to $target_file"
      ;;
    replace)
      existing_domain="$(read_domain "$target_file")"
      cp "$template_file" "$target_file"
      configure_domain "$target_file" "$existing_domain" "$target_name"
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
        existing_domain="$(read_domain "$target_file")"
        backup_file="$target_file.backup-$(date +%Y%m%d-%H%M%S)"
        cp "$target_file" "$backup_file"
        echo "Backed up $target_name to $backup_file"
        cp "$template_file" "$target_file"
        configure_domain "$target_file" "$existing_domain" "$target_name"
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

setup_codex() {
  local codex_master_file
  local codex_template_file

  mkdir -p "$repo_root/skills"
  echo "Ensured ./skills directory exists (created if missing)"

  codex_master_file="$repo_root/AGENT.md"
  codex_template_file="$repo_root/scripts/codex/AGENT.md"

  install_managed_template \
    "$codex_template_file" \
    "$codex_master_file" \
    "AGENT.md"
}

install_optional_skills() {
  local source_skills_dir="$repo_root/scripts/optional-skills"
  local target_skills_dir="$repo_root/skills"
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
  local domain_file="$repo_root/AGENT.md"

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
          initialize_optional_skill "$skill_name" "$destination_path" "$domain_file"
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
          initialize_optional_skill "$skill_name" "$destination_path" "$domain_file"
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
  setup_codex
  install_raw_protection_hook
  install_optional_skills
}

main "$@"
