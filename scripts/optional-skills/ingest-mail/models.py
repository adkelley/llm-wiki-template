from __future__ import annotations

from dataclasses import dataclass


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
