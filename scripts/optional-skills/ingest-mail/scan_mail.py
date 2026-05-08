from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import tomllib


class ConfigError(Exception):
    pass


class CommandError(Exception):
    pass


class ParseError(Exception):
    pass


class StateError(Exception):
    pass


class RawWriteError(Exception):
    pass


@dataclass(frozen=True)
class MailConfig:
    lookback_days: int
    raw_output_dir: str
    accounts: list[str]
    folders: list[str]
    max_messages_per_folder: int
    max_thread_context_messages: int
    wiki: str | None = None


@dataclass(frozen=True)
class Address:
    name: str | None
    addr: str | None


@dataclass(frozen=True)
class Envelope:
    account: str
    folder: str
    id: str
    flags: list[str]
    subject: str | None
    from_addr: Address | None
    to_addrs: list[Address]
    date: str | None
    has_attachment: bool


@dataclass(frozen=True)
class Message:
    account: str
    folder: str
    id: str
    text: str


@dataclass(frozen=True)
class StateRecord:
    account: str
    folder: str
    envelope_id: str
    decision: str
    evaluated_at: str


@dataclass(frozen=True)
class Candidate:
    envelope: Envelope
    message: Message | None
    message_error: str | None
    thread_context: list[Envelope]


@dataclass(frozen=True)
class Exclusion:
    account: str
    folder: str
    envelope_id: str
    subject: str | None
    reason: str


@dataclass(frozen=True)
class ScanResult:
    ok: bool
    accounts: list[str]
    folders: list[str]
    candidate_count: int
    candidates: list[Candidate]
    excluded_count: int
    excluded: list[Exclusion]
    scan_window_days: int
    last_scan: str | None = None


@dataclass(frozen=True)
class DecisionInput:
    account: str
    folder: str
    envelope_id: str
    decision: str


@dataclass(frozen=True)
class RawWriteResult:
    path: str


VALID_DECISIONS = {"yes", "no", "ambiguous", "context_only"}
EXPORT_ENVELOPE_PAGE_SIZE_MULTIPLIER = 4


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def slugify(value: str | None) -> str:
    if not value:
        return "untitled"

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def date_prefix(value: str | None) -> str:
    if value is not None and re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return datetime.now(UTC).date().isoformat()


def normalized_thread_subject(subject: str | None) -> str:
    if not subject:
        return ""

    value = subject.strip().lower()
    while True:
        updated = re.sub(r"^(re|fw|fwd):\s*", "", value).strip()
        if updated == value:
            return value
        value = updated


def same_thread_subject(left: Envelope, right: Envelope) -> bool:
    left_subject = normalized_thread_subject(left.subject)
    right_subject = normalized_thread_subject(right.subject)
    return bool(left_subject and left_subject == right_subject)


def thread_context_for_envelope(
    envelope: Envelope,
    envelopes: list[Envelope],
    limit: int,
) -> list[Envelope]:
    return [
        other
        for other in envelopes
        if other.id != envelope.id and same_thread_subject(envelope, other)
    ][:limit]


def format_address(address: Address | None) -> str:
    if address is None:
        return ""
    if address.name and address.addr:
        return f"{address.name} <{address.addr}>"
    return address.name or address.addr or ""


def format_addresses(addresses: list[Address]) -> str:
    return ", ".join(value for value in (format_address(a) for a in addresses) if value)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate

    raise RawWriteError(f"Could not find available filename for {path}")


def require_int(data: dict, key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    if value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def require_str(data: dict, key: str) -> str:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def require_list_str(data: dict, key: str) -> list[str]:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, list):
        raise ConfigError(f"{key} must be a list")
    if not value:
        raise ConfigError(f"{key} list must not be empty")
    if not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return value


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


def load_config(skill_dir: Path) -> MailConfig:
    config_path = skill_dir / "config.toml"
    if not config_path.exists():
        raise ConfigError(f"Missing config file: {config_path}")

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    return MailConfig(
        lookback_days=require_int(data, "lookback_days"),
        raw_output_dir=require_str(data, "raw_output_dir"),
        accounts=require_list_str(data, "accounts"),
        folders=require_list_str(data, "folders"),
        max_messages_per_folder=require_int(data, "max_messages_per_folder"),
        max_thread_context_messages=require_int(data, "max_thread_context_messages"),
        wiki=require_str(data, "wiki") if "wiki" in data else None,
    )


def parse_account_names(output: str) -> list[str]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError("Account list was not valid JSON") from exc

    if not isinstance(data, list):
        raise ParseError("Account list output must be a JSON list")

    names: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Account list items must be JSON objects")

        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ParseError("Account list item is missing a string name")

        names.append(name)

    return names


def parse_folder_names(output: str) -> list[str]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError("Folder list was not valid JSON") from exc

    if not isinstance(data, list):
        raise ParseError("Folder list output must be a JSON list")

    names: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Folder list items must be JSON objects")

        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ParseError("Folder list item is missing a string name")

        names.append(name)

    return names


def parse_address(value: object) -> Address | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ParseError("Address must be a JSON object")

    name = value.get("name")
    addr = value.get("addr")

    if name is not None and not isinstance(name, str):
        raise ParseError("Name must be a string or null")
    if addr is not None and not isinstance(addr, str):
        raise ParseError("Address must be a string or null")

    return Address(name=name, addr=addr)


def parse_address_list(value: object) -> list[Address]:
    if value is None:
        return []
    if isinstance(value, dict):
        address = parse_address(value)
        return [] if address is None else [address]
    if isinstance(value, list):
        addresses: list[Address] = []
        for item in value:
            address = parse_address(item)
            if address is not None:
                addresses.append(address)
        return addresses
    raise ParseError("Address list must be an object, list, or null")


def parse_envelopes(output: str, account: str, folder: str) -> list[Envelope]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Envelope list output was not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ParseError("Envelope list output was not a list")

    envelopes: list[Envelope] = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Envelope list items must be JSON objects")

        envelope_id = item.get("id")
        if not isinstance(envelope_id, str) or not envelope_id:
            raise ParseError("Envelope item is missing a string id")

        flags = item.get("flags")
        if not isinstance(flags, list) or not all(
            isinstance(flag, str) for flag in flags
        ):
            raise ParseError("Envelope flags must be a list of strings")

        subject = item.get("subject")
        if subject is not None and not isinstance(subject, str):
            raise ParseError("Envelope subject must be a string or null")

        date = item.get("date")
        if date is not None and not isinstance(date, str):
            raise ParseError("Envelope date must be a string or null")

        has_attachment = item.get("has_attachment")
        if not isinstance(has_attachment, bool):
            raise ParseError("Envelope has_attachment must be a boolean")

        envelopes.append(
            Envelope(
                account=account,
                folder=folder,
                id=envelope_id,
                flags=flags,
                subject=subject,
                date=date,
                from_addr=parse_address(item.get("from")),
                to_addrs=parse_address_list(item.get("to")),
                has_attachment=has_attachment,
            )
        )

    return envelopes


def parse_message(output: str, account: str, folder: str, message_id: str) -> Message:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError("Message read output was not valid JSON") from exc

    if not isinstance(data, str):
        raise ParseError("Message read output must be a JSON string")

    return Message(
        account=account,
        folder=folder,
        id=message_id,
        text=data,
    )


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


def parse_utc_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")

    return parsed.astimezone(UTC)


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


def scan_window_after_date(window_days: int, now: datetime | None = None) -> str:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    cutoff = current.date() - timedelta(days=window_days)
    return cutoff.isoformat()


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


def raw_output_dir(config: MailConfig, base_dir: Path) -> Path:
    output_dir = Path(config.raw_output_dir)
    if output_dir.is_absolute():
        return output_dir
    return base_dir / output_dir


def raw_filename(envelope: Envelope) -> str:
    date = date_prefix(envelope.date)
    slug = slugify(envelope.subject)
    digest = short_hash(f"{envelope.account}\t{envelope.folder}\t{envelope.id}")
    return f"{date}-email-{slug}-{digest}.md"


def raw_thread_context_text(envelopes: list[Envelope]) -> str:
    if not envelopes:
        return "None captured"

    lines: list[str] = []
    for envelope in envelopes:
        lines.extend(
            [
                f"- Envelope ID: {envelope.id}",
                f"  Subject: {envelope.subject or ''}",
                f"  From: {format_address(envelope.from_addr)}",
                f"  To: {format_addresses(envelope.to_addrs)}",
                f"  Date: {envelope.date or ''}",
            ]
        )
    return "\n".join(lines)


def raw_message_text(candidate: Candidate) -> str:
    if candidate.message is None:
        raise RawWriteError("Cannot write raw source without message text")

    envelope = candidate.envelope
    return "\n".join(
        [
            f"Subject: {envelope.subject or ''}",
            f"Envelope ID: {envelope.id}",
            "Source: Himalaya",
            f"Account: {envelope.account}",
            f"Folder: {envelope.folder}",
            f"From: {format_address(envelope.from_addr)}",
            f"To: {format_addresses(envelope.to_addrs)}",
            f"Date: {envelope.date or ''}",
            "Capture method: Himalaya CLI",
            "",
            candidate.message.text,
            "",
            "---",
            "",
            "Thread context used for evaluation:",
            "",
            raw_thread_context_text(candidate.thread_context),
            "",
        ]
    )


def write_raw_candidate(
    config: MailConfig, candidate: Candidate, base_dir: Path | None = None
) -> RawWriteResult:
    base = base_dir if base_dir is not None else Path.cwd()
    output_dir = raw_output_dir(config, base)
    output_dir.mkdir(parents=True, exist_ok=True)

    target = unique_path(output_dir / raw_filename(candidate.envelope))
    target.write_text(raw_message_text(candidate), encoding="utf-8")
    return RawWriteResult(path=str(target))


def missing_items(configured: list[str], available: list[str]) -> list[str]:
    available_set = set(available)
    return [item for item in configured if item not in available_set]


def run_command(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"Command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise CommandError(f"Command failed: {' '.join(args)}\n{message}") from exc

    return result.stdout


def himalaya_version() -> str:
    return run_command(["himalaya", "--version"]).strip()


def himalaya_account_list() -> list[str]:
    output = run_command(["himalaya", "account", "list", "--output", "json"]).strip()
    return parse_account_names(output)


def himalaya_folder_list(account: str) -> list[str]:
    output = run_command(
        [
            "himalaya",
            "folder",
            "list",
            "--account",
            account,
            "--output",
            "json",
        ]
    ).strip()
    return parse_folder_names(output)


def envelope_list_query(window_days: int | None = None) -> list[str]:
    if window_days is not None:
        return [
            "after",
            scan_window_after_date(window_days),
            "order",
            "by",
            "date",
            "desc",
        ]
    return []


def himalaya_envelope_list(
    config: MailConfig,
    account: str,
    folder: str,
    window_days: int | None = None,
    page_size: int | None = None,
) -> list[Envelope]:
    effective_page_size = page_size or config.max_messages_per_folder

    output = run_command(
        [
            "himalaya",
            "envelope",
            "list",
            "--account",
            account,
            "--folder",
            folder,
            "--page-size",
            str(effective_page_size),
            "--output",
            "json",
            *envelope_list_query(window_days),
        ]
    ).strip()
    return parse_envelopes(output, account, folder)


def himalaya_message_read(account: str, folder: str, message_id: str) -> Message:
    output = run_command(
        [
            "himalaya",
            "message",
            "read",
            "--account",
            account,
            "--folder",
            folder,
            "--preview",
            "--output",
            "json",
            message_id,
        ]
    )
    return parse_message(output, account, folder, message_id)


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
