from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "migrate_v2.py"
SPEC = importlib.util.spec_from_file_location("migrate_v2", SCRIPT_PATH)
assert SPEC is not None, "Failed to load migrate_v2 module"
assert SPEC.loader is not None, "Failed to load migrate_v2 module"

migrate_v2 = importlib.util.module_from_spec(SPEC)
sys.modules["migrate_v2"] = migrate_v2
SPEC.loader.exec_module(migrate_v2)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def entity_page(*, newline: str = "\n") -> bytes:
    lines = [
        "---",
        "type: entity",
        "entity_id: entity:acme",
        'title: "Acme Corporation"',
        "entity_type: company",
        "---",
        "",
        "# Acme Corporation",
        "",
    ]
    return (newline.join(lines) + newline).encode("utf-8")


class MigrateV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.wiki_dir = Path(self.temporary_directory.name) / "wiki"
        self.wiki_dir.mkdir()
        self.entities_dir = self.wiki_dir / "entities"

    def write_entity_page(
        self,
        *frontmatter_lines: str,
        filename: str = "acme.md",
        nested_directory: str | None = None,
        page_type: str = "entity",
        entity_id: str = "entity:acme",
        body_lines: tuple[str, ...] = (),
        newline: str = "\n",
    ) -> Path:
        parent = self.entities_dir
        if nested_directory is not None:
            parent /= nested_directory
        parent.mkdir(parents=True, exist_ok=True)

        path = parent / filename
        lines = [
            "---",
            f"type: {page_type}",
            f"entity_id: {entity_id}",
            *frontmatter_lines,
            "---",
            "",
            *body_lines,
        ]
        path.write_text(newline.join(lines), encoding="utf-8", newline="")
        return path

    def test_render_page_renames_title_to_canonical_name(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_bytes(entity_page())

        migration = migrate_v2.build_migration_plan(entities_dir)
        rendered = migrate_v2.render_page(migration.pages[0])

        self.assertIn('canonical_name: "Acme Corporation"\n', rendered)
        self.assertNotIn(
            '\ntitle: "Acme Corporation"\n',
            rendered,
        )
        self.assertIn("# Acme Corporation", rendered)
        self.assertEqual(path.read_bytes(), entity_page())

    def test_render_page_renames_title_with_key_spacing(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = "\n".join(
            [
                "---",
                "type: entity",
                "entity_id: entity:acme",
                'title : "Acme Corporation"',
                "---",
                "",
            ]
        )
        path.write_text(original, encoding="utf-8")

        migration = migrate_v2.build_migration_plan(entities_dir)

        self.assertTrue(migration.is_valid)
        rendered = migrate_v2.render_page(migration.pages[0])
        self.assertIn('canonical_name: "Acme Corporation"', rendered)
        self.assertNotIn('\ntitle : "Acme Corporation"', rendered)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_render_page_removes_title_when_canonical_name_exists(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = "\n".join(
            [
                "---",
                "type: entity",
                "entity_id: entity:acme",
                'title: "Old Acme Name"',
                'canonical_name: "Acme Corporation"',
                "aliases: []",
                "abbreviations: []",
                "known_variants: []",
                "known_errors: []",
                "---",
                "",
            ]
        )
        path.write_text(original, encoding="utf-8")

        migration = migrate_v2.build_migration_plan(entities_dir)
        rendered = migrate_v2.render_page(migration.pages[0])

        self.assertEqual(rendered.count("\ncanonical_name:"), 1)
        self.assertIn('canonical_name: "Acme Corporation"', rendered)
        self.assertNotIn('\ntitle: "Old Acme Name"', rendered)
        self.assertNotIn('canonical_name: "Old Acme Name"', rendered)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_render_page_completes_canonical_only_partial_page(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = "\n".join(
            [
                "---",
                "type: entity",
                "entity_id: entity:acme",
                'canonical_name: "Acme Corporation"',
                "aliases:",
                "  - Acme Corp",
                "---",
                "",
            ]
        )
        path.write_text(original, encoding="utf-8")

        migration = migrate_v2.build_migration_plan(entities_dir)
        page = migration.pages[0]

        self.assertTrue(page.needs_change)
        self.assertEqual(
            page.missing_name_fields,
            ("abbreviations", "known_variants", "known_errors"),
        )

        rendered = migrate_v2.render_page(page)

        self.assertIn(
            "\n".join(
                [
                    'canonical_name: "Acme Corporation"',
                    "abbreviations: []",
                    "known_variants: []",
                    "known_errors: []",
                ]
            ),
            rendered,
        )
        self.assertIn("aliases:\n  - Acme Corp", rendered)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_build_plan_accepts_populated_block_list_with_key_spacing(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases :",
            "  - Acme Corp",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertTrue(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)

    def test_build_plan_finds_nested_entity_pages(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        nested_dir = entities_dir / "archive"
        nested_dir.mkdir(parents=True)
        path = nested_dir / "acme.md"
        path.write_bytes(entity_page())

        migration = migrate_v2.build_migration_plan(entities_dir)

        self.assertTrue(migration.is_valid)
        self.assertEqual(len(migration.pages), 1)
        self.assertEqual(migration.pages[0].path, path)
        self.assertTrue(migration.pages[0].needs_change)
        self.assertEqual(
            migration.pages[0].proposed_canonical_name,
            '"Acme Corporation"',
        )

    def test_build_plan_identifies_missing_name_fields(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_bytes(entity_page())

        migration = migrate_v2.build_migration_plan(entities_dir)

        self.assertTrue(migration.is_valid)
        self.assertEqual(
            migration.pages[0].missing_name_fields,
            (
                "aliases",
                "abbreviations",
                "known_variants",
                "known_errors",
            ),
        )

    def test_build_plan_prefers_existing_canonical_name(self) -> None:
        self.write_entity_page(
            'title: "Old Acme Name"',
            'canonical_name: "Acme Corporation"',
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertTrue(migration.is_valid)
        page = migration.pages[0]
        self.assertEqual(page.existing_title, '"Old Acme Name"')
        self.assertEqual(page.existing_canonical_name, '"Acme Corporation"')
        self.assertEqual(page.proposed_canonical_name, '"Acme Corporation"')
        self.assertEqual(page.missing_name_fields, ())
        self.assertTrue(page.needs_change)

    def test_build_plan_rejects_entity_without_a_name(self) -> None:
        self.write_entity_page(
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertIsNone(migration.pages[0].proposed_canonical_name)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "missing title or canonical_name" in error for error in migration.errors
            )
        )

    def test_build_plan_rejects_empty_canonical_name(self) -> None:
        self.write_entity_page(
            "canonical_name:",
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "canonical_name must not be empty" in error
                for error in migration.errors
            )
        )

    def test_build_plan_rejects_quoted_empty_canonical_name(self) -> None:
        self.write_entity_page(
            'canonical_name: ""',
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "canonical_name must not be empty" in error
                for error in migration.errors
            )
        )

    def test_build_plan_rejects_list_as_canonical_name(self) -> None:
        self.write_entity_page(
            "canonical_name: []",
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "canonical_name must be a scalar" in error
                for error in migration.errors
            )
        )

    def test_build_plan_rejects_populated_list_as_canonical_name(self) -> None:
        self.write_entity_page(
            'canonical_name: ["Acme Corporation"]',
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "canonical_name must be a scalar" in error
                for error in migration.errors
            )
        )

    def test_build_plan_rejects_empty_legacy_title(self) -> None:
        self.write_entity_page(
            "title:",
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any("title must not be empty" in error for error in migration.errors)
        )

    def test_build_plan_rejects_non_list_name_field(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases: Acme Corp",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "aliases must be a list" in error for error in migration.errors
            )
        )

    def test_build_plan_rejects_bare_name_field_without_list_items(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases:",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "aliases must be a list" in error for error in migration.errors
            )
        )

    def test_build_plan_rejects_malformed_block_list(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases:",
            "  - Acme Corp",
            "  not-a-list-item",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(
            any("aliases must be a list" in error for error in migration.errors)
        )

    def test_build_plan_rejects_duplicate_name_field(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases: []",
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any(
                "duplicate field: aliases" in error for error in migration.errors
            )
        )

    def test_build_plan_rejects_duplicate_field_with_key_spacing(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases: []",
            "aliases : []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(
            any(
                "duplicate field: aliases" in error for error in migration.errors
            )
        )

    def test_build_plan_reports_malformed_frontmatter_once(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_text(
            "\n".join(
                [
                    "---",
                    "type: entity",
                    "entity_id: entity:acme",
                    'title: "Acme Corporation"',
                ]
            ),
            encoding="utf-8",
        )

        migration = migrate_v2.build_migration_plan(entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertEqual(len(migration.pages), 1)
        self.assertEqual(len(migration.pages[0].errors), 1)
        self.assertEqual(migration.errors, migration.pages[0].errors)
        self.assertIn("missing closing frontmatter delimiter", migration.errors[0])

    def test_build_plan_rejects_top_level_frontmatter_line_without_colon(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_text(
            "\n".join(
                [
                    "---",
                    "type: entity",
                    "entity_id: entity:acme",
                    'canonical_name: "Acme Corporation"',
                    "not-a-frontmatter-field",
                    "aliases: []",
                    "abbreviations: []",
                    "known_variants: []",
                    "known_errors: []",
                    "---",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        migration = migrate_v2.build_migration_plan(entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(
            any(
                "malformed frontmatter line" in error
                for error in migration.errors
            )
        )

    def test_build_plan_rejects_page_with_wrong_type(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
            page_type="concept",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertFalse(migration.pages[0].needs_change)
        self.assertTrue(
            any("expected type: entity" in error for error in migration.errors)
        )

    def test_build_plan_ignores_markdown_files_outside_entities(self) -> None:
        self.entities_dir.mkdir()
        concepts_dir = self.wiki_dir / "concepts"
        concepts_dir.mkdir()
        concept_path = concepts_dir / "knowledge-graph.md"
        concept_path.write_text(
            "\n".join(
                [
                    "---",
                    "type: concept",
                    "concept_id: concept:knowledge-graph",
                    'title: "Knowledge Graph"',
                    "---",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        original = concept_path.read_bytes()

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        changed = migrate_v2.apply_migration(migration)

        self.assertTrue(migration.is_valid)
        self.assertEqual(migration.pages, ())
        self.assertEqual(changed, ())
        self.assertEqual(concept_path.read_bytes(), original)

    def test_build_plan_rejects_yaml_null_canonical_names(self) -> None:
        for null_value in ("null", "Null", "NULL", "~"):
            with self.subTest(null_value=null_value):
                self.write_entity_page(
                    f"canonical_name: {null_value}",
                    "aliases: []",
                    "abbreviations: []",
                    "known_variants: []",
                    "known_errors: []",
                )

                migration = migrate_v2.build_migration_plan(self.entities_dir)

                self.assertFalse(migration.is_valid)
                self.assertFalse(migration.pages[0].needs_change)
                self.assertTrue(
                    any(
                        "canonical_name must not be null" in error
                        for error in migration.errors
                    )
                )

    def test_build_plan_rejects_null_name_list_item(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases:",
            "  -",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(
            any(
                "aliases must contain non-empty scalar values" in error
                for error in migration.errors
            )
        )

    def test_build_plan_rejects_mapping_name_list_item(self) -> None:
        self.write_entity_page(
            'canonical_name: "Acme Corporation"',
            "aliases:",
            "  - name: Acme Corp",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(
            any(
                "aliases must contain non-empty scalar values" in error
                for error in migration.errors
            )
        )

    def test_render_page_adds_missing_name_fields_in_order(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_bytes(entity_page())

        migration = migrate_v2.build_migration_plan(entities_dir)
        rendered = migrate_v2.render_page(migration.pages[0])

        expected = "\n".join(
            [
                'canonical_name: "Acme Corporation"',
                "aliases: []",
                "abbreviations: []",
                "known_variants: []",
                "known_errors: []",
            ]
        )
        self.assertIn(expected, rendered)
        self.assertEqual(path.read_bytes(), entity_page())

    def test_render_page_preserves_populated_name_lists(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = "\n".join(
            [
                "---",
                "type: entity",
                "entity_id: entity:acme",
                'title: "Acme Corporation"',
                "aliases:",
                '  - "Acme Corp"',
                '  - "Acme Company"',
                "abbreviations:",
                '  - "ACME"',
                "known_variants:",
                '  - "Acme Co."',
                "known_errors:",
                '  - "Acnee"',
                "---",
                "",
            ]
        )
        path.write_text(original, encoding="utf-8")

        migration = migrate_v2.build_migration_plan(entities_dir)
        rendered = migrate_v2.render_page(migration.pages[0])

        self.assertTrue(migration.is_valid)
        self.assertEqual(migration.pages[0].missing_name_fields, ())
        self.assertIn(
            "\n".join(
                [
                    "aliases:",
                    '  - "Acme Corp"',
                    '  - "Acme Company"',
                    "abbreviations:",
                    '  - "ACME"',
                    "known_variants:",
                    '  - "Acme Co."',
                    "known_errors:",
                    '  - "Acnee"',
                ]
            ),
            rendered,
        )
        for field in migrate_v2.NAME_FIELDS:
            self.assertNotIn(f"{field}: []", rendered)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_apply_migration_writes_entity_page(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = entity_page()
        path.write_bytes(original)

        migration = migrate_v2.build_migration_plan(entities_dir)
        changed = migrate_v2.apply_migration(migration)

        self.assertEqual(changed, (path,))
        migrated = path.read_text(encoding="utf-8")
        self.assertIn(
            "\n".join(
                [
                    'canonical_name: "Acme Corporation"',
                    "aliases: []",
                    "abbreviations: []",
                    "known_variants: []",
                    "known_errors: []",
                ]
            ),
            migrated,
        )
        self.assertNotIn('\ntitle: "Acme Corporation"\n', migrated)
        self.assertIn("# Acme Corporation", migrated)
        self.assertNotEqual(path.read_bytes(), original)

    def test_invalid_page_prevents_all_migration_writes(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()

        valid_path = entities_dir / "acme.md"
        valid_path.write_bytes(entity_page())

        invalid_path = entities_dir / "invalid.md"
        invalid_path.write_text(
            "\n".join(
                [
                    "---",
                    "type: entity",
                    "entity_id: entity:invalid",
                    'canonical_name: "Invalid Entity"',
                    "aliases: not-a-list",
                    "abbreviations: []",
                    "known_variants: []",
                    "known_errors: []",
                    "---",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        originals = {
            valid_path: valid_path.read_bytes(),
            invalid_path: invalid_path.read_bytes(),
        }

        migration = migrate_v2.build_migration_plan(entities_dir)

        self.assertFalse(migration.is_valid)
        with self.assertRaisesRegex(ValueError, "invalid migration"):
            migrate_v2.apply_migration(migration)

        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_second_apply_is_idempotent(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_bytes(entity_page())

        first_plan = migrate_v2.build_migration_plan(entities_dir)
        first_changed = migrate_v2.apply_migration(first_plan)
        after_first_apply = path.read_bytes()

        second_plan = migrate_v2.build_migration_plan(entities_dir)
        second_changed = migrate_v2.apply_migration(second_plan)

        self.assertEqual(first_changed, (path,))
        self.assertTrue(second_plan.is_valid)
        self.assertFalse(second_plan.pages[0].needs_change)
        self.assertEqual(second_changed, ())
        self.assertEqual(path.read_bytes(), after_first_apply)

    def test_apply_preserves_lf_and_crlf_line_endings(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        lf_path = entities_dir / "lf.md"
        crlf_path = entities_dir / "crlf.md"
        lf_path.write_bytes(entity_page(newline="\n"))
        crlf_path.write_bytes(entity_page(newline="\r\n"))

        migration = migrate_v2.build_migration_plan(entities_dir)
        migrate_v2.apply_migration(migration)

        lf_bytes = lf_path.read_bytes()
        crlf_bytes = crlf_path.read_bytes()
        self.assertIn(b'canonical_name: "Acme Corporation"\n', lf_bytes)
        self.assertNotIn(b"\r\n", lf_bytes)
        self.assertIn(b'canonical_name: "Acme Corporation"\r\n', crlf_bytes)
        self.assertNotIn(b"\n", crlf_bytes.replace(b"\r\n", b""))

    def test_cli_preview_reports_pending_page_without_writing(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = entity_page()
        path.write_bytes(original)

        result = run_cli("--wiki-dir", str(self.wiki_dir))

        self.assertEqual(result.returncode, 0)
        self.assertIn("pages=1", result.stdout)
        self.assertIn("valid=True", result.stdout)
        self.assertIn("pending=1", result.stdout)
        self.assertIn(f"would update: {path}", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(path.read_bytes(), original)

    def test_cli_apply_writes_and_reports_updated_page(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_bytes(entity_page())

        result = run_cli("--wiki-dir", str(self.wiki_dir), "--apply")

        self.assertEqual(result.returncode, 0)
        self.assertIn("pages=1", result.stdout)
        self.assertIn("valid=True", result.stdout)
        self.assertIn("pending=1", result.stdout)
        self.assertIn(f"updated: {path}", result.stdout)
        self.assertNotIn("would update:", result.stdout)
        self.assertEqual(result.stderr, "")

        migrated = path.read_text(encoding="utf-8")
        self.assertIn('canonical_name: "Acme Corporation"', migrated)
        self.assertNotIn('\ntitle: "Acme Corporation"\n', migrated)
        for field in migrate_v2.NAME_FIELDS:
            self.assertIn(f"{field}: []", migrated)

    def test_cli_preview_json_reports_pending_page_without_writing(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        original = entity_page()
        path.write_bytes(original)

        result = run_cli("--wiki-dir", str(self.wiki_dir), "--json")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout),
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
        self.assertEqual(path.read_bytes(), original)

    def test_cli_apply_json_reports_changed_page(self) -> None:
        entities_dir = self.wiki_dir / "entities"
        entities_dir.mkdir()
        path = entities_dir / "acme.md"
        path.write_bytes(entity_page())

        result = run_cli(
            "--wiki-dir",
            str(self.wiki_dir),
            "--apply",
            "--json",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout),
            {
                "wiki_dir": str(self.wiki_dir),
                "apply": True,
                "page_count": 1,
                "pending_count": 1,
                "changed_count": 1,
                "error_count": 0,
                "valid": True,
                "errors": [],
                "pending_paths": [str(path)],
                "changed_paths": [str(path)],
            },
        )
        self.assertIn(
            'canonical_name: "Acme Corporation"',
            path.read_text(encoding="utf-8"),
        )

    def test_cli_missing_entity_directory_reports_json_error(self) -> None:
        result = run_cli("--wiki-dir", str(self.wiki_dir), "--json")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["wiki_dir"], str(self.wiki_dir))
        self.assertIs(report["apply"], False)
        self.assertEqual(report["page_count"], 0)
        self.assertEqual(report["pending_count"], 0)
        self.assertEqual(report["changed_count"], 0)
        self.assertEqual(report["error_count"], 1)
        self.assertIs(report["valid"], False)
        self.assertEqual(report["pending_paths"], [])
        self.assertEqual(report["changed_paths"], [])
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("entity directory does not exist", report["errors"][0])
        self.assertNotIn("Traceback", result.stdout)
