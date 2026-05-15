from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scan_notes.py"
SKILL_DIR = SCRIPT_PATH.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

# import models  # noqa: E402

SPEC = importlib.util.spec_from_file_location("scan_notes", SCRIPT_PATH)
assert SPEC is not None, "Failed to load scan_notes module"
assert SPEC.loader is not None, "Failed to load scan_notes module"

scan_notes = importlib.util.module_from_spec(SPEC)
sys.modules["scan_notes"] = scan_notes
SPEC.loader.exec_module(scan_notes)


class ScanNotesTest(unittest.TestCase):
    def write_config(self, skill_dir: Path) -> None:
        (skill_dir / "config.toml").write_text(
            "\n".join(
                [
                    "lookback_days = 7",
                    'raw_output_dir = "raw/"',
                    "accounts = []",
                    "folders = []",
                    "include_tags = []",
                    "exclude_tags = []",
                    "max_notes = 25",
                    'database_path = ""',
                    'wiki = "example-wiki"',
                ]
            ),
            encoding="utf-8",
        )

    class FakeNamed:
        def __init__(self, name: str):
            self.name = name

    class FakeParserNote:
        def __init__(
            self,
            *,
            applescript_id: str | None = None,
            uuid: str | None = None,
            note_id: int | None = None,
            id: int | None = None,
            title: str | None = "Research",
            content: str | None = "body",
            tags: list[str] | None = None,
            creation_date: object | None = "2026-05-11T09:00:00Z",
            modification_date: object | None = "2026-05-12T09:00:00Z",
            account: object | None = None,
            folder: object | None = None,
            folder_path: str | None = "Root/Work",
        ):
            self.applescript_id = applescript_id
            self.uuid = uuid
            self.note_id = note_id
            self.id = id
            self.title = title
            self.content = content
            self.tags = tags if tags is not None else []
            self.creation_date = creation_date
            self.modification_date = modification_date
            self.account = account
            self.folder = folder
            self._folder_path = folder_path

        def get_folder_path(self) -> str | None:
            return self._folder_path

    def test_load_config_reads_toml_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        "accounts = []",
                        "folders = []",
                        "include_tags = []",
                        "exclude_tags = []",
                        "max_notes = 3",
                        'database_path = ""',
                        'wiki = "example-wiki"',
                    ]
                ),
                encoding="utf-8",
            )

            config = scan_notes.load_config(skill_dir)
        self.assertEqual(config.lookback_days, 14)
        self.assertEqual(config.raw_output_dir, "raw/")
        self.assertEqual(config.accounts, [])
        self.assertEqual(config.folders, [])
        self.assertEqual(config.include_tags, [])
        self.assertEqual(config.exclude_tags, [])
        self.assertEqual(config.max_notes, 3)
        self.assertIsNone(config.database_path)
        self.assertEqual(config.wiki, "example-wiki")

    def test_load_state_returns_empty_list_when_state_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            state = scan_notes.load_state(skill_dir)
        self.assertEqual(state, [])

    def test_load_state_reads_jsonl_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            (skill_dir / "state.jsonl").write_text(
                (
                    '{"decision":"no",'
                    '"evaluated_at":"2026-05-11T16:30:00Z",'
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-10T09:15:00Z",'
                    '"note_id":"x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567"}\n'
                ),
                encoding="utf-8",
            )
            records = scan_notes.load_state(skill_dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].note_id, "x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567"
        )
        self.assertEqual(records[0].content_hash, "abc123")
        self.assertEqual(records[0].modified_at, "2026-05-10T09:15:00Z")
        self.assertEqual(records[0].decision, "no")
        self.assertEqual(records[0].evaluated_at, "2026-05-11T16:30:00Z")

    def test_load_state_rejects_malformed_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            (skill_dir / "state.jsonl").write_text(
                (
                    '{"decision""no",'  # missing colon
                    '"evaluated_at":"2026-05-11T16:30:00Z",'
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-10T09:15:00Z",'
                    '"note_id":"x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567"}\n'
                ),
                encoding="utf-8",
            )
            with self.assertRaises(scan_notes.StateError):
                scan_notes.load_state(skill_dir)

    def test_append_state_records_adds_jsonl_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            (skill_dir / "state.jsonl").write_text(
                (
                    '{"decision":"no",'
                    '"evaluated_at":"2026-05-11T16:30:00Z",'
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-10T09:15:00Z",'
                    '"note_id":"x-coredata://A1B2C3D4-E5F6-7890-1234-ABCDE1234567"}\n'
                ),
                encoding="utf-8",
            )
            records = scan_notes.load_state(skill_dir)
            self.assertEqual(len(records), 1)
            record = [
                scan_notes.StateRecord(
                    decision="yes",
                    evaluated_at="2026-05-12T10:45:00Z",
                    content_hash="abc123",
                    modified_at="2026-05-11T15:00:00Z",
                    note_id="x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789",
                )
            ]
            scan_notes.append_state_records(skill_dir, record)
            records = scan_notes.load_state(skill_dir)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[1].decision, "yes")
            self.assertEqual(records[1].evaluated_at, "2026-05-12T10:45:00Z")
            self.assertEqual(records[1].content_hash, "abc123")
            self.assertEqual(records[1].modified_at, "2026-05-11T15:00:00Z")
            self.assertEqual(
                records[1].note_id, "x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789"
            )

    def test_load_decisions_reads_json_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            path = skill_dir / "decisions.jsonl"
            path.write_text(
                (
                    "["
                    '{"decision":"yes",'
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-11T15:00:00Z",'
                    '"note_id":"x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789"}'
                    "]"
                ),
                encoding="utf-8",
            )
            decisions = scan_notes.load_decisions(path)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0].decision, "yes")
            self.assertEqual(decisions[0].content_hash, "abc123")
            self.assertEqual(decisions[0].modified_at, "2026-05-11T15:00:00Z")
            self.assertEqual(
                decisions[0].note_id,
                "x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789",
            )

    def test_load_decisions_rejects_invalid_decision_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            path = skill_dir / "decisions.jsonl"
            path.write_text(
                (
                    "["
                    '{"decision":"",'  # cannot be blank
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-11T15:00:00Z",'
                    '"note_id":"x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789"}'
                    "]"
                ),
                encoding="utf-8",
            )
            self.assertRaises(scan_notes.StateError, scan_notes.load_decisions, path)

    def test_load_last_scan_reads_written_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            scan_notes.write_last_scan(skill_dir, "2026-05-11T15:00:00Z")
            last_scan = scan_notes.load_last_scan(skill_dir)
            self.assertEqual(last_scan, "2026-05-11T15:00:00Z")

    def test_state_command_prints_empty_state(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir: Path = Path(tmp)
            with redirect_stdout(stdout):
                code = scan_notes.main(["state", "--skill-dir", str(skill_dir)])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), [])

    def test_finalize_command_appends_state_and_writes_last_scan(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            decisions_path = skill_dir / "decisions.json"
            decisions_path.write_text(
                (
                    "["
                    '{"decision":"yes",'
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-11T15:00:00Z",'
                    '"note_id":"x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789"}'
                    "]"
                ),
                encoding="utf-8",
            )

            with redirect_stdout(stdout):
                code = scan_notes.main(
                    [
                        "finalize",
                        "--skill-dir",
                        str(skill_dir),
                        "--decisions",
                        str(decisions_path),
                    ]
                )

            records = scan_notes.load_state(skill_dir)
            last_scan = scan_notes.load_last_scan(skill_dir)

        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["appended"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].decision, "yes")
        self.assertEqual(records[0].content_hash, "abc123")
        self.assertEqual(records[0].modified_at, "2026-05-11T15:00:00Z")
        self.assertEqual(
            records[0].note_id,
            "x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789",
        )
        self.assertIsNotNone(last_scan)
        self.assertEqual(records[0].evaluated_at, last_scan)

    def test_finalize_command_returns_5_for_invalid_decision(self):
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            decisions_path = skill_dir / "decisions.json"
            decisions_path.write_text(
                (
                    "["
                    '{"decision":"maybe",'
                    '"content_hash":"abc123",'
                    '"modified_at":"2026-05-11T15:00:00Z",'
                    '"note_id":"x-coredata://B2C3D4E5-F6G7-8901-2345-BCDE23456789"}'
                    "]"
                ),
                encoding="utf-8",
            )

            with redirect_stderr(stderr):
                code = scan_notes.main(
                    [
                        "finalize",
                        "--skill-dir",
                        str(skill_dir),
                        "--decisions",
                        str(decisions_path),
                    ]
                )

            records = scan_notes.load_state(skill_dir)
            last_scan = scan_notes.load_last_scan(skill_dir)

        self.assertEqual(code, 5)
        self.assertIn("State error:", stderr.getvalue())
        self.assertEqual(records, [])
        self.assertIsNone(last_scan)

    def test_note_content_hash_is_stable_for_same_content(self):
        first = scan_notes.note_content_hash("Research note", "Some body text")
        second = scan_notes.note_content_hash("Research note", "Some body text")

        self.assertEqual(first, second)

    def test_note_content_hash_changes_when_plaintext_changes(self):
        first = scan_notes.note_content_hash("Research note", "Some body text")
        second = scan_notes.note_content_hash("Research note", "Some updated body text")

        self.assertNotEqual(first, second)

    def test_note_content_hash_ignores_modified_at(self):
        first = scan_notes.note_content_hash("Research note", "Some body text")
        second = scan_notes.note_content_hash("Research note", "Some body text")

        self.assertEqual(first, second)

    def test_note_content_hash_changes_when_tags_change(self):
        first = scan_notes.note_content_hash("Research note", "Some body text", [])
        second = scan_notes.note_content_hash(
            "Research note", "Some body text", ["wiki"]
        )

        self.assertNotEqual(first, second)

    def test_note_content_hash_sorts_tags(self):
        first = scan_notes.note_content_hash(
            "Research note", "Some body text", ["wiki", "research"]
        )
        second = scan_notes.note_content_hash(
            "Research note", "Some body text", ["research", "wiki"]
        )

        self.assertEqual(first, second)

    def test_parser_note_to_note_prefers_applescript_id(self):
        parser_note = self.FakeParserNote(
            applescript_id="x-coredata://note-1",
            uuid="uuid-1",
            id=123,
            account=self.FakeNamed("iCloud"),
            folder=self.FakeNamed("Work"),
        )

        note = scan_notes.parser_note_to_note(parser_note, include_content=False)

        self.assertEqual(note.note_id, "x-coredata://note-1")

    def test_parser_note_to_note_falls_back_to_uuid_then_id(self):
        uuid_note = self.FakeParserNote(
            applescript_id=None,
            uuid="uuid-1",
            id=123,
        )
        id_note = self.FakeParserNote(
            applescript_id=None,
            uuid=None,
            id=123,
        )

        self.assertEqual(
            scan_notes.parser_note_to_note(uuid_note, include_content=False).note_id,
            "uuid-1",
        )
        self.assertEqual(
            scan_notes.parser_note_to_note(id_note, include_content=False).note_id,
            "123",
        )

    def test_parser_note_to_note_raises_when_identifier_missing(self):
        parser_note = self.FakeParserNote(
            applescript_id=None,
            uuid=None,
            note_id=None,
            id=None,
        )

        with self.assertRaises(scan_notes.NotesClientError):
            scan_notes.parser_note_to_note(parser_note, include_content=False)

    def test_parser_note_to_note_maps_dates_account_folder_and_hash(self):
        parser_note = self.FakeParserNote(
            applescript_id="note-1",
            title="Research",
            content="body",
            tags=["wiki", "research"],
            creation_date="2026-05-11T09:00:00Z",
            modification_date="2026-05-12T09:00:00Z",
            account=self.FakeNamed("iCloud"),
            folder=self.FakeNamed("Work"),
            folder_path="Root/Work",
        )

        note = scan_notes.parser_note_to_note(parser_note, include_content=False)

        self.assertEqual(note.title, "Research")
        self.assertEqual(note.account, "iCloud")
        self.assertEqual(note.folder, "Root/Work")
        self.assertEqual(note.tags, ["research", "wiki"])
        self.assertEqual(note.created_at, "2026-05-11T09:00:00Z")
        self.assertEqual(note.modified_at, "2026-05-12T09:00:00Z")
        self.assertEqual(
            note.content_hash,
            scan_notes.note_content_hash("Research", "body", ["research", "wiki"]),
        )

    def test_parser_note_to_note_omits_plaintext_without_include_content(self):
        parser_note = self.FakeParserNote(applescript_id="note-1", content="body")

        note = scan_notes.parser_note_to_note(parser_note, include_content=False)

        self.assertIsNone(note.plaintext)

    def test_parser_note_to_note_includes_plaintext_with_include_content(self):
        parser_note = self.FakeParserNote(applescript_id="note-1", content="body")

        note = scan_notes.parser_note_to_note(parser_note, include_content=True)

        self.assertEqual(note.plaintext, "body")

    def test_sort_notes_for_scan_orders_newer_notes_first(self):
        old_note = scan_notes.Note(
            note_id="old-note",
            content_hash="hash-old",
            title="Old",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-05-10T09:00:00Z",
            plaintext=None,
        )
        new_note = scan_notes.Note(
            note_id="new-note",
            content_hash="hash-new",
            title="New",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
        )

        sorted_notes = scan_notes.sort_notes_for_scan([old_note, new_note])

        self.assertEqual(sorted_notes, [new_note, old_note])

    def test_sort_notes_for_scan_places_missing_or_unparsable_dates_last(self):
        dated_note = scan_notes.Note(
            note_id="dated-note",
            content_hash="hash-dated",
            title="Dated",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
        )
        missing_date_note = scan_notes.Note(
            note_id="missing-date-note",
            content_hash="hash-missing",
            title="Missing Date",
            account=None,
            folder=None,
            created_at=None,
            modified_at=None,
            plaintext=None,
        )
        bad_date_note = scan_notes.Note(
            note_id="bad-date-note",
            content_hash="hash-bad",
            title="Bad Date",
            account=None,
            folder=None,
            created_at=None,
            modified_at="not a date",
            plaintext=None,
        )

        sorted_notes = scan_notes.sort_notes_for_scan(
            [missing_date_note, dated_note, bad_date_note]
        )

        self.assertEqual(sorted_notes[0], dated_note)
        self.assertEqual(
            {note.note_id for note in sorted_notes[1:]},
            {"missing-date-note", "bad-date-note"},
        )

    def test_limit_notes_for_scan_applies_limit_after_sorting(self):
        old_note = scan_notes.Note(
            note_id="old-note",
            content_hash="hash-old",
            title="Old",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-05-10T09:00:00Z",
            plaintext=None,
        )
        new_note = scan_notes.Note(
            note_id="new-note",
            content_hash="hash-new",
            title="New",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
        )

        limited_notes = scan_notes.limit_notes_for_scan([old_note, new_note], limit=1)

        self.assertEqual(limited_notes, [new_note])

    def test_exclude_recently_deleted_notes_removes_trash_folder(self):
        active_note = scan_notes.Note(
            note_id="active-note",
            content_hash="hash-active",
            title="Active",
            account=None,
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
        )
        deleted_note = scan_notes.Note(
            note_id="deleted-note",
            content_hash="hash-deleted",
            title="Deleted",
            account=None,
            folder="Recently Deleted",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
        )

        notes = scan_notes.exclude_recently_deleted_notes([active_note, deleted_note])

        self.assertEqual(notes, [active_note])

    def test_filter_notes_by_config_excludes_recently_deleted_by_default(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=[],
            folders=[],
            include_tags=[],
            exclude_tags=[],
            max_notes=25,
            wiki="example-wiki",
        )
        active_note = scan_notes.Note(
            note_id="active-note",
            content_hash="hash-active",
            title="Active",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
        )
        deleted_note = scan_notes.Note(
            note_id="deleted-note",
            content_hash="hash-deleted",
            title="Deleted",
            account="iCloud",
            folder="Recently Deleted",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
        )

        notes = scan_notes.filter_notes_by_config([deleted_note, active_note], config)

        self.assertEqual(notes, [active_note])

    def test_filter_notes_by_config_includes_recently_deleted_when_explicit(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=[],
            folders=["Recently Deleted"],
            include_tags=[],
            exclude_tags=[],
            max_notes=25,
            wiki="example-wiki",
        )
        deleted_note = scan_notes.Note(
            note_id="deleted-note",
            content_hash="hash-deleted",
            title="Deleted",
            account="iCloud",
            folder="Recently Deleted",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
        )

        notes = scan_notes.filter_notes_by_config([deleted_note], config)

        self.assertEqual(notes, [deleted_note])

    def test_note_matches_include_tags_returns_true_when_include_tags_empty(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Research",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
            tags=[],
        )

        self.assertTrue(scan_notes.note_matches_include_tags(note, []))

    def test_note_matches_exclude_tags_returns_false_when_exclude_tags_empty(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Research",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
            tags=["epiphan"],
        )

        self.assertFalse(scan_notes.note_matches_exclude_tags(note, []))

    def test_filter_notes_by_config_keeps_note_matching_include_tag(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=[],
            folders=[],
            include_tags=["epiphan"],
            exclude_tags=[],
            max_notes=25,
            wiki="example-wiki",
        )
        matching_note = scan_notes.Note(
            note_id="matching-note",
            content_hash="hash-matching",
            title="Epiphan Research",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
            tags=["epiphan", "gca"],
        )
        other_note = scan_notes.Note(
            note_id="other-note",
            content_hash="hash-other",
            title="Bash Scripting",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
            tags=["programming"],
        )

        notes = scan_notes.filter_notes_by_config([matching_note, other_note], config)

        self.assertEqual(notes, [matching_note])

    def test_filter_notes_by_config_matches_include_tags_case_insensitively(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=[],
            folders=[],
            include_tags=["Epiphan"],
            exclude_tags=[],
            max_notes=25,
            wiki="example-wiki",
        )
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Epiphan Research",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
            tags=["epiphan"],
        )

        notes = scan_notes.filter_notes_by_config([note], config)

        self.assertEqual(notes, [note])

    def test_filter_notes_by_config_drops_note_matching_exclude_tag(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=[],
            folders=[],
            include_tags=[],
            exclude_tags=["personal"],
            max_notes=25,
            wiki="example-wiki",
        )
        excluded_note = scan_notes.Note(
            note_id="excluded-note",
            content_hash="hash-excluded",
            title="Home Project",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
            tags=["personal"],
        )
        kept_note = scan_notes.Note(
            note_id="kept-note",
            content_hash="hash-kept",
            title="Research",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext=None,
            tags=["research"],
        )

        notes = scan_notes.filter_notes_by_config([excluded_note, kept_note], config)

        self.assertEqual(notes, [kept_note])

    def test_filter_notes_by_config_lets_exclude_tags_win_over_include_tags(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=[],
            folders=[],
            include_tags=["epiphan"],
            exclude_tags=["archive"],
            max_notes=25,
            wiki="example-wiki",
        )
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Archived Epiphan Research",
            account="iCloud",
            folder="Notes",
            created_at=None,
            modified_at="2026-05-12T10:00:00Z",
            plaintext=None,
            tags=["epiphan", "archive"],
        )

        notes = scan_notes.filter_notes_by_config([note], config)

        self.assertEqual(notes, [])

    def test_filter_new_notes_excludes_evaluated_note_version(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Research",
            account="iCloud",
            folder="Work",
            created_at="2026-05-10T09:00:00Z",
            modified_at="2026-05-11T09:00:00Z",
            plaintext="body",
        )
        records = [
            scan_notes.StateRecord(
                note_id="note-1",
                content_hash="hash-1",
                modified_at="2026-05-11T09:00:00Z",
                decision="yes",
                evaluated_at="2026-05-11T10:00:00Z",
            )
        ]

        candidates, excluded = scan_notes.filter_new_notes([note], records)

        self.assertEqual(candidates, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].reason, "already evaluated in state.jsonl")

    def test_filter_new_notes_keeps_unevaluated_note(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Research",
            account="iCloud",
            folder="Work",
            created_at=None,
            modified_at=None,
            plaintext="body",
        )

        candidates, excluded = scan_notes.filter_new_notes([note], [])

        self.assertEqual(candidates, [note])
        self.assertEqual(excluded, [])

    def test_filter_new_notes_keeps_updated_note_with_new_hash(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-2",
            title="Research",
            account="iCloud",
            folder="Work",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext="updated body",
        )
        records = [
            scan_notes.StateRecord(
                note_id="note-1",
                content_hash="hash-1",
                modified_at="2026-05-11T09:00:00Z",
                decision="yes",
                evaluated_at="2026-05-11T10:00:00Z",
            )
        ]

        candidates, excluded = scan_notes.filter_new_notes([note], records)

        self.assertEqual(candidates, [note])
        self.assertEqual(excluded, [])

    def test_scan_candidates_from_notes_returns_candidates_and_exclusions(self):
        notes = [
            scan_notes.Note(
                note_id="note-1",
                content_hash="hash-1",
                title="Old",
                account="iCloud",
                folder="Work",
                created_at=None,
                modified_at="2026-05-11T09:00:00Z",
                plaintext="old",
            ),
            scan_notes.Note(
                note_id="note-2",
                content_hash="hash-2",
                title="New",
                account="iCloud",
                folder="Work",
                created_at=None,
                modified_at="2026-05-12T09:00:00Z",
                plaintext="new",
            ),
        ]
        records = [
            scan_notes.StateRecord(
                note_id="note-1",
                content_hash="hash-1",
                modified_at="2026-05-11T09:00:00Z",
                decision="yes",
                evaluated_at="2026-05-11T10:00:00Z",
            )
        ]
        filters = scan_notes.ScanFilters(
            accounts=[],
            folders=[],
            include_tags=[],
            exclude_tags=[],
        )

        result = scan_notes.scan_candidates_from_notes(
            notes,
            records,
            scan_window_days=7,
            last_scan="2026-05-11T10:00:00Z",
            filters=filters,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.candidates[0].note.note_id, "note-2")
        self.assertEqual(result.excluded_count, 1)
        self.assertEqual(result.excluded[0].note_id, "note-1")
        self.assertEqual(result.scan_window_days, 7)
        self.assertEqual(result.last_scan, "2026-05-11T10:00:00Z")

    def test_scan_candidates_from_notes_applies_limit_after_exclusions(self):
        notes = [
            scan_notes.Note(
                note_id="note-1",
                content_hash="hash-1",
                title="One",
                account=None,
                folder=None,
                created_at=None,
                modified_at="2026-05-13T09:00:00Z",
                plaintext="one",
            ),
            scan_notes.Note(
                note_id="note-2",
                content_hash="hash-2",
                title="Two",
                account=None,
                folder=None,
                created_at=None,
                modified_at="2026-05-13T10:00:00Z",
                plaintext="two",
            ),
        ]
        filters = scan_notes.ScanFilters(
            accounts=[],
            folders=[],
            include_tags=[],
            exclude_tags=[],
        )

        result = scan_notes.scan_candidates_from_notes(
            notes,
            [],
            scan_window_days=7,
            last_scan=None,
            limit=1,
            now=scan_notes.datetime(2026, 5, 14, tzinfo=scan_notes.UTC),
            filters=filters,
        )

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.candidates[0].note.note_id, "note-1")
        self.assertEqual(result.excluded_count, 0)

    def test_filter_notes_by_scan_window_keeps_recent_note(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Recent",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-05-13T09:00:00Z",
            plaintext=None,
        )

        included, excluded = scan_notes.filter_notes_by_scan_window(
            [note],
            scan_window_days=7,
            now=scan_notes.datetime(2026, 5, 14, tzinfo=scan_notes.UTC),
        )

        self.assertEqual(included, [note])
        self.assertEqual(excluded, [])

    def test_filter_notes_by_scan_window_excludes_old_note(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Old",
            account=None,
            folder=None,
            created_at=None,
            modified_at="2026-04-01T09:00:00Z",
            plaintext=None,
        )

        included, excluded = scan_notes.filter_notes_by_scan_window(
            [note],
            scan_window_days=7,
            now=scan_notes.datetime(2026, 5, 14, tzinfo=scan_notes.UTC),
        )

        self.assertEqual(included, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].reason, "outside scan window")

    def test_filter_notes_by_scan_window_excludes_unparsable_modified_at(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Unknown Date",
            account=None,
            folder=None,
            created_at=None,
            modified_at="not a date",
            plaintext=None,
        )

        included, excluded = scan_notes.filter_notes_by_scan_window(
            [note],
            scan_window_days=7,
            now=scan_notes.datetime(2026, 5, 14, tzinfo=scan_notes.UTC),
        )

        self.assertEqual(included, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].reason, "missing or unparsable modified_at")

    def test_scan_candidates_from_notes_applies_limit_after_window_and_state_exclusions(
        self,
    ):
        notes = [
            scan_notes.Note(
                note_id="old-note",
                content_hash="hash-old",
                title="Old",
                account=None,
                folder=None,
                created_at=None,
                modified_at="2026-04-01T09:00:00Z",
                plaintext=None,
            ),
            scan_notes.Note(
                note_id="seen-note",
                content_hash="hash-seen",
                title="Seen",
                account=None,
                folder=None,
                created_at=None,
                modified_at="2026-05-13T09:00:00Z",
                plaintext=None,
            ),
            scan_notes.Note(
                note_id="new-note-1",
                content_hash="hash-new-1",
                title="New One",
                account=None,
                folder=None,
                created_at=None,
                modified_at="2026-05-13T10:00:00Z",
                plaintext=None,
            ),
            scan_notes.Note(
                note_id="new-note-2",
                content_hash="hash-new-2",
                title="New Two",
                account=None,
                folder=None,
                created_at=None,
                modified_at="2026-05-13T11:00:00Z",
                plaintext=None,
            ),
        ]
        records = [
            scan_notes.StateRecord(
                note_id="seen-note",
                content_hash="hash-seen",
                modified_at="2026-05-13T09:00:00Z",
                decision="no",
                evaluated_at="2026-05-13T12:00:00Z",
            )
        ]
        filters = scan_notes.ScanFilters(
            accounts=[],
            folders=[],
            include_tags=[],
            exclude_tags=[],
        )

        result = scan_notes.scan_candidates_from_notes(
            notes,
            records,
            scan_window_days=7,
            last_scan=None,
            limit=1,
            filters=filters,
            now=scan_notes.datetime(2026, 5, 14, tzinfo=scan_notes.UTC),
        )

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.candidates[0].note.note_id, "new-note-1")
        self.assertEqual(result.excluded_count, 2)
        self.assertEqual(
            [exclusion.reason for exclusion in result.excluded],
            ["outside scan window", "already evaluated in state.jsonl"],
        )

    def test_scan_command_prints_scan_result(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 7",
                        'raw_output_dir = "raw/"',
                        'accounts = ["iCloud"]',
                        'folders = ["Work"]',
                        'include_tags = ["research"]',
                        'exclude_tags = ["archive"]',
                        "max_notes = 25",
                        'database_path = ""',
                        'wiki = "example-wiki"',
                    ]
                ),
                encoding="utf-8",
            )
            notes = [
                scan_notes.Note(
                    note_id="note-1",
                    content_hash="hash-1",
                    title="Research",
                    account="iCloud",
                    folder="Work",
                    created_at=None,
                    modified_at="2026-05-12T09:00:00Z",
                    plaintext="body",
                )
            ]

            with mock.patch.object(scan_notes, "load_notes", return_value=notes):
                with redirect_stdout(stdout):
                    code = scan_notes.main(["scan", "--skill-dir", str(skill_dir)])

        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["note"]["note_id"], "note-1")
        self.assertEqual(
            result["filters"],
            {
                "accounts": ["iCloud"],
                "folders": ["Work"],
                "include_tags": ["research"],
                "exclude_tags": ["archive"],
            },
        )

    def test_scan_command_returns_3_when_notes_backend_missing(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)

            with mock.patch.object(
                scan_notes,
                "load_notes",
                side_effect=scan_notes.NotesClientError("backend unavailable"),
            ):
                with redirect_stderr(stderr):
                    code = scan_notes.main(["scan", "--skill-dir", str(skill_dir)])

            self.assertEqual(code, 3)
            self.assertIn("Notes client error: backend unavailable", stderr.getvalue())

    def test_decision_template_from_candidates_defaults_to_ambiguous(self):
        candidate = scan_notes.Candidate(
            note=scan_notes.Note(
                note_id="note-1",
                content_hash="hash-1",
                title="Research",
                account="iCloud",
                folder="Work",
                created_at=None,
                modified_at="2026-05-12T09:00:00Z",
                plaintext=None,
            )
        )

        decisions = scan_notes.decision_template_from_candidates([candidate])

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].note_id, "note-1")
        self.assertEqual(decisions[0].content_hash, "hash-1")
        self.assertEqual(decisions[0].modified_at, "2026-05-12T09:00:00Z")
        self.assertEqual(decisions[0].decision, "ambiguous")

    def test_decisions_template_command_prints_ambiguous_decisions(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)
            notes = [
                scan_notes.Note(
                    note_id="note-1",
                    content_hash="hash-1",
                    title="Research",
                    account="iCloud",
                    folder="Work",
                    created_at=None,
                    modified_at="2026-05-12T09:00:00Z",
                    plaintext=None,
                )
            ]

            with mock.patch.object(scan_notes, "load_notes", return_value=notes):
                with redirect_stdout(stdout):
                    code = scan_notes.main(
                        ["decisions-template", "--skill-dir", str(skill_dir)]
                    )

        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["note_id"], "note-1")
        self.assertEqual(result[0]["content_hash"], "hash-1")
        self.assertEqual(result[0]["decision"], "ambiguous")

    def test_slugify_normalizes_note_titles(self):
        self.assertEqual(
            scan_notes.slugify("Research: Apple Notes!"), "research-apple-notes"
        )
        self.assertEqual(scan_notes.slugify(None), "untitled")

    def test_raw_filename_includes_date_note_slug_and_hash(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Research: Apple Notes!",
            account="iCloud",
            folder="Work",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext="body",
        )

        filename = scan_notes.raw_filename(note)

        self.assertTrue(filename.startswith("2026-05-12-note-research-apple-notes-"))
        self.assertTrue(filename.endswith(".md"))

    def test_write_raw_note_writes_content_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            config = scan_notes.NotesConfig(
                lookback_days=7,
                raw_output_dir="raw/",
                database_path=None,
                accounts=[],
                folders=[],
                include_tags=[],
                exclude_tags=[],
                max_notes=25,
                wiki="example-wiki",
            )
            note = scan_notes.Note(
                note_id="note-1",
                content_hash="hash-1",
                title="Research",
                account="iCloud",
                folder="Work",
                created_at="2026-05-11T09:00:00Z",
                modified_at="2026-05-12T09:00:00Z",
                plaintext="body",
                tags=["research", "wiki"],
            )

            result = scan_notes.write_raw_note(config, note, base_dir=base_dir)
            text = Path(result.path).read_text(encoding="utf-8")

        self.assertIn("Content hash: hash-1", text)
        self.assertIn("Tags: research, wiki", text)
        self.assertIn("body", text)

    def test_write_raw_note_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            config = scan_notes.NotesConfig(
                lookback_days=7,
                raw_output_dir="raw/",
                database_path=None,
                accounts=[],
                folders=[],
                include_tags=[],
                exclude_tags=[],
                max_notes=25,
                wiki="example-wiki",
            )
            note = scan_notes.Note(
                note_id="note-1",
                content_hash="hash-1",
                title="Research",
                account="iCloud",
                folder="Work",
                created_at=None,
                modified_at="2026-05-12T09:00:00Z",
                plaintext="body",
            )

            first = scan_notes.write_raw_note(config, note, base_dir=base_dir)
            second = scan_notes.write_raw_note(config, note, base_dir=base_dir)

        self.assertNotEqual(first.path, second.path)
        self.assertTrue(second.path.endswith("-2.md"))

    def test_find_note_for_decision_matches_note_id_and_content_hash(self):
        note = scan_notes.Note(
            note_id="note-1",
            content_hash="hash-1",
            title="Research",
            account="iCloud",
            folder="Work",
            created_at=None,
            modified_at="2026-05-12T09:00:00Z",
            plaintext="body",
        )
        decision = scan_notes.DecisionInput(
            note_id="note-1",
            content_hash="hash-1",
            modified_at="2026-05-12T09:00:00Z",
            decision="yes",
        )

        found = scan_notes.find_note_for_decision([note], decision)

        self.assertEqual(found, note)

    def test_find_note_for_decision_raises_for_missing_note(self):
        decision = scan_notes.DecisionInput(
            note_id="note-1",
            content_hash="hash-1",
            modified_at="2026-05-12T09:00:00Z",
            decision="yes",
        )

        with self.assertRaises(scan_notes.RawWriteError):
            scan_notes.find_note_for_decision([], decision)

    def test_export_approved_command_writes_only_yes_decisions(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)
            decisions_path = skill_dir / "decisions.json"
            decisions_path.write_text(
                json.dumps(
                    [
                        {
                            "note_id": "note-1",
                            "content_hash": "hash-1",
                            "modified_at": "2026-05-12T09:00:00Z",
                            "decision": "yes",
                        },
                        {
                            "note_id": "note-2",
                            "content_hash": "hash-2",
                            "modified_at": "2026-05-12T10:00:00Z",
                            "decision": "no",
                        },
                        {
                            "note_id": "note-3",
                            "content_hash": "hash-3",
                            "modified_at": "2026-05-12T11:00:00Z",
                            "decision": "ambiguous",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            notes = [
                scan_notes.Note(
                    note_id="note-1",
                    content_hash="hash-1",
                    title="Research",
                    account="iCloud",
                    folder="Work",
                    created_at=None,
                    modified_at="2026-05-12T09:00:00Z",
                    plaintext="body",
                )
            ]

            with mock.patch.object(scan_notes, "load_notes", return_value=notes):
                with mock.patch.object(
                    scan_notes,
                    "write_raw_note",
                    return_value=scan_notes.RawWriteResult(path="/tmp/raw/note.md"),
                ) as write_raw:
                    with redirect_stdout(stdout):
                        code = scan_notes.main(
                            [
                                "export-approved",
                                "--skill-dir",
                                str(skill_dir),
                                "--decisions",
                                str(decisions_path),
                            ]
                        )

        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        write_raw.assert_called_once()
        self.assertEqual(result["exported"], 1)
        self.assertEqual(result["raw_files"], ["/tmp/raw/note.md"])

    def test_export_approved_command_without_decisions_returns_2(self):
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)

            with redirect_stderr(stderr):
                code = scan_notes.main(
                    ["export-approved", "--skill-dir", str(skill_dir)]
                )

        self.assertEqual(code, 2)
        self.assertIn("Error: --decisions is required", stderr.getvalue())

    def test_export_approved_command_returns_6_when_note_missing(self):
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)
            decisions_path = skill_dir / "decisions.json"
            decisions_path.write_text(
                json.dumps(
                    [
                        {
                            "note_id": "note-1",
                            "content_hash": "hash-1",
                            "modified_at": "2026-05-12T09:00:00Z",
                            "decision": "yes",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(scan_notes, "load_notes", return_value=[]):
                with redirect_stderr(stderr):
                    code = scan_notes.main(
                        [
                            "export-approved",
                            "--skill-dir",
                            str(skill_dir),
                            "--decisions",
                            str(decisions_path),
                        ]
                    )

        self.assertEqual(code, 6)
        self.assertIn("Raw write error:", stderr.getvalue())

    def test_preflight_returns_3_when_dependency_missing(self):
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)

            with mock.patch.object(
                scan_notes,
                "preflight_notes",
                side_effect=scan_notes.NotesClientError("missing dependency"),
            ):
                with redirect_stderr(stderr):
                    code = scan_notes.main(["preflight", "--skill-dir", str(skill_dir)])

        self.assertEqual(code, 3)
        self.assertIn("Notes client error: missing dependency", stderr.getvalue())

    def test_preflight_prints_backend_status(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            self.write_config(skill_dir)

            with mock.patch.object(
                scan_notes,
                "preflight_notes",
                return_value={
                    "ok": True,
                    "backend": "apple_notes_parser",
                    "database_path": "auto",
                },
            ):
                with redirect_stdout(stdout):
                    code = scan_notes.main(["preflight", "--skill-dir", str(skill_dir)])

        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["backend"], "apple_notes_parser")
        self.assertEqual(result["database_path"], "auto")

    def test_scan_filters_from_config_copies_config_filter_values(self):
        config = scan_notes.NotesConfig(
            lookback_days=7,
            raw_output_dir="raw/",
            database_path=None,
            accounts=["iCloud"],
            folders=["Work"],
            include_tags=["research"],
            exclude_tags=["archive"],
            max_notes=25,
            wiki="example-wiki",
        )

        filters = scan_notes.scan_filters_from_config(config)

        self.assertEqual(filters.accounts, ["iCloud"])
        self.assertEqual(filters.folders, ["Work"])
        self.assertEqual(filters.include_tags, ["research"])
        self.assertEqual(filters.exclude_tags, ["archive"])
