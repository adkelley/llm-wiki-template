from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NotesConfig:
    lookback_days: int
    raw_output_dir: str
    database_path: str | None
    accounts: list[str]
    folders: list[str]
    include_tags: list[str]
    exclude_tags: list[str]
    max_notes: int
    wiki: str | None = None


@dataclass(frozen=True)
class StateRecord:
    note_id: str
    content_hash: str
    modified_at: str | None
    decision: str
    evaluated_at: str


@dataclass(frozen=True)
class DecisionInput:
    note_id: str
    content_hash: str
    modified_at: str | None
    decision: str


@dataclass(frozen=True)
class Note:
    note_id: str
    content_hash: str
    title: str | None
    account: str | None
    folder: str | None
    created_at: str | None
    modified_at: str | None
    plaintext: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    note: Note


@dataclass(frozen=True)
class Exclusion:
    note_id: str
    title: str | None
    reason: str


@dataclass(frozen=True)
class ScanFilters:
    accounts: list[str]
    folders: list[str]
    include_tags: list[str]
    exclude_tags: list[str]


@dataclass(frozen=True)
class ScanResult:
    ok: bool
    candidate_count: int
    candidates: list[Candidate]
    excluded_count: int
    excluded: list[Exclusion]
    scan_window_days: int
    filters: ScanFilters
    last_scan: str | None = None


@dataclass(frozen=True)
class RawWriteResult:
    path: str


VALID_DECISIONS = {
    "yes",
    "no",
    "ambiguous",
    "context_only",
}
