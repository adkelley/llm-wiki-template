from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from errors import RawWriteError
from models import Address, Candidate, Envelope, MailConfig, RawWriteResult


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
