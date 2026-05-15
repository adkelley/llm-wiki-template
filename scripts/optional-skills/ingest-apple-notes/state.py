from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from errors import StateError
from models import VALID_DECISIONS, DecisionInput, StateRecord


def state_path(skill_dir: Path) -> Path:
    return skill_dir / "state.jsonl"


def last_scan_path(skill_dir: Path) -> Path:
    return skill_dir / "last_scan.txt"


def note_version_key(note_id: str, content_hash: str) -> tuple[str, str]:
    return (note_id, content_hash)


def evaluated_keys(records: list[StateRecord]) -> set[tuple[str, str]]:
    return {note_version_key(r.note_id, r.content_hash) for r in records}


def load_state(skill_dir: Path) -> list[StateRecord]:
    path = state_path(skill_dir)
    if not path.exists():
        return []

    records: list[StateRecord] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            records.append(
                StateRecord(
                    note_id=data["note_id"],
                    content_hash=data["content_hash"],
                    modified_at=data["modified_at"],
                    decision=data["decision"],
                    evaluated_at=data["evaluated_at"],
                )
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise StateError(
                f"Malformed state.jsonl line {line_number}: {exc}"
            ) from exc
    return records


def append_state_records(skill_dir: Path, records: list[StateRecord]) -> None:
    if not records:
        return
    path = state_path(skill_dir)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def load_last_scan(skill_dir: Path) -> str | None:
    path = last_scan_path(skill_dir)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def write_last_scan(skill_dir: Path, timestamp: str) -> None:
    path = last_scan_path(skill_dir)
    path.write_text(timestamp + "\n", encoding="utf-8")


def load_decisions(path: Path) -> list[DecisionInput]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Failed to load decisions file {path}: {exc}") from exc

    if not isinstance(data, list):
        raise StateError("Decisions file must contain a JSON array")

    decisions: list[DecisionInput] = []
    for index, item in enumerate(data, 1):
        try:
            decision = DecisionInput(
                note_id=item["note_id"],
                content_hash=item["content_hash"],
                modified_at=item["modified_at"],
                decision=item["decision"],
            )
        except (KeyError, TypeError) as exc:
            raise StateError(f"Malformed decision at index {index}: {exc}") from exc

        if decision.decision not in VALID_DECISIONS:
            raise StateError(
                f"Invalid decision for note {decision.note_id}: {decision.decision}"
            )

        decisions.append(decision)

    return decisions
