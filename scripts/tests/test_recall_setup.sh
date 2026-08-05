#!/usr/bin/env bash
# shellcheck disable=SC1090,SC2123,SC2329
set -uo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/recall-setup-tests.XXXXXX")"
pass_count=0
fail_count=0

cleanup() {
  rm -rf -- "$test_root"
}
trap cleanup EXIT

pass() {
  printf 'PASS: %s\n' "$1"
  pass_count=$((pass_count + 1))
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  fail_count=$((fail_count + 1))
}

assert_equal() {
  local expected="$1"
  local actual="$2"
  local label="$3"

  if [ "$actual" = "$expected" ]; then
    pass "$label"
  else
    fail "$label (expected <$expected>, got <$actual>)"
  fi
}

assert_status() {
  local expected="$1"
  local actual="$2"
  local label="$3"

  if [ "$actual" -eq "$expected" ]; then
    pass "$label"
  else
    fail "$label (expected status $expected, got $actual)"
  fi
}

load_setup() {
  local setup_file="$1"

  # Load definitions without executing the interactive main function.
  source <(awk '/^main "\$@"$/ { exit } { print }' "$setup_file")
  set +e
}

test_domain_helpers() {
  local suite="$1"
  local fixture_dir="$test_root/$suite-domain"
  local output status

  mkdir -p "$fixture_dir"

  assert_equal \
    'ai-and-llm-research-may-2026' \
    "$(normalize_domain 'AI and LLM Research — May 2026')" \
    "$suite normalizes punctuation"
  assert_equal 'cafe-etudes' "$(normalize_domain 'Café Études')" \
    "$suite transliterates accents"
  assert_equal 'full-width-1' "$(normalize_domain 'Ｆｕｌｌ Ｗｉｄｔｈ ①')" \
    "$suite normalizes compatibility characters"
  assert_equal '' "$(normalize_domain '!!! 💭 —')" \
    "$suite permits an empty normalized result"

  printf '## Domain\nAI Research\n\n## Next\n' >"$fixture_dir/valid.md"
  printf '## Domain\n[Enter your wiki subject here]\n\n## Next\n' >"$fixture_dir/unset.md"
  printf '## Domain\n!!! 💭 —\n\n## Next\n' >"$fixture_dir/empty.md"

  output="$(resolve_recall_collection_name "$fixture_dir/valid.md" 2>/dev/null)"
  status=$?
  assert_status 0 "$status" "$suite accepts a configured Domain"
  assert_equal 'ai-research' "$output" "$suite returns the Domain slug"

  resolve_recall_collection_name "$fixture_dir/unset.md" >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects an unset Domain"
  resolve_recall_collection_name "$fixture_dir/empty.md" >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects an empty normalized Domain"
}

test_collection_list_parser() {
  local suite="$1"
  local valid no_collections output

  valid=$'Collections (2):\n\nnotes (qmd://notes/)\n  Pattern:  **/*.md\n  Files:    10\n  Updated:  now\n\narchive (qmd://archive/) [excluded]\n  Pattern:  **/*.md\n  Ignore:   private/**\n  Files:    5\n  Updated:  yesterday'
  no_collections="No collections found. Run 'qmd collection add .' to create one."

  output="$(parse_qmd_collection_names "$valid" 2>/dev/null)"
  assert_status 0 "$?" "$suite parses qmd collection list"
  assert_equal $'notes\narchive' "$output" "$suite returns every collection name"

  output="$(parse_qmd_collection_names "$no_collections" 2>/dev/null)"
  assert_status 0 "$?" "$suite accepts no qmd collections"
  assert_equal '' "$output" "$suite emits nothing for no collections"

  parse_qmd_collection_names $'Collections (1):\nnotes (qmd://other/)\n  Pattern: x' >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects mismatched display and URI names"
  parse_qmd_collection_names $'Collections (2):\nnotes (qmd://notes/)\n  Pattern: x' >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects a collection count mismatch"
  parse_qmd_collection_names 'unexpected output' >/dev/null 2>&1
  assert_status 1 "$?" "$suite fails closed on unknown list output"
}

test_collection_path_parser() {
  local suite="$1"
  local valid output

  valid=$'Collection: notes\n  Path:     /tmp/my notes\n  Pattern:  **/*.md\n  Include:  yes (default)\n  Update:   git pull\n  Contexts: 2'
  output="$(parse_qmd_collection_path "$valid" notes 2>/dev/null)"
  assert_status 0 "$?" "$suite parses qmd collection show"
  assert_equal '/tmp/my notes' "$output" "$suite preserves spaces in collection paths"

  parse_qmd_collection_path "$valid" archive >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects the wrong collection name"
  parse_qmd_collection_path $'Collection: notes\n  Path: /tmp/a\n  Path: /tmp/b' notes >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects duplicate collection paths"
  parse_qmd_collection_path $'Collection: notes\n  Path: /tmp/a\n  Owner: someone' notes >/dev/null 2>&1
  assert_status 1 "$?" "$suite fails closed on unknown show output"
}

test_qmd_availability() {
  local suite="$1"

  (
    PATH=/nonexistent
    qmd() { :; }
    npm() { return 99; }
    yes_no_prompt() { return 99; }
    ensure_qmd_available
  ) >/dev/null 2>&1
  assert_status 0 "$?" "$suite accepts an existing qmd command"

  (
    PATH=/nonexistent
    yes_no_prompt() { return 1; }
    npm() { return 99; }
    ensure_qmd_available
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite handles declined qmd installation"

  (
    PATH=/nonexistent
    yes_no_prompt() { return 0; }
    npm() { return 42; }
    ensure_qmd_available
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite handles npm installation failure"

  (
    PATH=/nonexistent
    yes_no_prompt() { return 0; }
    npm() {
      qmd() { :; }
      return 0
    }
    ensure_qmd_available
  ) >/dev/null 2>&1
  assert_status 0 "$?" "$suite verifies qmd after installation"

  (
    PATH=/nonexistent
    yes_no_prompt() { return 0; }
    npm() { return 0; }
    ensure_qmd_available
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects an installed qmd missing from PATH"
}

test_collection_resolution() {
  local suite="$1"
  local fixture_dir="$test_root/$suite-resolution"
  local wiki_path other_path output status add_log

  mkdir -p "$fixture_dir/wiki" "$fixture_dir/other"
  wiki_path="$(canonicalize_directory "$fixture_dir/wiki")"
  other_path="$(canonicalize_directory "$fixture_dir/other")"
  add_log="$fixture_dir/add.log"

  (
    list_qmd_collection_names() { return 0; }
    qmd() { printf '%s\n' "$*" >>"$add_log"; return 0; }
    resolve_or_add_qmd_collection "$wiki_path" ai-wiki
  ) >"$fixture_dir/output" 2>/dev/null
  status=$?
  output="$(cat "$fixture_dir/output")"
  assert_status 0 "$status" "$suite adds a new collection"
  assert_equal 'ai-wiki' "$output" "$suite returns a new collection name"
  assert_equal "collection add $wiki_path --name ai-wiki" "$(cat "$add_log")" \
    "$suite registers only the canonical wiki path"

  output="$({
    list_qmd_collection_names() { printf 'old-name\n'; }
    get_qmd_collection_path() { printf '%s\n' "$wiki_path"; }
    resolve_or_add_qmd_collection "$wiki_path" ai-wiki
  } 2>/dev/null)"
  assert_status 0 "$?" "$suite adopts an existing path under another name"
  assert_equal 'old-name' "$output" "$suite returns the adopted name"

  (
    list_qmd_collection_names() { printf 'ai-wiki\n'; }
    get_qmd_collection_path() { printf '%s\n' "$other_path"; }
    resolve_or_add_qmd_collection "$wiki_path" ai-wiki
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects a derived-name collision"

  (
    list_qmd_collection_names() { printf 'one\ntwo\n'; }
    get_qmd_collection_path() { printf '%s\n' "$wiki_path"; }
    resolve_or_add_qmd_collection "$wiki_path" ai-wiki
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite rejects multiple names for one path"
}

test_qmd_lifecycle() {
  local suite="$1"
  local log_file="$test_root/$suite-lifecycle.log"
  local context_line

  context_line='context add qmd://ai-wiki Maintained wiki pages for AI Research. This collection contains wiki pages only; it does not contain raw source material or repository configuration.'

  (
    qmd() { printf '%s\n' "$*" >>"$log_file"; return 0; }
    prepare_qmd_collection ai-wiki 'AI Research'
  ) >/dev/null 2>&1
  assert_status 0 "$?" "$suite completes qmd preparation"
  assert_equal "$context_line
update
embed" "$(cat "$log_file")" "$suite runs context, update, and embed in order"

  : >"$log_file"
  (
    qmd() {
      printf '%s\n' "$*" >>"$log_file"
      return 1
    }
    prepare_qmd_collection ai-wiki 'AI Research'
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite reports qmd context failure"
  assert_equal "$context_line" "$(cat "$log_file")" \
    "$suite stops immediately after context failure"

  : >"$log_file"
  (
    qmd() {
      printf '%s\n' "$*" >>"$log_file"
      [ "$1" != update ]
    }
    prepare_qmd_collection ai-wiki 'AI Research'
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite reports qmd update failure"
  assert_equal "$context_line
update" "$(cat "$log_file")" "$suite skips embed after update failure"

  : >"$log_file"
  (
    qmd() {
      printf '%s\n' "$*" >>"$log_file"
      [ "$1" != embed ]
    }
    prepare_qmd_collection ai-wiki 'AI Research'
  ) >/dev/null 2>&1
  assert_status 1 "$?" "$suite reports qmd embed failure"
  assert_equal "$context_line
update
embed" "$(cat "$log_file")" "$suite reaches embed only after update"
}

test_config_preservation() {
  local suite="$1"
  local fixture_dir="$test_root/$suite-config"
  local source_skill="$fixture_dir/source"
  local destination="$fixture_dir/destination"
  local expected actual

  mkdir -p "$source_skill" "$destination"
  printf 'skill v1\n' >"$source_skill/SKILL.md"
  write_recall_config "$destination" ai-wiki >/dev/null
  expected=$'# Recall configuration\n\nqmd_collection: ai-wiki'
  actual="$(cat "$destination/config.md")"
  assert_equal "$expected" "$actual" "$suite writes recall config"

  printf 'skill v2\n' >"$source_skill/SKILL.md"
  printf 'qmd_collection: overwrite-attempt\n' >"$source_skill/config.md"
  update_existing_skill "$source_skill" "$destination" recall >/dev/null
  assert_equal "$expected" "$(cat "$destination/config.md")" \
    "$suite preserves config during skill update"
  assert_equal 'skill v2' "$(cat "$destination/SKILL.md")" \
    "$suite still updates other skill files"
}

run_suite() {
  local setup_file="$1"
  local suite

  suite="$(basename "$(dirname "$setup_file")")"
  printf '\n== %s ==\n' "$suite"
  load_setup "$setup_file"
  test_domain_helpers "$suite"
  test_collection_list_parser "$suite"
  test_collection_path_parser "$suite"
  test_qmd_availability "$suite"
  test_collection_resolution "$suite"
  test_qmd_lifecycle "$suite"
  test_config_preservation "$suite"
}

bash -n "$project_root/scripts/codex/setup.sh" || fail 'Codex setup syntax'
bash -n "$project_root/scripts/claude/setup.sh" || fail 'Claude setup syntax'

run_suite "$project_root/scripts/codex/setup.sh"
run_suite "$project_root/scripts/claude/setup.sh"

printf '\nSummary: %s passed, %s failed\n' "$pass_count" "$fail_count"
[ "$fail_count" -eq 0 ]
