from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from errors import StateError
from models import VALID_DECISIONS, DecisionInput, Envelope, StateRecord


def last_scan_path(skill_dir: Path) -> Path:
    return skill_dir / "last_scan.txt"


def load_last_scan(skill_dir: Path) -> str | None:
    path = last_scan_path(skill_dir)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def write_last_scan(skill_dir: Path, timestamp: str) -> None:
    path = last_scan_path(skill_dir)
    path.write_text(timestamp + "\n", encoding="utf-8")


def parse_state_record(data: object, line_number: int) -> StateRecord:
    if not isinstance(data, dict):
        raise StateError(f"state.jsonl line {line_number} must be a JSON object")

    account = data.get("account")
    folder = data.get("folder")
    envelope_id = data.get("envelope_id")
    decision = data.get("decision")
    evaluated_at = data.get("evaluated_at")

    if not isinstance(account, str) or not account:
        raise StateError(f"state.jsonl line {line_number}: account must be a string")
    if not isinstance(folder, str) or not folder:
        raise StateError(f"state.jsonl line {line_number}: folder must be a string")
    if not isinstance(envelope_id, str) or not envelope_id:
        raise StateError(
            f"state.jsonl line {line_number}: envelope_id must be a string"
        )
    if not isinstance(decision, str) or decision not in VALID_DECISIONS:
        raise StateError(f"state.jsonl line {line_number}: invalid decision")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise StateError(
            f"state.jsonl line {line_number}: evaluated_at must be a string"
        )

    return StateRecord(
        account=account,
        folder=folder,
        envelope_id=envelope_id,
        decision=decision,
        evaluated_at=evaluated_at,
    )


def parse_decision_input(data: object, index: int) -> DecisionInput:
    label = f"decision #{index}"

    if not isinstance(data, dict):
        raise StateError(f"{label} must be a JSON object")

    account = data.get("account")
    folder = data.get("folder")
    envelope_id = data.get("envelope_id")
    decision = data.get("decision")

    if not isinstance(account, str) or not account:
        raise StateError(f"{label}: account must be a string")
    if not isinstance(folder, str) or not folder:
        raise StateError(f"{label}: folder must be a string")
    if not isinstance(envelope_id, str) or not envelope_id:
        raise StateError(f"{label}: envelope_id must be a string")
    if not isinstance(decision, str) or decision not in VALID_DECISIONS:
        raise StateError(f"{label}: invalid decision")

    return DecisionInput(
        account=account,
        folder=folder,
        envelope_id=envelope_id,
        decision=decision,
    )


def load_decisions(path: Path) -> list[DecisionInput]:
    if not path.exists():
        raise StateError(f"Missing decisions file: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Decisions file was not valid JSON: {path}") from exc

    if not isinstance(data, list):
        raise StateError(f"Decisions file {path} must be a JSON array")

    return [
        parse_decision_input(item, index) for index, item in enumerate(data, start=1)
    ]


def load_state(skill_dir: Path) -> list[StateRecord]:
    state_path = skill_dir / "state.jsonl"
    if not state_path.exists():
        return []

    records: list[StateRecord] = []
    with state_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise StateError(
                    f"state.jsonl line {line_number}: was not valid JSON"
                ) from exc
            records.append(parse_state_record(data, line_number))

    return records


def append_state_records(skill_dir: Path, records: list[StateRecord]) -> None:
    state_path = skill_dir / "state.jsonl"
    with state_path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), sort_keys=True))
            f.write("\n")


MessageKey = tuple[str, str, str]


def state_key(record: StateRecord) -> MessageKey:
    return (record.account, record.folder, record.envelope_id)


def envelope_key(envelope: Envelope) -> MessageKey:
    return (envelope.account, envelope.folder, envelope.id)


def evaluated_keys(records: list[StateRecord]) -> set[MessageKey]:
    return {state_key(record) for record in records}


def filter_new_envelopes(
    envelopes: list[Envelope],
    records: list[StateRecord],
) -> list[Envelope]:
    seen = evaluated_keys(records)
    return [envelope for envelope in envelopes if envelope_key(envelope) not in seen]
