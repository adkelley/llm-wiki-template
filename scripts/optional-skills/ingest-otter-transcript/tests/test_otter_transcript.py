from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "otter_transcript.py"
SKILL_DIR = SCRIPT_PATH.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

SPEC = importlib.util.spec_from_file_location("otter_transcript", SCRIPT_PATH)
assert SPEC is not None, "Failed to load otter_transcript module"
assert SPEC.loader is not None, "Failed to load otter_transcript module"

otter_transcript = importlib.util.module_from_spec(SPEC)
sys.modules["otter_transcript"] = otter_transcript
SPEC.loader.exec_module(otter_transcript)


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OtterTranscriptTest(unittest.TestCase):
    def sample_list_conversation(self) -> dict:
        return {
            "id": "abc123",
            "title": "Nick Divehall & Turtles",
            "url": "https://otter.ai/u/abc123",
            "created_at": "2026-05-14T22:05:26Z",
            "owner": {
                "email": "alex@example.com",
            },
            "calendar_guests": [
                {"email": "nick@example.com"},
                {"email": "ALEX@example.com"},
                {"email": None},
            ],
            "shared_emails": [
                {
                    "email": "shared@example.com",
                    "user": {"email": "nick@example.com"},
                }
            ],
        }

    def sample_full_conversation(self) -> dict:
        conversation = self.sample_list_conversation()
        conversation["relationships"] = {
            "transcript": {
                "content": "Nick Divehall  00:00\nHello from Otter.\n",
                "format": "txt",
            }
        }
        return conversation

    def test_slugify_normalizes_filename_text(self):
        self.assertEqual(
            otter_transcript.slugify("Nick Divehall & Turtles"),
            "nick-divehall-turtles",
        )
        self.assertEqual(otter_transcript.slugify("!!!", "fallback"), "fallback")
        self.assertEqual(otter_transcript.slugify("A---B"), "a-b")

    def test_date_from_created_at_uses_iso_date_prefix(self):
        self.assertEqual(
            otter_transcript.date_from_created_at("2026-05-14T22:05:26Z"),
            "2026-05-14",
        )
        self.assertEqual(otter_transcript.date_from_created_at(None), "undated")
        self.assertEqual(otter_transcript.date_from_created_at("not-a-date"), "undated")

    def test_filters_match_title_date_and_email(self):
        conversation = self.sample_list_conversation()

        self.assertTrue(otter_transcript.title_matches(conversation, "turtles"))
        self.assertFalse(otter_transcript.title_matches(conversation, "avalon"))
        self.assertTrue(otter_transcript.date_matches(conversation, "2026-05-14"))
        self.assertFalse(otter_transcript.date_matches(conversation, "2026-05-13"))
        self.assertTrue(
            otter_transcript.email_matches(conversation, "nick@example.com")
        )
        self.assertFalse(
            otter_transcript.email_matches(conversation, "missing@example.com")
        )

    def test_conversation_emails_collects_and_normalizes_addresses(self):
        self.assertEqual(
            otter_transcript.conversation_emails(self.sample_list_conversation()),
            {
                "alex@example.com",
                "nick@example.com",
                "shared@example.com",
            },
        )

    def test_raw_output_path_uses_date_title_and_id(self):
        path = otter_transcript.raw_output_path(
            self.sample_full_conversation(),
            Path("raw"),
        )
        self.assertEqual(
            path,
            Path("raw")
            / "2026-05-14-otter-nick-divehall-turtles-abc123.md",
        )

    def test_transcript_from_conversation_rejects_missing_content(self):
        with self.assertRaises(otter_transcript.OtterTranscriptError):
            otter_transcript.transcript_from_conversation({"relationships": {}})

        with self.assertRaises(otter_transcript.OtterTranscriptError):
            otter_transcript.transcript_from_conversation(
                {"relationships": {"transcript": {"content": "   "}}}
            )

    def test_raw_markdown_preserves_transcript_and_adds_metadata(self):
        markdown = otter_transcript.raw_markdown(self.sample_full_conversation())

        self.assertIn("Title: Nick Divehall & Turtles\n", markdown)
        self.assertIn("Source: Otter.ai Public API\n", markdown)
        self.assertIn("Conversation ID: abc123\n", markdown)
        self.assertIn(
            "Participant emails: alex@example.com, nick@example.com, shared@example.com\n",
            markdown,
        )
        self.assertTrue(markdown.endswith("Nick Divehall  00:00\nHello from Otter.\n\n"))

    def test_write_raw_markdown_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "raw" / "example.md"
            otter_transcript.write_raw_markdown(output_path, "first")

            self.assertEqual(output_path.read_text(encoding="utf-8"), "first")
            with self.assertRaises(otter_transcript.OtterTranscriptError):
                otter_transcript.write_raw_markdown(output_path, "second")

            self.assertEqual(output_path.read_text(encoding="utf-8"), "first")

    def test_list_conversations_reads_data_list(self):
        payload = {"meta": {}, "data": [self.sample_list_conversation()]}

        with mock.patch.object(
            otter_transcript.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            conversations = otter_transcript.list_conversations("test-key")

        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["id"], "abc123")

    def test_fetch_conversation_reads_data_object(self):
        payload = {"meta": {}, "data": self.sample_full_conversation()}

        with mock.patch.object(
            otter_transcript.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            conversation = otter_transcript.fetch_conversation("test-key", "abc123")

        self.assertEqual(conversation["id"], "abc123")
        self.assertEqual(
            conversation["relationships"]["transcript"]["content"],
            "Nick Divehall  00:00\nHello from Otter.\n",
        )

    def test_main_direct_conversation_writes_raw_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "raw"

            with mock.patch.dict(
                otter_transcript.os.environ,
                {"OTTER_API_KEY": "test-key"},
                clear=True,
            ), mock.patch.object(
                otter_transcript,
                "fetch_conversation",
                return_value=self.sample_full_conversation(),
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = otter_transcript.main(
                        [
                            "--conversation-id",
                            "abc123",
                            "--raw-output-dir",
                            output_dir.as_posix(),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertIn("Created:", stdout.getvalue())
            output_files = list(output_dir.glob("*.md"))
            self.assertEqual(len(output_files), 1)
            self.assertIn(
                "Nick Divehall  00:00\nHello from Otter.\n",
                output_files[0].read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
