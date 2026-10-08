#!/usr/bin/env bash

set -Eeuo pipefail

# Refresh one or more Slackdump archive directories before Slack workflows use
# them. The archive itself is deliberately kept outside the mutable state
# directory; only refresh logs and status summaries are written here.

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
state_root="$repo_root/.llm-wiki/slack"
slackdump="${SLACKDUMP_BIN:-slackdump}"

usage() {
    cat <<'EOF'
Usage: refresh_slack.sh ARCHIVE [ARCHIVE ...]

Run `slackdump resume` and `slackdump resume --dedupe` for each archive.
If no archive is supplied, archives are discovered below raw/Slack that contain
slackdump.sqlite.

Environment:
  SLACKDUMP_BIN  Slackdump executable to use (default: slackdump)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if ! command -v "$slackdump" >/dev/null 2>&1; then
    printf 'Error: Slackdump executable not found: %s\n' "$slackdump" >&2
    exit 127
fi

declare -a archives=()
if (( $# > 0 )); then
    archives=("$@")
else
    while IFS= read -r -d '' database; do
        archives+=("$(dirname "$database")")
    done < <(find "$repo_root/raw/Slack" -type f -name slackdump.sqlite -print0 2>/dev/null)
fi

if (( ${#archives[@]} == 0 )); then
    printf 'Error: no Slackdump archives supplied or discovered.\n' >&2
    exit 1
fi

mkdir -p "$state_root"

json_summary() {
    local output_path="$1"
    local archive="$2"
    local started_at="$3"
    local completed_at="$4"
    local resume_status="$5"
    local dedupe_status="$6"
    local log_path="$7"
    local overall_status="$8"

    python3 - "$output_path" "$archive" "$started_at" "$completed_at" \
        "$resume_status" "$dedupe_status" "$log_path" "$overall_status" <<'PY'
import json
import sys
from pathlib import Path

(output, archive, started, completed, resume, dedupe, log, status) = sys.argv[1:]
payload = {
    "archive": archive,
    "started_at": started,
    "completed_at": completed,
    "resume": {"status": "success" if resume == "0" else "failed", "exit_code": int(resume)},
    "dedupe": {"status": "success" if dedupe == "0" else "failed", "exit_code": int(dedupe)},
    "status": status,
    "log": log,
}
Path(output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

refresh_archive() {
    local archive="$1"
    local archive_name
    archive_name="$(basename "${archive%/}")"

    if [[ ! -d "$archive" ]]; then
        printf 'Error: archive directory not found: %s\n' "$archive" >&2
        return 1
    fi

    local refresh_root="$state_root/$archive_name/refresh"
    local log_dir="$refresh_root/logs"
    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H%M%SZ')"
    local log_path="$log_dir/$timestamp.log"
    local summary_path="$refresh_root/latest.json"
    local lock_dir="$refresh_root/.lock"
    local started_at
    started_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local resume_status=1
    local dedupe_status=1

    mkdir -p "$log_dir"
    if ! mkdir "$lock_dir" 2>/dev/null; then
        printf 'Error: another refresh is already running for %s\n' "$archive" >&2
        return 1
    fi
    trap 'rmdir "$lock_dir" 2>/dev/null || true' RETURN

    {
        printf '[%s] Starting Slackdump refresh: %s\n' "$started_at" "$archive"
        printf '[%s] Command: %s resume %q\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$slackdump" "$archive"
    } | tee -a "$log_path"

    set +e
    "$slackdump" resume "$archive" 2>&1 | tee -a "$log_path"
    resume_status=${PIPESTATUS[0]}
    set -e
    printf '[%s] Resume exit code: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$resume_status" | tee -a "$log_path"

    if (( resume_status == 0 )); then
        printf '[%s] Command: %s resume --dedupe %q\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$slackdump" "$archive" | tee -a "$log_path"
        set +e
        "$slackdump" resume --dedupe "$archive" 2>&1 | tee -a "$log_path"
        dedupe_status=${PIPESTATUS[0]}
        set -e
        printf '[%s] Resume --dedupe exit code: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$dedupe_status" | tee -a "$log_path"
    else
        printf '[%s] Skipping dedupe because resume failed\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$log_path"
    fi

    local completed_at
    completed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local overall_status="failed"
    if (( resume_status == 0 && dedupe_status == 0 )); then
        overall_status="success"
    fi
    json_summary "$summary_path" "$archive" "$started_at" "$completed_at" \
        "$resume_status" "$dedupe_status" "$log_path" "$overall_status"
    printf '[%s] Refresh status: %s\n' "$completed_at" "$overall_status" | tee -a "$log_path"

    return $([[ "$overall_status" == "success" ]] && echo 0 || echo 1)
}

overall_exit=0
for archive in "${archives[@]}"; do
    if ! refresh_archive "$archive"; then
        overall_exit=1
    fi
done

exit "$overall_exit"
