from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from config import load_config
from errors import (
    CommandError,
    ConfigError,
    ParseError,
    RawWriteError,
    StateError,
)
from himalaya_client import (
    himalaya_account_list,
    himalaya_envelope_list,
    himalaya_folder_list,
    himalaya_message_read,
    himalaya_version,
)
from models import (
    EXPORT_ENVELOPE_PAGE_SIZE_MULTIPLIER,
    Candidate,
    DecisionInput,
    Envelope,
    Exclusion,
    MailConfig,
    RawWriteResult,
    ScanResult,
    StateRecord,
)
from parsers import parse_utc_timestamp
from raw_export import write_raw_candidate
from state import (
    append_state_records,
    envelope_key,
    evaluated_keys,
    filter_new_envelopes,
    last_scan_path,
    load_decisions,
    load_last_scan,
    load_state,
    write_last_scan,
)
from thread_context import thread_context_for_envelope


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def scan_candidates(
    skill_dir: Path, include_messages: bool = False, limit: int | None = None
) -> ScanResult:
    config = load_config(skill_dir)
    records = load_state(skill_dir)
    seen = evaluated_keys(records)
    last_scan = load_last_scan(skill_dir)
    window_days = scan_window_days(config.lookback_days, last_scan)

    candidates: list[Candidate] = []
    excluded: list[Exclusion] = []

    for account in config.accounts:
        for folder in config.folders:
            envelopes = himalaya_envelope_list(config, account, folder, window_days)

            new_envelopes: list[Envelope] = []
            for envelope in envelopes:
                if envelope_key(envelope) in seen:
                    excluded.append(
                        Exclusion(
                            account=envelope.account,
                            folder=envelope.folder,
                            envelope_id=envelope.id,
                            subject=envelope.subject,
                            reason="already evaluated in state.jsonl",
                        )
                    )
                else:
                    new_envelopes.append(envelope)

            for envelope in new_envelopes:
                if limit is not None and len(candidates) >= limit:
                    return ScanResult(
                        ok=True,
                        accounts=config.accounts,
                        folders=config.folders,
                        candidate_count=len(candidates),
                        candidates=candidates,
                        excluded_count=len(excluded),
                        excluded=excluded,
                        scan_window_days=window_days,
                        last_scan=last_scan,
                    )

                message = None
                message_error = None
                if include_messages:
                    try:
                        message = himalaya_message_read(account, folder, envelope.id)
                    except CommandError as exc:
                        message_error = str(exc)

                thread_context = thread_context_for_envelope(
                    envelope,
                    new_envelopes,
                    config.max_thread_context_messages,
                )
                candidates.append(
                    Candidate(
                        envelope=envelope,
                        message=message,
                        message_error=message_error,
                        thread_context=thread_context,
                    )
                )

    return ScanResult(
        ok=True,
        accounts=config.accounts,
        folders=config.folders,
        candidate_count=len(candidates),
        candidates=candidates,
        excluded_count=len(excluded),
        excluded=excluded,
        scan_window_days=window_days,
        last_scan=last_scan,
    )


def scan_window_days(
    lookback_days: int,
    last_scan: str | None,
    now: datetime | None = None,
) -> int:
    if last_scan is None:
        return lookback_days

    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    try:
        last = parse_utc_timestamp(last_scan)
    except ValueError:
        return lookback_days

    seconds_since_last_scan = (current - last).total_seconds()
    if seconds_since_last_scan < 0:
        return lookback_days

    days_since_last_scan = int(seconds_since_last_scan // 86400) + 1
    return min(lookback_days, max(1, days_since_last_scan + 1))


def decision_template_from_candidates(
    candidates: list[Candidate],
) -> list[DecisionInput]:
    return [
        DecisionInput(
            account=candidate.envelope.account,
            folder=candidate.envelope.folder,
            envelope_id=candidate.envelope.id,
            decision="ambiguous",
        )
        for candidate in candidates
    ]


def missing_items(configured: list[str], available: list[str]) -> list[str]:
    available_set = set(available)
    return [item for item in configured if item not in available_set]


def find_envelope_in_list(
    envelopes: list[Envelope],
    decision: DecisionInput,
) -> Envelope:
    for envelope in envelopes:
        if envelope.id == decision.envelope_id:
            return envelope
    raise RawWriteError(
        "Could not find envelope "
        f"{decision.envelope_id} in {decision.account} / {decision.folder}"
    )


def find_envelope_for_decision(config: MailConfig, decision: DecisionInput) -> Envelope:
    envelopes = himalaya_envelope_list(config, decision.account, decision.folder)
    return find_envelope_in_list(envelopes, decision)


def export_resolution_page_size(config: MailConfig) -> int:
    return config.max_messages_per_folder * EXPORT_ENVELOPE_PAGE_SIZE_MULTIPLIER


def export_resolution_envelopes(
    config: MailConfig,
    skill_dir: Path,
    account: str,
    folder: str,
) -> list[Envelope]:
    last_scan = load_last_scan(skill_dir)
    window_days = scan_window_days(config.lookback_days, last_scan)
    return himalaya_envelope_list(
        config,
        account,
        folder,
        window_days=window_days,
        page_size=export_resolution_page_size(config),
    )


def export_approved(skill_dir: Path, decisions_path: Path) -> list[RawWriteResult]:
    config = load_config(skill_dir)
    decisions = load_decisions(decisions_path)

    results: list[RawWriteResult] = []
    for decision in decisions:
        if decision.decision != "yes":
            continue
        envelopes = export_resolution_envelopes(
            config,
            skill_dir,
            decision.account,
            decision.folder,
        )
        envelope = find_envelope_in_list(envelopes, decision)
        thread_context = thread_context_for_envelope(
            envelope,
            envelopes,
            config.max_thread_context_messages,
        )
        message = himalaya_message_read(
            decision.account,
            decision.folder,
            decision.envelope_id,
        )
        candidate = Candidate(
            envelope=envelope,
            message=message,
            message_error=None,
            thread_context=thread_context,
        )
        results.append(write_raw_candidate(config, candidate))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "config",
            "himalaya-version",
            "preflight",
            "folder-list",
            "envelope-list",
            "message-read",
            "state",
            "scan",
            "finalize",
            "export-approved",
            "decisions-template",
        ],
    )
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--message-id")
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--include-messages", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--decisions")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir)

    if args.limit is not None and args.limit < 0:
        print("Error: --limit must be a positive integer", file=sys.stderr)
        return 2

    if args.command == "config":
        try:
            config = load_config(skill_dir)
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2

        print_json(asdict(config))
        return 0

    if args.command == "himalaya-version":
        try:
            output = himalaya_version()
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3

        print(output.strip())
        return 0

    if args.command == "folder-list":
        try:
            config = load_config(skill_dir)
            for account in config.accounts:
                folders = himalaya_folder_list(account)
                result = {
                    "account": account,
                    "folders": folders,
                }
                print_json(result)
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3

        return 0

    if args.command == "envelope-list":
        try:
            config = load_config(skill_dir)
            for account in config.accounts:
                for folder in config.folders:
                    # Keep envelope-list diagnostic; scan_candidates applies the scan window.
                    envelopes = himalaya_envelope_list(config, account, folder)

                    if args.new_only:
                        records = load_state(skill_dir)
                        envelopes = filter_new_envelopes(envelopes, records)

                    print_json(
                        [asdict(envelope) for envelope in envelopes],
                    )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3
        except ParseError as exc:
            print(f"Himalaya parse error: {exc}", file=sys.stderr)
            return 4
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5

        return 0

    if args.command == "message-read":
        if not args.message_id:
            print("Error: --message-id is required", file=sys.stderr)
            return 2

        try:
            config = load_config(skill_dir)
            account = config.accounts[0]
            folder = config.folders[0]
            message = himalaya_message_read(account, folder, args.message_id)
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3
        except ParseError as exc:
            print(f"Himalaya parse error: {exc}", file=sys.stderr)
            return 4

        print_json(asdict(message))
        return 0

    if args.command == "state":
        try:
            records = load_state(skill_dir)
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5

        print_json([asdict(record) for record in records])
        return 0

    if args.command == "scan":
        try:
            result = scan_candidates(
                skill_dir,
                include_messages=args.include_messages,
                limit=args.limit,
            )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3
        except ParseError as exc:
            print(f"Himalaya parse error: {exc}", file=sys.stderr)
            return 4
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5

        print_json(asdict(result))
        return 0

    if args.command == "finalize":
        if not args.decisions:
            print("Error: --decisions is required", file=sys.stderr)
            return 2

        try:
            decisions = load_decisions(Path(args.decisions))
            evaluated_at = utc_now_iso()
            records = [
                StateRecord(
                    account=d.account,
                    folder=d.folder,
                    envelope_id=d.envelope_id,
                    decision=d.decision,
                    evaluated_at=evaluated_at,
                )
                for d in decisions
            ]
            append_state_records(skill_dir, records)
            write_last_scan(skill_dir, evaluated_at)
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5

        print_json(
            {
                "ok": True,
                "appended": len(records),
                "evaluated_at": evaluated_at,
                "state_path": str(skill_dir / "state.jsonl"),
                "last_scan_path": str(last_scan_path(skill_dir)),
            }
        )
        return 0

    if args.command == "export-approved":
        if not args.decisions:
            print("Error: --decisions is required", file=sys.stderr)
            return 2
        try:
            results = export_approved(
                skill_dir=skill_dir, decisions_path=Path(args.decisions)
            )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3
        except ParseError as exc:
            print(f"Himalaya parse error: {exc}", file=sys.stderr)
            return 4
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5
        except RawWriteError as exc:
            print(f"Raw write error: {exc}", file=sys.stderr)
            return 6

        print_json(
            {
                "ok": True,
                "exported": len(results),
                "raw_files": [result.path for result in results],
            }
        )
        return 0

    if args.command == "decisions-template":
        try:
            result = scan_candidates(
                skill_dir,
                include_messages=False,
                limit=args.limit,
            )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3
        except ParseError as exc:
            print(f"Himalaya parse error: {exc}", file=sys.stderr)
            return 4
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5

        decisions = decision_template_from_candidates(result.candidates)
        print_json([asdict(decision) for decision in decisions])
        return 0

    if args.command == "preflight":
        try:
            config = load_config(skill_dir)
            version_output = himalaya_version()
            available_accounts = himalaya_account_list()
            missing_accounts = missing_items(config.accounts, available_accounts)
            if missing_accounts:
                raise ConfigError(
                    "Configured account(s) not found in Himalaya: "
                    + ", ".join(missing_accounts)
                )
            folders_by_account: dict[str, list[str]] = {}
            for account in config.accounts:
                available_folders = himalaya_folder_list(account)
                missing_folders = missing_items(config.folders, available_folders)
                if missing_folders:
                    raise ConfigError(
                        f"Configured folder(s) not found for account {account}: "
                        + ", ".join(missing_folders)
                    )
                folders_by_account[account] = available_folders
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except CommandError as exc:
            print(f"Himalaya error: {exc}", file=sys.stderr)
            return 3
        except ParseError as exc:
            print(f"Himalaya parse error: {exc}", file=sys.stderr)
            return 4
        result = {
            "ok": True,
            "himalaya_version": version_output.strip(),
            "accounts": config.accounts,
            "available_accounts": available_accounts,
            "folders": config.folders,
            "available_folders": folders_by_account,
        }
        print_json(result)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
