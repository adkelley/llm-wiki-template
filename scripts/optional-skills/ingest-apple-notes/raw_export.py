from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from errors import RawWriteError
from models import Note, NotesConfig, RawWriteResult


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


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate

    raise RawWriteError(f"Could not find available filename for {path}")


def raw_output_dir(config: NotesConfig, base_dir: Path) -> Path:
    output_dir = Path(config.raw_output_dir)
    if output_dir.is_absolute():
        return output_dir
    return base_dir / output_dir


def raw_filename(note: Note) -> str:
    date = date_prefix(note.modified_at)
    slug = slugify(note.title)
    digest = short_hash(note.note_id)
    return f"{date}-note-{slug}-{digest}.md"


def raw_note_text(note: Note) -> str:
    if note.plaintext is None:
        raise RawWriteError("Cannot write raw source without note plaintext")

    return "\n".join(
        [
            f"Title: {note.title or ''}",
            f"Note ID: {note.note_id}",
            f"Content hash: {note.content_hash}",
            "Source: Apple Notes",
            f"Account: {note.account or ''}",
            f"Folder: {note.folder or ''}",
            f"Tags: {', '.join(note.tags)}",
            f"Created: {note.created_at or ''}",
            f"Modified: {note.modified_at or ''}",
            "Capture method: apple-notes-parser",
            "",
            note.plaintext,
            "",
        ]
    )


def write_raw_note(
    config: NotesConfig,
    note: Note,
    base_dir: Path | None = None,
) -> RawWriteResult:
    base = base_dir if base_dir is not None else Path.cwd()
    output_dir = raw_output_dir(config, base)
    output_dir.mkdir(parents=True, exist_ok=True)

    target = unique_path(output_dir / raw_filename(note))
    target.write_text(raw_note_text(note), encoding="utf-8")
    return RawWriteResult(path=str(target))
