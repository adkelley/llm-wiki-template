from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scan_mail.py"
SKILL_DIR = SCRIPT_PATH.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import himalaya_client  # noqa: E402
import models  # noqa: E402
import parsers  # noqa: E402
import raw_export  # noqa: E402
import thread_context  # noqa: E402

SPEC = importlib.util.spec_from_file_location("scan_mail", SCRIPT_PATH)
assert SPEC is not None, "Failed to load scan_mail module"
assert SPEC.loader is not None, "Failed to load scan_mail module"

scan_mail = importlib.util.module_from_spec(SPEC)
sys.modules["scan_mail"] = scan_mail
SPEC.loader.exec_module(scan_mail)


class ScanMailTests(unittest.TestCase):
    def test_parse_account_names(self):
        output = json.dumps(
            [
                {"name": "personal", "backend": "IMAP, SMTP", "default": True},
                {"name": "work", "backend": "IMAP", "default": False},
            ]
        )

        self.assertEqual(parsers.parse_account_names(output), ["personal", "work"])

    def test_parse_folder_names(self) -> None:
        output = json.dumps(
            [
                {"name": "INBOX", "desc": ""},
                {"name": "Sent Items", "desc": ""},
            ]
        )

        self.assertEqual(parsers.parse_folder_names(output), ["INBOX", "Sent Items"])

    def test_parse_message(self) -> None:
        message = parsers.parse_message(
            json.dumps("From: A <a@example.com>\nSubject: Test\n\nBody"),
            account="personal",
            folder="INBOX",
            message_id="143950",
        )

        self.assertEqual(message.account, "personal")
        self.assertEqual(message.folder, "INBOX")
        self.assertEqual(message.id, "143950")
        self.assertIn("Subject: Test", message.text)

    def test_parse_envelopes(self) -> None:
        output = json.dumps(
            [
                {
                    "id": "123",
                    "flags": ["Seen"],
                    "subject": "Project update",
                    "from": {"name": "Sender Example", "addr": "sender@example.com"},
                    "to": {
                        "name": "Recipient Example",
                        "addr": "recipient@example.com",
                    },
                    "date": "2026-05-07T20:05:12Z",
                    "has_attachment": False,
                }
            ]
        )

        envelopes = parsers.parse_envelopes(
            output,
            account="personal",
            folder="INBOX",
        )

        self.assertEqual(len(envelopes), 1)

        envelope = envelopes[0]
        self.assertEqual(envelope.account, "personal")
        self.assertEqual(envelope.folder, "INBOX")
        self.assertEqual(envelope.id, "123")
        self.assertEqual(envelope.subject, "Project update")

        self.assertIsNotNone(envelope.from_addr)
        assert envelope.from_addr is not None
        self.assertEqual(envelope.from_addr.name, "Sender Example")
        self.assertEqual(envelope.from_addr.addr, "sender@example.com")

        self.assertEqual(len(envelope.to_addrs), 1)
        self.assertEqual(envelope.to_addrs[0].name, "Recipient Example")
        self.assertEqual(envelope.to_addrs[0].addr, "recipient@example.com")

        self.assertEqual(envelope.date, "2026-05-07T20:05:12Z")
        self.assertFalse(envelope.has_attachment)

    def test_filter_new_envelopes_removes_evaluated_message(self) -> None:
        envelope = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        record = scan_mail.StateRecord(
            account="personal",
            folder="INBOX",
            envelope_id="123",
            decision="no",
            evaluated_at="2026-05-07T20:10:00Z",
        )

        self.assertEqual(scan_mail.filter_new_envelopes([envelope], [record]), [])

    def test_filter_new_envelopes_keeps_unevaluated_message(self) -> None:
        envelope = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        record = scan_mail.StateRecord(
            account="personal",
            folder="INBOX",
            envelope_id="999",
            decision="no",
            evaluated_at="2026-05-07T20:10:00Z",
        )

        self.assertEqual(
            scan_mail.filter_new_envelopes([envelope], [record]), [envelope]
        )

    def test_normalized_thread_subject_removes_reply_and_forward_prefixes(self) -> None:
        self.assertEqual(
            thread_context.normalized_thread_subject("Re: Project update"),
            "project update",
        )
        self.assertEqual(
            thread_context.normalized_thread_subject("Fwd: Re: Project update"),
            "project update",
        )
        self.assertEqual(
            thread_context.normalized_thread_subject(" FW:  FWD: Project update "),
            "project update",
        )

    def test_normalized_thread_subject_handles_empty_subjects(self) -> None:
        self.assertEqual(thread_context.normalized_thread_subject(None), "")
        self.assertEqual(thread_context.normalized_thread_subject(""), "")
        self.assertEqual(thread_context.normalized_thread_subject("   "), "")

    def test_same_thread_subject_matches_normalized_subjects(self) -> None:
        original = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        reply = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="456",
            flags=[],
            subject="Re: Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T21:05:12Z",
            has_attachment=False,
        )

        self.assertTrue(thread_context.same_thread_subject(original, reply))

    def test_same_thread_subject_rejects_unrelated_or_empty_subjects(self) -> None:
        first = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        unrelated = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="456",
            flags=[],
            subject="Different topic",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T21:05:12Z",
            has_attachment=False,
        )
        empty = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="789",
            flags=[],
            subject="",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T22:05:12Z",
            has_attachment=False,
        )

        self.assertFalse(thread_context.same_thread_subject(first, unrelated))
        self.assertFalse(thread_context.same_thread_subject(empty, empty))

    def test_thread_context_for_envelope_filters_self_unrelated_and_limit(self) -> None:
        target = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="target",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        same_id = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="target",
            flags=[],
            subject="Re: Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:10:12Z",
            has_attachment=False,
        )
        first_reply = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="reply-1",
            flags=[],
            subject="Re: Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:15:12Z",
            has_attachment=False,
        )
        unrelated = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="unrelated",
            flags=[],
            subject="Different topic",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:20:12Z",
            has_attachment=False,
        )
        second_reply = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="reply-2",
            flags=[],
            subject="Fwd: Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:25:12Z",
            has_attachment=False,
        )

        context = scan_mail.thread_context_for_envelope(
            target,
            [target, same_id, first_reply, unrelated, second_reply],
            limit=1,
        )

        self.assertEqual([envelope.id for envelope in context], ["reply-1"])

    def test_load_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                        'wiki = "example-wiki"',
                    ]
                ),
                encoding="utf-8",
            )

            config = scan_mail.load_config(skill_dir)

        self.assertEqual(config.lookback_days, 14)
        self.assertEqual(config.raw_output_dir, "raw/")
        self.assertEqual(config.accounts, ["personal"])
        self.assertEqual(config.folders, ["INBOX"])
        self.assertEqual(config.max_messages_per_folder, 5)
        self.assertEqual(config.max_thread_context_messages, 3)
        self.assertEqual(config.wiki, "example-wiki")

    def test_load_config_rejects_empty_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        "accounts = []",
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(scan_mail.ConfigError):
                scan_mail.load_config(skill_dir)

    def test_raw_thread_context_text_returns_none_captured_when_empty(self) -> None:
        self.assertEqual(raw_export.raw_thread_context_text([]), "None captured")

    def test_raw_thread_context_text_formats_all_context_envelopes(self) -> None:
        first = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=models.Address(name="Sender One", addr="one@example.com"),
            to_addrs=[models.Address(name="Recipient", addr="to@example.com")],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        second = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="456",
            flags=[],
            subject="Re: Project update",
            from_addr=models.Address(name="Sender Two", addr="two@example.com"),
            to_addrs=[],
            date="2026-05-07T21:05:12Z",
            has_attachment=False,
        )

        text = raw_export.raw_thread_context_text([first, second])

        self.assertIn("- Envelope ID: 123", text)
        self.assertIn("  Subject: Project update", text)
        self.assertIn("  From: Sender One <one@example.com>", text)
        self.assertIn("  To: Recipient <to@example.com>", text)
        self.assertIn("- Envelope ID: 456", text)
        self.assertIn("  Subject: Re: Project update", text)
        self.assertIn("  From: Sender Two <two@example.com>", text)

    def test_write_raw_candidate(self) -> None:
        config = scan_mail.MailConfig(
            lookback_days=14,
            raw_output_dir="raw/",
            accounts=["personal"],
            folders=["INBOX"],
            max_messages_per_folder=5,
            max_thread_context_messages=3,
            wiki="example-wiki",
        )
        envelope = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=models.Address(
                name="Sender Example",
                addr="sender@example.com",
            ),
            to_addrs=[
                models.Address(
                    name="Recipient Example",
                    addr="recipient@example.com",
                )
            ],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        message = models.Message(
            account="personal",
            folder="INBOX",
            id="123",
            text="From: Sender Example <sender@example.com>\n\nBody text",
        )
        candidate = models.Candidate(
            envelope=envelope,
            message=message,
            message_error=None,
            thread_context=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = raw_export.write_raw_candidate(config, candidate, Path(tmp))
            output_path = Path(result.path)

            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.parent.name, "raw")
            self.assertTrue(
                output_path.name.startswith("2026-05-07-email-project-update-")
            )

            content = output_path.read_text(encoding="utf-8")

        self.assertIn("Subject: Project update", content)
        self.assertIn("Envelope ID: 123", content)
        self.assertIn("Source: Himalaya", content)
        self.assertIn("From: Sender Example <sender@example.com>", content)
        self.assertIn("To: Recipient Example <recipient@example.com>", content)
        self.assertIn("Body text", content)
        self.assertIn("None captured", content)

    def test_export_approved_writes_only_yes_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skill"
            skill_dir.mkdir()
            raw_dir = Path(tmp) / "raw"
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        f'raw_output_dir = "{raw_dir}"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "last_scan.txt").write_text(
                "2026-05-07T12:00:00Z\n",
                encoding="utf-8",
            )
            decisions_path = Path(tmp) / "decisions.json"
            decisions_path.write_text(
                json.dumps(
                    [
                        {
                            "account": "personal",
                            "folder": "INBOX",
                            "envelope_id": "123",
                            "decision": "yes",
                        },
                        {
                            "account": "personal",
                            "folder": "INBOX",
                            "envelope_id": "456",
                            "decision": "no",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            envelope = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="123",
                flags=[],
                subject="Project update",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:05:12Z",
                has_attachment=False,
            )
            message = models.Message(
                account="personal",
                folder="INBOX",
                id="123",
                text="Approved body",
            )

            with (
                mock.patch.object(
                    scan_mail, "himalaya_envelope_list", return_value=[envelope]
                ) as envelope_list,
                mock.patch.object(
                    scan_mail, "himalaya_message_read", return_value=message
                ) as read_message,
                mock.patch.object(
                    scan_mail,
                    "datetime",
                    wraps=scan_mail.datetime,
                ) as datetime_mock,
            ):
                datetime_mock.now.return_value = datetime(
                    2026,
                    5,
                    8,
                    12,
                    0,
                    0,
                    tzinfo=UTC,
                )
                results = scan_mail.export_approved(skill_dir, decisions_path)

            self.assertEqual(len(results), 1)
            envelope_list.assert_called_once()
            args, kwargs = envelope_list.call_args
            self.assertEqual(args[1:], ("personal", "INBOX"))
            self.assertEqual(kwargs["window_days"], 3)
            self.assertEqual(kwargs["page_size"], 20)
            read_message.assert_called_once_with("personal", "INBOX", "123")
            output_path = Path(results[0].path)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.parent, raw_dir)
            self.assertIn("Approved body", output_path.read_text(encoding="utf-8"))

    def test_export_approved_writes_thread_context_to_raw_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skill"
            skill_dir.mkdir()
            raw_dir = Path(tmp) / "raw"
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        f'raw_output_dir = "{raw_dir}"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "last_scan.txt").write_text(
                "2026-05-07T12:00:00Z\n",
                encoding="utf-8",
            )
            decisions_path = Path(tmp) / "decisions.json"
            decisions_path.write_text(
                json.dumps(
                    [
                        {
                            "account": "personal",
                            "folder": "INBOX",
                            "envelope_id": "123",
                            "decision": "yes",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            approved = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="123",
                flags=[],
                subject="Project update",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:05:12Z",
                has_attachment=False,
            )
            related = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="456",
                flags=[],
                subject="Re: Project update",
                from_addr=models.Address(
                    name="Related Sender",
                    addr="related@example.com",
                ),
                to_addrs=[],
                date="2026-05-07T21:05:12Z",
                has_attachment=False,
            )
            unrelated = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="789",
                flags=[],
                subject="Different topic",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T22:05:12Z",
                has_attachment=False,
            )
            message = models.Message(
                account="personal",
                folder="INBOX",
                id="123",
                text="Approved body",
            )

            with (
                mock.patch.object(
                    scan_mail,
                    "himalaya_envelope_list",
                    return_value=[approved, related, unrelated],
                ),
                mock.patch.object(
                    scan_mail,
                    "himalaya_message_read",
                    return_value=message,
                ),
            ):
                results = scan_mail.export_approved(skill_dir, decisions_path)

            content = Path(results[0].path).read_text(encoding="utf-8")

        self.assertIn("Thread context used for evaluation:", content)
        self.assertIn("- Envelope ID: 456", content)
        self.assertIn("  Subject: Re: Project update", content)
        self.assertIn("  From: Related Sender <related@example.com>", content)
        self.assertNotIn("- Envelope ID: 789", content)

    def test_export_approved_finds_envelope_only_available_in_windowed_lookup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skill"
            skill_dir.mkdir()
            raw_dir = Path(tmp) / "raw"
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        f'raw_output_dir = "{raw_dir}"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "last_scan.txt").write_text(
                "2026-05-07T12:00:00Z\n",
                encoding="utf-8",
            )
            decisions_path = Path(tmp) / "decisions.json"
            decisions_path.write_text(
                json.dumps(
                    [
                        {
                            "account": "personal",
                            "folder": "INBOX",
                            "envelope_id": "approved-old",
                            "decision": "yes",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            newer = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="newer",
                flags=[],
                subject="Newer message",
                from_addr=None,
                to_addrs=[],
                date="2026-05-08T20:05:12Z",
                has_attachment=False,
            )
            approved_old = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="approved-old",
                flags=[],
                subject="Project update",
                from_addr=None,
                to_addrs=[],
                date="2026-04-24T20:05:12Z",
                has_attachment=False,
            )
            message = models.Message(
                account="personal",
                folder="INBOX",
                id="approved-old",
                text="Approved old body",
            )

            def list_envelopes(
                config,
                account,
                folder,
                window_days=None,
                page_size=None,
            ):
                if window_days is None:
                    return [newer]
                return [newer, approved_old]

            with (
                mock.patch.object(
                    scan_mail,
                    "himalaya_envelope_list",
                    side_effect=list_envelopes,
                ) as envelope_list,
                mock.patch.object(
                    scan_mail,
                    "himalaya_message_read",
                    return_value=message,
                ),
                mock.patch.object(
                    scan_mail,
                    "datetime",
                    wraps=scan_mail.datetime,
                ) as datetime_mock,
            ):
                datetime_mock.now.return_value = datetime(
                    2026,
                    5,
                    8,
                    12,
                    0,
                    0,
                    tzinfo=UTC,
                )
                results = scan_mail.export_approved(skill_dir, decisions_path)

            content = Path(results[0].path).read_text(encoding="utf-8")

        self.assertIn("Envelope ID: approved-old", content)
        self.assertIn("Approved old body", content)
        _args, kwargs = envelope_list.call_args
        self.assertEqual(kwargs["window_days"], 3)
        self.assertEqual(kwargs["page_size"], 20)

    def test_export_approved_command_outputs_export_summary(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            scan_mail,
            "export_approved",
            return_value=[models.RawWriteResult(path="/tmp/raw/email.md")],
        ) as export_approved:
            with redirect_stdout(output):
                exit_code = scan_mail.main(
                    [
                        "export-approved",
                        "--skill-dir",
                        "/tmp/example-skill",
                        "--decisions",
                        "/tmp/decisions.json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        export_approved.assert_called_once_with(
            skill_dir=Path("/tmp/example-skill"),
            decisions_path=Path("/tmp/decisions.json"),
        )
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "exported": 1,
                "ok": True,
                "raw_files": ["/tmp/raw/email.md"],
            },
        )

    def test_scan_candidates_reports_candidates_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "state.jsonl").write_text(
                json.dumps(
                    {
                        "account": "personal",
                        "folder": "INBOX",
                        "envelope_id": "already-seen",
                        "decision": "no",
                        "evaluated_at": "2026-05-07T20:10:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            seen_envelope = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="already-seen",
                flags=[],
                subject="Already seen",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:05:12Z",
                has_attachment=False,
            )
            new_envelope = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="new-message",
                flags=[],
                subject="New message",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:06:12Z",
                has_attachment=False,
            )

            with mock.patch.object(
                scan_mail,
                "himalaya_envelope_list",
                return_value=[seen_envelope, new_envelope],
            ):
                result = scan_mail.scan_candidates(skill_dir)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.candidates[0].envelope.id, "new-message")

        self.assertEqual(result.excluded_count, 1)
        self.assertEqual(result.excluded[0].envelope_id, "already-seen")
        self.assertEqual(
            result.excluded[0].reason,
            "already evaluated in state.jsonl",
        )

    def test_scan_candidates_captures_message_read_errors_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            first = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="first",
                flags=[],
                subject="First message",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:05:12Z",
                has_attachment=False,
            )
            second = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="second",
                flags=[],
                subject="Second message",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:06:12Z",
                has_attachment=False,
            )

            def read_message(
                account: str,
                folder: str,
                message_id: str,
            ):
                if message_id == "first":
                    raise scan_mail.CommandError(
                        "Command failed: himalaya message read first\n"
                        "unexpected NO response: Service temporarily unavailable"
                    )
                return models.Message(
                    account=account,
                    folder=folder,
                    id=message_id,
                    text="Second body",
                )

            with (
                mock.patch.object(
                    scan_mail,
                    "himalaya_envelope_list",
                    return_value=[first, second],
                ),
                mock.patch.object(
                    scan_mail,
                    "himalaya_message_read",
                    side_effect=read_message,
                ),
            ):
                result = scan_mail.scan_candidates(skill_dir, include_messages=True)

        self.assertEqual(result.candidate_count, 2)
        self.assertIsNone(result.candidates[0].message)
        self.assertIsNotNone(result.candidates[0].message_error)
        assert result.candidates[0].message_error is not None
        self.assertIn(
            "Service temporarily unavailable",
            result.candidates[0].message_error,
        )
        self.assertEqual(result.candidates[1].message.text, "Second body")
        self.assertIsNone(result.candidates[1].message_error)

    def test_scan_candidates_reports_scan_window_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "last_scan.txt").write_text(
                "2026-05-07T12:00:00Z\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(scan_mail, "himalaya_envelope_list", return_value=[]),
                mock.patch.object(
                    scan_mail, "datetime", wraps=scan_mail.datetime
                ) as datetime_mock,
            ):
                datetime_mock.now.return_value = datetime(
                    2026,
                    5,
                    8,
                    12,
                    0,
                    0,
                    tzinfo=UTC,
                )
                result = scan_mail.scan_candidates(skill_dir)

        self.assertEqual(result.last_scan, "2026-05-07T12:00:00Z")
        self.assertEqual(result.scan_window_days, 3)

    def test_scan_candidates_passes_scan_window_to_envelope_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 3",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "last_scan.txt").write_text(
                "2026-05-07T12:00:00Z\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(
                    scan_mail,
                    "himalaya_envelope_list",
                    return_value=[],
                ) as envelope_list,
                mock.patch.object(
                    scan_mail,
                    "datetime",
                    wraps=scan_mail.datetime,
                ) as datetime_mock,
            ):
                datetime_mock.now.return_value = datetime(
                    2026,
                    5,
                    8,
                    12,
                    0,
                    0,
                    tzinfo=UTC,
                )
                scan_mail.scan_candidates(skill_dir)

        args, _kwargs = envelope_list.call_args
        self.assertEqual(args[1:], ("personal", "INBOX", 3))

    def test_scan_candidates_includes_thread_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "config.toml").write_text(
                "\n".join(
                    [
                        "lookback_days = 14",
                        'raw_output_dir = "raw/"',
                        'accounts = ["personal"]',
                        'folders = ["INBOX"]',
                        "max_messages_per_folder = 5",
                        "max_thread_context_messages = 1",
                    ]
                ),
                encoding="utf-8",
            )
            target = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="target",
                flags=[],
                subject="Project update",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:05:12Z",
                has_attachment=False,
            )
            related = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="related",
                flags=[],
                subject="Re: Project update",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:10:12Z",
                has_attachment=False,
            )
            unrelated = scan_mail.Envelope(
                account="personal",
                folder="INBOX",
                id="unrelated",
                flags=[],
                subject="Different topic",
                from_addr=None,
                to_addrs=[],
                date="2026-05-07T20:15:12Z",
                has_attachment=False,
            )

            with mock.patch.object(
                scan_mail,
                "himalaya_envelope_list",
                return_value=[target, related, unrelated],
            ):
                result = scan_mail.scan_candidates(skill_dir, limit=1)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.candidates[0].envelope.id, "target")
        self.assertEqual(
            [envelope.id for envelope in result.candidates[0].thread_context],
            ["related"],
        )

    def test_envelope_list_query_without_scan_window_is_empty(self) -> None:
        self.assertEqual(himalaya_client.envelope_list_query(), [])

    def test_envelope_list_query_with_scan_window_filters_and_sorts(self) -> None:
        with mock.patch.object(
            himalaya_client,
            "scan_window_after_date",
            return_value="2026-05-05",
        ):
            self.assertEqual(
                himalaya_client.envelope_list_query(3),
                ["after", "2026-05-05", "order", "by", "date", "desc"],
            )

    def test_himalaya_envelope_list_accepts_page_size_override(self) -> None:
        config = scan_mail.MailConfig(
            lookback_days=14,
            raw_output_dir="raw/",
            accounts=["personal"],
            folders=["INBOX"],
            max_messages_per_folder=5,
            max_thread_context_messages=3,
            wiki="example-wiki",
        )

        with mock.patch.object(
            himalaya_client, "run_command", return_value="[]"
        ) as run:
            envelopes = scan_mail.himalaya_envelope_list(
                config,
                "personal",
                "INBOX",
                window_days=3,
                page_size=20,
            )

        self.assertEqual(envelopes, [])
        self.assertEqual(
            run.call_args.args[0],
            [
                "himalaya",
                "envelope",
                "list",
                "--account",
                "personal",
                "--folder",
                "INBOX",
                "--page-size",
                "20",
                "--output",
                "json",
                "after",
                himalaya_client.scan_window_after_date(3),
                "order",
                "by",
                "date",
                "desc",
            ],
        )

    def test_decision_template_from_candidates_defaults_to_ambiguous(self) -> None:
        envelope = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        candidate = scan_mail.Candidate(
            envelope=envelope,
            message=None,
            message_error=None,
            thread_context=[],
        )

        decisions = scan_mail.decision_template_from_candidates([candidate])

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].account, "personal")
        self.assertEqual(decisions[0].folder, "INBOX")
        self.assertEqual(decisions[0].envelope_id, "123")
        self.assertEqual(decisions[0].decision, "ambiguous")

    def test_decisions_template_command_outputs_decision_array(self) -> None:
        envelope = scan_mail.Envelope(
            account="personal",
            folder="INBOX",
            id="123",
            flags=[],
            subject="Project update",
            from_addr=None,
            to_addrs=[],
            date="2026-05-07T20:05:12Z",
            has_attachment=False,
        )
        result = scan_mail.ScanResult(
            ok=True,
            accounts=["personal"],
            folders=["INBOX"],
            candidate_count=1,
            candidates=[
                scan_mail.Candidate(
                    envelope=envelope,
                    message=None,
                    message_error=None,
                    thread_context=[],
                )
            ],
            excluded_count=0,
            excluded=[],
            scan_window_days=14,
            last_scan=None,
        )

        output = io.StringIO()
        with mock.patch.object(scan_mail, "scan_candidates", return_value=result):
            with redirect_stdout(output):
                exit_code = scan_mail.main(
                    [
                        "decisions-template",
                        "--skill-dir",
                        "/tmp/example-skill",
                        "--limit",
                        "1",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            [
                {
                    "account": "personal",
                    "decision": "ambiguous",
                    "envelope_id": "123",
                    "folder": "INBOX",
                }
            ],
        )

    def test_scan_window_days_without_last_scan_uses_lookback(self) -> None:
        self.assertEqual(
            scan_mail.scan_window_days(
                lookback_days=14,
                last_scan=None,
                now=datetime(2026, 5, 8, tzinfo=UTC),
            ),
            14,
        )

    def test_scan_window_days_with_invalid_last_scan_uses_lookback(self) -> None:
        self.assertEqual(
            scan_mail.scan_window_days(
                lookback_days=14,
                last_scan="not-a-timestamp",
                now=datetime(2026, 5, 8, tzinfo=UTC),
            ),
            14,
        )

    def test_scan_window_days_with_future_last_scan_uses_lookback(self) -> None:
        self.assertEqual(
            scan_mail.scan_window_days(
                lookback_days=14,
                last_scan="2026-05-09T00:00:00Z",
                now=datetime(2026, 5, 8, tzinfo=UTC),
            ),
            14,
        )

    def test_scan_window_days_with_recent_last_scan_uses_small_window(self) -> None:
        self.assertEqual(
            scan_mail.scan_window_days(
                lookback_days=14,
                last_scan="2026-05-07T12:00:00Z",
                now=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC),
            ),
            3,
        )

    def test_scan_window_days_caps_old_last_scan_at_lookback(self) -> None:
        self.assertEqual(
            scan_mail.scan_window_days(
                lookback_days=14,
                last_scan="2026-04-01T00:00:00Z",
                now=datetime(2026, 5, 8, tzinfo=UTC),
            ),
            14,
        )


if __name__ == "__main__":
    unittest.main()
