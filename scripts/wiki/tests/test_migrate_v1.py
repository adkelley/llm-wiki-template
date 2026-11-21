from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "migrate_v1.py"
SPEC = importlib.util.spec_from_file_location("migrate_v1", SCRIPT_PATH)
assert SPEC is not None, "Failed to load migrate_v1 module"
assert SPEC.loader is not None, "Failed to load migrate_v1 module"

migrate_v1 = importlib.util.module_from_spec(SPEC)
sys.modules["migrate_v1"] = migrate_v1
SPEC.loader.exec_module(migrate_v1)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def page_bytes(
    page_type: str,
    *,
    stable_id: tuple[str, str] | None = None,
    newline: str = "\n",
    body: str = "Body text that must remain unchanged.",
) -> bytes:
    lines = ["---", f"type: {page_type}"]
    if stable_id is not None:
        field, value = stable_id
        lines.append(f"{field}: {value}")
    lines.extend([f'title: "Example {page_type.title()}"', "---", "", body, ""])
    return newline.join(lines).encode("utf-8")


class MigrateV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.wiki_dir = Path(self.temporary_directory.name) / "wiki"
        self.wiki_dir.mkdir()

    def write_page(
        self,
        directory: str,
        filename: str,
        page_type: str,
        *,
        stable_id: tuple[str, str] | None = None,
        newline: str = "\n",
        body: str = "Body text that must remain unchanged.",
        nested_directory: str | None = None,
    ) -> Path:
        parent = self.wiki_dir / directory
        if nested_directory is not None:
            parent /= nested_directory
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / filename
        path.write_bytes(
            page_bytes(
                page_type,
                stable_id=stable_id,
                newline=newline,
                body=body,
            )
        )
        return path

    def test_build_plan_finds_every_supported_page_type(self) -> None:
        for page_type in migrate_v1.PAGE_TYPES:
            self.write_page(
                page_type.directory,
                f"example-{page_type.frontmatter_type}.md",
                page_type.frontmatter_type,
            )

        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        self.assertTrue(migration.is_valid)
        self.assertEqual(len(migration.pages), len(migrate_v1.PAGE_TYPES))
        self.assertTrue(all(page.needs_change for page in migration.pages))

    def test_preview_render_does_not_write_page(self) -> None:
        path = self.write_page("entities", "acme.md", "entity")
        original = path.read_bytes()
        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        rendered = migrate_v1.render_page(migration.pages[0])

        self.assertIn("entity_id: entity:acme\n", rendered)
        self.assertEqual(path.read_bytes(), original)

    def test_apply_inserts_one_id_line_and_preserves_body(self) -> None:
        body = "First body line.\n\nSecond body line."
        path = self.write_page("entities", "acme.md", "entity", body=body)
        original = path.read_text(encoding="utf-8")
        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        changed = migrate_v1.apply_migration(migration)

        expected = original.replace(
            "type: entity\n",
            "type: entity\nentity_id: entity:acme\n",
            1,
        )
        self.assertEqual(changed, (path,))
        self.assertEqual(path.read_text(encoding="utf-8"), expected)
        self.assertEqual(path.read_text(encoding="utf-8").count("entity_id:"), 1)
        self.assertTrue(path.read_text(encoding="utf-8").endswith(body + "\n"))

    def test_existing_valid_id_is_preserved(self) -> None:
        path = self.write_page(
            "entities",
            "renamed-page.md",
            "entity",
            stable_id=("entity_id", "entity:permanent-id"),
        )
        original = path.read_bytes()
        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        changed = migrate_v1.apply_migration(migration)

        self.assertTrue(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertEqual(changed, ())
        self.assertEqual(path.read_bytes(), original)

    def test_second_apply_is_idempotent(self) -> None:
        path = self.write_page("concepts", "machine-learning.md", "concept")
        first_plan = migrate_v1.build_migration_plan(self.wiki_dir)
        migrate_v1.apply_migration(first_plan)
        after_first_apply = path.read_bytes()

        second_plan = migrate_v1.build_migration_plan(self.wiki_dir)
        second_changed = migrate_v1.apply_migration(second_plan)

        self.assertTrue(second_plan.is_valid)
        self.assertEqual(second_changed, ())
        self.assertEqual(path.read_bytes(), after_first_apply)

    def test_invalid_page_prevents_all_writes(self) -> None:
        valid_path = self.write_page("entities", "acme.md", "entity")
        invalid_path = self.write_page("concepts", "wrong-type.md", "entity")
        originals = {
            valid_path: valid_path.read_bytes(),
            invalid_path: invalid_path.read_bytes(),
        }
        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        with self.assertRaisesRegex(ValueError, "invalid migration"):
            migrate_v1.apply_migration(migration)

        self.assertFalse(migration.is_valid)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_duplicate_ids_are_rejected_without_writes(self) -> None:
        first = self.write_page("entities", "acme.md", "entity")
        second = self.write_page(
            "entities",
            "acme.md",
            "entity",
            nested_directory="archive",
        )
        originals = {first: first.read_bytes(), second: second.read_bytes()}
        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        with self.assertRaisesRegex(ValueError, "invalid migration"):
            migrate_v1.apply_migration(migration)

        self.assertFalse(migration.is_valid)
        self.assertTrue(any("duplicate ID" in error for error in migration.errors))
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_apply_preserves_lf_and_crlf_line_endings(self) -> None:
        lf_path = self.write_page("concepts", "lf-page.md", "concept", newline="\n")
        crlf_path = self.write_page(
            "entities",
            "crlf-page.md",
            "entity",
            newline="\r\n",
        )
        migration = migrate_v1.build_migration_plan(self.wiki_dir)

        migrate_v1.apply_migration(migration)

        lf_bytes = lf_path.read_bytes()
        crlf_bytes = crlf_path.read_bytes()
        self.assertIn(b"concept_id: concept:lf-page\n", lf_bytes)
        self.assertNotIn(b"\r\n", lf_bytes)
        self.assertIn(b"entity_id: entity:crlf-page\r\n", crlf_bytes)
        self.assertNotIn(b"\n", crlf_bytes.replace(b"\r\n", b""))

    def test_cli_help_describes_supported_options(self) -> None:
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("--wiki-dir", result.stdout)
        self.assertIn("--apply", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_cli_preview_succeeds_without_writing(self) -> None:
        path = self.write_page("entities", "acme.md", "entity")
        original = path.read_bytes()

        result = run_cli("--wiki-dir", str(self.wiki_dir))

        self.assertEqual(result.returncode, 0)
        self.assertIn("pages=1", result.stdout)
        self.assertIn("valid=True", result.stdout)
        self.assertIn("pending=1", result.stdout)
        self.assertIn(f"would update: {path}", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(path.read_bytes(), original)

    def test_cli_apply_writes_and_reports_update(self) -> None:
        path = self.write_page("entities", "acme.md", "entity")

        result = run_cli("--wiki-dir", str(self.wiki_dir), "--apply")

        self.assertEqual(result.returncode, 0)
        self.assertIn(f"updated: {path}", result.stdout)
        self.assertNotIn("would update:", result.stdout)
        self.assertIn("entity_id: entity:acme\n", path.read_text(encoding="utf-8"))
        self.assertEqual(result.stderr, "")

    def test_cli_missing_wiki_returns_failure_without_traceback(self) -> None:
        missing_wiki = self.wiki_dir / "missing"

        result = run_cli("--wiki-dir", str(missing_wiki))

        self.assertEqual(result.returncode, 1)
        self.assertIn("valid=False", result.stdout)
        self.assertIn("wiki directory does not exist", result.stdout)
        self.assertNotIn("Traceback", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stderr, "")

    def test_cli_second_run_is_idempotent(self) -> None:
        path = self.write_page("concepts", "machine-learning.md", "concept")
        first_result = run_cli("--wiki-dir", str(self.wiki_dir), "--apply")
        after_first_apply = path.read_bytes()

        second_result = run_cli("--wiki-dir", str(self.wiki_dir))

        self.assertEqual(first_result.returncode, 0)
        self.assertEqual(second_result.returncode, 0)
        self.assertIn("pending=0", second_result.stdout)
        self.assertNotIn("would update:", second_result.stdout)
        self.assertEqual(second_result.stderr, "")
        self.assertEqual(path.read_bytes(), after_first_apply)

    def test_cli_preview_json(self) -> None:
        path = self.write_page("entities", "acme.md", "entity")
        original = path.read_bytes()

        result = run_cli("--wiki-dir", str(self.wiki_dir), "--json")

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(
            report,
            {
                "wiki_dir": str(self.wiki_dir),
                "apply": False,
                "page_count": 1,
                "pending_count": 1,
                "changed_count": 0,
                "error_count": 0,
                "valid": True,
                "errors": [],
                "pending_paths": [str(path)],
                "changed_paths": [],
            },
        )
        self.assertNotIn("would update:", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(path.read_bytes(), original)

    def test_cli_apply_json(self) -> None:
        path = self.write_page("entities", "acme.md", "entity")

        result = run_cli("--wiki-dir", str(self.wiki_dir), "--apply", "--json")

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["wiki_dir"], str(self.wiki_dir))
        self.assertIs(report["apply"], True)
        self.assertEqual(report["page_count"], 1)
        self.assertEqual(report["pending_count"], 1)
        self.assertEqual(report["changed_count"], 1)
        self.assertEqual(report["error_count"], 0)
        self.assertIs(report["valid"], True)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["pending_paths"], [str(path)])
        self.assertEqual(report["changed_paths"], [str(path)])
        self.assertNotIn("updated:", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertIn("entity_id: entity:acme\n", path.read_text(encoding="utf-8"))

    def test_cli_invalid_wiki_json(self) -> None:
        missing_wiki = self.wiki_dir / "missing"

        result = run_cli("--wiki-dir", str(missing_wiki), "--json")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["wiki_dir"], str(missing_wiki))
        self.assertIs(report["apply"], False)
        self.assertEqual(report["page_count"], 0)
        self.assertEqual(report["pending_count"], 0)
        self.assertEqual(report["changed_count"], 0)
        self.assertEqual(report["error_count"], 1)
        self.assertIs(report["valid"], False)
        self.assertEqual(report["pending_paths"], [])
        self.assertEqual(report["changed_paths"], [])
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("wiki directory does not exist", report["errors"][0])
        self.assertNotIn("error:", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
