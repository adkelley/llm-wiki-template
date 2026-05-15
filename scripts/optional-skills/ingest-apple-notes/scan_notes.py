from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from config import load_config
from errors import ConfigError, NotesClientError, RawWriteError, StateError
from models import (
    Candidate,
    DecisionInput,
    Exclusion,
    Note,
    NotesConfig,
    RawWriteResult,
    ScanFilters,
    ScanResult,
    StateRecord,
)
from notes_client import (
    exclude_recently_deleted_notes,
    filter_notes_by_config,
    limit_notes_for_scan,
    load_notes,
    normalize_tags,
    note_content_hash,
    note_matches_exclude_tags,
    note_matches_include_tags,
    parser_note_to_note,
    preflight_notes,
    sort_notes_for_scan,
)
from raw_export import (
    raw_filename,
    raw_note_text,
    slugify,
    write_raw_note,
)
from state import (
    append_state_records,
    evaluated_keys,
    load_decisions,
    load_last_scan,
    load_state,
    write_last_scan,
)


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def filter_new_notes(
    notes: list[Note],
    records: list[StateRecord],
) -> tuple[list[Note], list[Exclusion]]:
    seen = evaluated_keys(records)
    candidates: list[Note] = []
    excluded: list[Exclusion] = []

    for note in notes:
        if (note.note_id, note.content_hash) in seen:
            excluded.append(
                Exclusion(
                    note_id=note.note_id,
                    title=note.title,
                    reason="already evaluated in state.jsonl",
                )
            )
        else:
            candidates.append(note)

    return candidates, excluded


def parse_note_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def filter_notes_by_scan_window(
    notes: list[Note],
    scan_window_days: int,
    now: datetime | None = None,
) -> tuple[list[Note], list[Exclusion]]:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    cutoff = current.timestamp() - (scan_window_days * 86400)

    included: list[Note] = []
    excluded: list[Exclusion] = []

    for note in notes:
        modified = parse_note_datetime(note.modified_at)
        if modified is None:
            excluded.append(
                Exclusion(
                    note_id=note.note_id,
                    title=note.title,
                    reason="missing or unparsable modified_at",
                )
            )
            continue

        if modified.timestamp() < cutoff:
            excluded.append(
                Exclusion(
                    note_id=note.note_id,
                    title=note.title,
                    reason="outside scan window",
                )
            )
            continue

        included.append(note)

    return included, excluded


def scan_filters_from_config(config: NotesConfig) -> ScanFilters:
    return ScanFilters(
        accounts=config.accounts,
        folders=config.folders,
        include_tags=config.include_tags,
        exclude_tags=config.exclude_tags,
    )


def scan_candidates_from_notes(
    notes: list[Note],
    records: list[StateRecord],
    scan_window_days: int,
    last_scan: str | None,
    filters: ScanFilters,
    limit: int | None = None,
    now: datetime | None = None,
) -> ScanResult:
    window_notes, window_excluded = filter_notes_by_scan_window(
        notes,
        scan_window_days,
        now=now,
    )
    new_notes, state_excluded = filter_new_notes(window_notes, records)
    excluded = window_excluded + state_excluded

    if limit is not None:
        new_notes = new_notes[:limit]

    candidates = [Candidate(note=note) for note in new_notes]

    return ScanResult(
        ok=True,
        candidate_count=len(candidates),
        candidates=candidates,
        excluded_count=len(excluded),
        excluded=excluded,
        scan_window_days=scan_window_days,
        filters=filters,
        last_scan=last_scan,
    )


def decision_template_from_candidates(
    candidates: list[Candidate],
) -> list[DecisionInput]:
    return [
        DecisionInput(
            note_id=candidate.note.note_id,
            content_hash=candidate.note.content_hash,
            modified_at=candidate.note.modified_at,
            decision="ambiguous",
        )
        for candidate in candidates
    ]


def find_note_for_decision(notes: list[Note], decision: DecisionInput) -> Note:
    for note in notes:
        if (
            note.note_id == decision.note_id
            and note.content_hash == decision.content_hash
        ):
            return note
    raise RawWriteError(
        "Note not found for decision: "
        f"{decision.note_id} with content hash {decision.content_hash}"
    )


def export_approved(skill_dir: Path, decisions_path: Path) -> list[RawWriteResult]:
    config = load_config(skill_dir)
    decisions = load_decisions(decisions_path)
    notes = load_notes(config=config, skill_dir=skill_dir, include_content=True)

    results: list[RawWriteResult] = []
    for decision in decisions:
        if decision.decision != "yes":
            continue

        note = find_note_for_decision(notes, decision)
        results.append(write_raw_note(config, note))
    return results


def parse_note_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def filter_notes_by_scan_window(
    notes: list[Note],
    scan_window_days: int,
    now: datetime | None = None,
) -> tuple[list[Note], list[Exclusion]]:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    cutoff = current.timestamp() - (scan_window_days * 24 * 60 * 60)

    included: list[Note] = []
    excluded: list[Exclusion] = []

    for note in notes:
        modified = parse_note_datetime(note.modified_at)
        if modified is None:
            excluded.append(
                Exclusion(
                    note_id=note.note_id,
                    title=note.title,
                    reason="missing or unparsable modified_at",
                )
            )
            continue

        if modified.timestamp() < cutoff:
            excluded.append(
                Exclusion(
                    note_id=note.note_id,
                    title=note.title,
                    reason="outside scan window",
                )
            )
            continue

        included.append(note)

    return included, excluded


def main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "config",
            "state",
            "scan",
            "decisions-template",
            "export-approved",
            "finalize",
            "preflight",
        ],
    )
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--decisions")
    parser.add_argument("--include-content", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir)

    if args.command == "config":
        try:
            config: NotesConfig = load_config(skill_dir)
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2

        print_json(asdict(config))
        return 0

    if args.limit is not None and args.limit < 0:
        print("Error: --limit must be a positive integer", file=sys.stderr)
        return 2

    if args.command == "state":
        try:
            records: list[StateRecord] = load_state(skill_dir)
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5

        print_json([asdict(record) for record in records])
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
                    note_id=d.note_id,
                    content_hash=d.content_hash,
                    modified_at=d.modified_at,
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
                "last_scan_path": str(skill_dir / "last_scan.txt"),
            }
        )
        return 0

    if args.command == "scan":
        try:
            config = load_config(skill_dir)
            records = load_state(skill_dir)
            last_scan = load_last_scan(skill_dir)
            notes = load_notes(
                config=config, skill_dir=skill_dir, include_content=args.include_content
            )
            filters = scan_filters_from_config(config)
            result = scan_candidates_from_notes(
                notes=notes,
                records=records,
                scan_window_days=config.lookback_days,
                last_scan=last_scan,
                filters=filters,
                limit=args.limit,
            )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5
        except NotesClientError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3
        except NotImplementedError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3

        print_json(asdict(result))
        return 0

    if args.command == "decisions-template":
        if args.limit is not None and args.limit < 0:
            print("Error: --limit must be a positive integer", file=sys.stderr)
            return 2

        try:
            config = load_config(skill_dir)
            records = load_state(skill_dir)
            last_scan = load_last_scan(skill_dir)
            notes = load_notes(
                config=config,
                skill_dir=skill_dir,
                include_content=False,
            )
            filters = scan_filters_from_config(config)
            result = scan_candidates_from_notes(
                notes=notes,
                records=records,
                scan_window_days=config.lookback_days,
                last_scan=last_scan,
                filters=filters,
                limit=args.limit,
            )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5
        except NotesClientError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3
        except NotImplementedError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3

        decisions = decision_template_from_candidates(result.candidates)
        print_json([asdict(decision) for decision in decisions])
        return 0

    if args.command == "export-approved":
        if not args.decisions:
            print("Error: --decisions is required", file=sys.stderr)
            return 2

        try:
            results = export_approved(
                skill_dir=skill_dir,
                decisions_path=Path(args.decisions),
            )
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except StateError as exc:
            print(f"State error: {exc}", file=sys.stderr)
            return 5
        except NotesClientError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3
        except NotImplementedError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3
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

    if args.command == "preflight":
        try:
            config = load_config(skill_dir)
            result = preflight_notes(config=config, skill_dir=skill_dir)
        except ConfigError as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 2
        except NotesClientError as exc:
            print(f"Notes client error: {exc}", file=sys.stderr)
            return 3

        print_json(result)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
