from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from errors import NotesClientError
from models import Note, NotesConfig


def normalize_tags(tags: object) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        return []
    return sorted(str(tag) for tag in tags if tag)


def note_content_hash(
    title: str | None, plaintext: str | None, tags: list[str] | None = None
) -> str:
    payload = {
        "title": title or "",
        "plaintext": plaintext or "",
        "tags": sorted(tags or []),
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def iso_or_none(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def attr_name(value: object | None) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    return str(name) if name is not None else None


def folder_path(note: object) -> str | None:
    get_folder_path = getattr(note, "get_folder_path", None)
    if callable(get_folder_path):
        value = get_folder_path()
        return str(value) if value is not None else None
    return attr_name(getattr(note, "folder", None))


def note_identity(note: object) -> str:
    for key in ("applescript_id", "uuid", "note_id", "id"):
        value = getattr(note, key, None)
        if value:
            return str(value)
    raise NotesClientError("Note is missing a usable identifier")


def parser_note_to_note(note: object, include_content: bool) -> Note:
    title = getattr(note, "title", None)
    content = getattr(note, "content", None) or ""
    tags = normalize_tags(getattr(note, "tags", None))
    return Note(
        note_id=note_identity(note),
        content_hash=note_content_hash(title, content, tags),
        title=str(title) if title is not None else None,
        account=attr_name(getattr(note, "account", None)),
        folder=folder_path(note),
        created_at=iso_or_none(getattr(note, "creation_date", None)),
        modified_at=iso_or_none(getattr(note, "modification_date", None)),
        plaintext=content if include_content else None,
        tags=tags,
    )


def note_sort_timestamp(note: Note) -> float:
    if not note.modified_at:
        return 0
    try:
        parsed = datetime.fromisoformat(note.modified_at)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def sort_notes_for_scan(notes: list[Note]) -> list[Note]:
    return sorted(notes, key=note_sort_timestamp, reverse=True)


def limit_notes_for_scan(notes: list[Note], limit: int) -> list[Note]:
    return sort_notes_for_scan(notes)[:limit]


def note_is_recently_deleted(note: Note) -> bool:
    return (note.folder or "").split("/")[-1].lower() == "recently deleted"


def exclude_recently_deleted_notes(notes: list[Note]) -> list[Note]:
    return [note for note in notes if not note_is_recently_deleted(note)]


def normalized_tag_set(tags: list[str]) -> set[str]:
    return {tag.lower() for tag in tags}


def note_matches_include_tags(note: Note, include_tags: list[str]) -> bool:
    if not include_tags:
        return True
    return bool(normalized_tag_set(note.tags) & normalized_tag_set(include_tags))


def note_matches_exclude_tags(note: Note, exclude_tags: list[str]) -> bool:
    if not exclude_tags:
        return False
    return bool(normalized_tag_set(note.tags) & normalized_tag_set(exclude_tags))


def note_account_matches(note: Note, accounts: list[str]) -> bool:
    if not accounts:
        return True
    if note.account is None:
        return False

    allowed_accounts = {account.lower() for account in accounts}
    return note.account.lower() in allowed_accounts


def note_folder_matches(note: Note, folders: list[str]) -> bool:
    if not folders:
        return True
    if note.folder is None:
        return False

    allowed_folders = {folder.lower() for folder in folders}
    folder = note.folder.lower()
    leaf_folder = note.folder.split("/")[-1].lower()
    return folder in allowed_folders or leaf_folder in allowed_folders


def filter_notes_by_config(notes: list[Note], config: NotesConfig) -> list[Note]:
    kept: list[Note] = []

    for note in notes:
        if config.accounts and not note_account_matches(note, config.accounts):
            continue

        if config.folders and not note_folder_matches(note, config.folders):
            continue

        if not config.folders and note_is_recently_deleted(note):
            continue

        if not note_matches_include_tags(note, config.include_tags):
            continue

        if note_matches_exclude_tags(note, config.exclude_tags):
            continue

        kept.append(note)

    return limit_notes_for_scan(kept, config.max_notes)


def load_notes(
    config: NotesConfig, skill_dir: Path, include_content: bool = False
) -> list[Note]:
    _ = skill_dir
    try:
        from apple_notes_parser import AppleNotesParser
        from apple_notes_parser.exceptions import AppleNotesParserError
    except ImportError as exc:
        raise NotesClientError(
            "Missing optional dependency: apple-notes-parser. "
            "Install it for the Python used to run this skill with: "
            "python3 -m pip install apple-notes-parser"
        ) from exc

    try:
        parser = AppleNotesParser(config.database_path)
        parser.load_data()
        notes = [
            parser_note_to_note(note, include_content=include_content)
            for note in parser.notes
        ]
    except AppleNotesParserError as exc:
        raise NotesClientError(
            "Could not read Apple Notes database. "
            "On macOS, grant Full Disk Access to the terminal or app running "
            "this Python process. "
            f"Original error: {str(exc)}"
        ) from exc

    return filter_notes_by_config(notes, config)


def preflight_notes(config: NotesConfig, skill_dir: Path) -> dict[str, object]:
    try:
        import apple_notes_parser  # noqa: F401
    except ImportError as exc:
        raise NotesClientError(
            "Missing optional dependency: apple-notes-parser. "
            "Install it for the Python used to run this skill with: "
            "python3 -m pip install apple-notes-parser"
        ) from exc

    return {
        "ok": True,
        "backend": "apple-notes-parser",
        "database_path": config.database_path or "auto",
    }
