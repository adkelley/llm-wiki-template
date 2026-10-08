import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1] / "refresh_slack.sh"
).resolve()


class RefreshSlackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.raw_slack = self.root / "raw" / "Slack"
        self.raw_slack.mkdir(parents=True)
        self.fake_slackdump = self.root / "fake-slackdump.sh"
        self.calls = self.root / "calls.txt"
        self.fake_slackdump.write_text(
            "#!/usr/bin/env bash\n"
            "set -u\n"
            "printf '%s\\n' \"$*\" >> \"$CALLS_FILE\"\n"
            "printf 'fake slackdump output for %s\\n' \"$*\"\n"
            "if [[ \"${FAIL_RESUME:-0}\" == 1 && \"$1\" == \"resume\" && \"$2\" != \"--dedupe\" ]]; then exit 7; fi\n"
            "if [[ \"${FAIL_DEDUPE:-0}\" == 1 && \"$2\" == \"--dedupe\" ]]; then exit 9; fi\n",
            encoding="utf-8",
        )
        self.fake_slackdump.chmod(
            self.fake_slackdump.stat().st_mode | stat.S_IXUSR
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_refresh(self, *archives: Path, **extra_env: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update(
            {
                "SLACKDUMP_BIN": str(self.fake_slackdump),
                "CALLS_FILE": str(self.calls),
                **extra_env,
            }
        )
        return subprocess.run(
            [str(SCRIPT), *(str(archive) for archive in archives)],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def make_archive(self, name: str) -> Path:
        archive = self.raw_slack / name
        archive.mkdir()
        (archive / "slackdump.sqlite").touch()
        return archive

    def summary_for(self, archive: Path) -> dict:
        return json.loads(
            (
                self.root
                / ".llm-wiki"
                / "slack"
                / archive.name
                / "refresh"
                / "latest.json"
            ).read_text(encoding="utf-8")
        )

    def test_runs_resume_then_dedupe_and_writes_log_and_summary(self) -> None:
        archive = self.make_archive("project alpha")

        result = self.run_refresh(archive)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fake slackdump output for resume", result.stdout)
        self.assertIn("fake slackdump output for resume --dedupe", result.stdout)
        self.assertEqual(
            self.calls.read_text(encoding="utf-8").splitlines(),
            [f"resume {archive}", f"resume --dedupe {archive}"],
        )
        summary = self.summary_for(archive)
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["resume"]["exit_code"], 0)
        self.assertEqual(summary["dedupe"]["exit_code"], 0)
        log_path = Path(summary["log"])
        self.assertTrue(log_path.is_file())
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("fake slackdump output", log)
        self.assertIn("Refresh status: success", log)

    def test_resume_failure_skips_dedupe_and_records_failure(self) -> None:
        archive = self.make_archive("project-alpha")

        result = self.run_refresh(archive, FAIL_RESUME="1")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.calls.read_text(encoding="utf-8").splitlines(),
            [f"resume {archive}"],
        )
        summary = self.summary_for(archive)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["resume"]["exit_code"], 7)
        self.assertEqual(summary["dedupe"]["exit_code"], 1)
        self.assertIn("Skipping dedupe", Path(summary["log"]).read_text())

    def test_discovers_all_archives_when_no_arguments_are_given(self) -> None:
        first = self.make_archive("first")
        second = self.make_archive("second")

        result = self.run_refresh()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / ".llm-wiki" / "slack" / first.name).is_dir())
        self.assertTrue((self.root / ".llm-wiki" / "slack" / second.name).is_dir())
        self.assertEqual(len(self.calls.read_text(encoding="utf-8").splitlines()), 4)

    def test_existing_lock_prevents_refresh(self) -> None:
        archive = self.make_archive("locked")
        lock = self.root / ".llm-wiki" / "slack" / archive.name / "refresh" / ".lock"
        lock.mkdir(parents=True)

        result = self.run_refresh(archive)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already running", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_dedupe_failure_is_reported(self) -> None:
        archive = self.make_archive("dedupe-fails")

        result = self.run_refresh(archive, FAIL_DEDUPE="1")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.calls.read_text(encoding="utf-8").splitlines(),
            [f"resume {archive}", f"resume --dedupe {archive}"],
        )
        summary = self.summary_for(archive)
        self.assertEqual(summary["resume"]["exit_code"], 0)
        self.assertEqual(summary["dedupe"]["exit_code"], 9)
        self.assertEqual(summary["status"], "failed")


if __name__ == "__main__":
    unittest.main()
