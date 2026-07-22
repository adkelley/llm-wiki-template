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
        for directory in (
            self.wiki_dir / "traces",
            self.wiki_dir / "tasks" / "contradiction-resolutions",
        ):
            directory.mkdir(parents=True)
            (directory / ".gitkeep").write_bytes(b"")

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

    def write_concept_page(
        self,
        *frontmatter_lines: str,
        filename: str = "knowledge-graph.md",
        body_lines: tuple[str, ...] = (),
        newline: str = "\n",
    ) -> Path:
        concepts_dir = self.wiki_dir / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)

        path = concepts_dir / filename
        lines = [
            "---",
            "type: concept",
            f"concept_id: concept:{path.stem}",
            *frontmatter_lines,
            "---",
            "",
            *body_lines,
        ]
        path.write_text(newline.join(lines), encoding="utf-8", newline="")
        return path

    def write_source_page(
        self,
        *frontmatter_lines: str,
        filename: str = "article.md",
        body_lines: tuple[str, ...] = (),
        newline: str = "\n",
        include_source_schema: bool = True,
    ) -> Path:
        sources_dir = self.wiki_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        path = sources_dir / filename
        source_schema_lines = (
            [
                'source_file: "[[raw/article.md]]"',
                "renditions: []",
                "source_type: unknown",
            ]
            if include_source_schema
            else []
        )
        supplied_fields = {
            line.partition(":")[0].strip() for line in frontmatter_lines
        }
        source_schema_lines = [
            line
            for line in source_schema_lines
            if line.partition(":")[0].strip() not in supplied_fields
        ]
        lines = [
            "---",
            "type: source",
            f"source_id: source:{path.stem}",
            *source_schema_lines,
            *frontmatter_lines,
            "---",
            "",
            *body_lines,
        ]
        path.write_text(newline.join(lines), encoding="utf-8", newline="")
        return path

    def write_work_page(
        self,
        page_type: str,
        *frontmatter_lines: str,
        filename: str | None = None,
        body_lines: tuple[str, ...] = (),
        newline: str = "\n",
    ) -> Path:
        directory = self.wiki_dir / {
            "comparison": "comparisons",
            "synthesis": "syntheses",
            "trace": "traces",
        }[page_type]
        directory.mkdir(parents=True, exist_ok=True)
        if page_type == "trace":
            gitkeep = directory / ".gitkeep"
            if gitkeep.exists():
                gitkeep.unlink()
        path = directory / (filename or f"example-{page_type}.md")
        lines = [
            "---",
            f"type: {page_type}",
            f"{page_type}_id: {page_type}:{path.stem}",
            *frontmatter_lines,
            "---",
            "",
            *body_lines,
        ]
        path.write_text(newline.join(lines), encoding="utf-8", newline="")
        return path

    def write_contradiction_page(
        self, *frontmatter_lines: str, filename: str = "pricing-conflict.md"
    ) -> Path:
        directory = self.wiki_dir / "tasks" / "contradiction-resolutions"
        gitkeep = directory / ".gitkeep"
        if gitkeep.exists():
            gitkeep.unlink()
        path = directory / filename
        lines = [
            "---",
            "type: contradiction-resolution",
            *frontmatter_lines,
            "---",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_render_source_adds_missing_renditions_and_source_type(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'source_file: "[[raw/report.md]]"',
            'attribution: "Research Team"',
            include_source_schema=False,
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        source_plan = next(
            page for page in migration.pages if page.path == source_path
        )
        rendered = migrate_v2.render_page(source_plan)

        self.assertTrue(migration.is_valid)
        self.assertEqual(
            source_plan.missing_source_fields,
            ("renditions", "source_type"),
        )
        self.assertIn(
            '\n'.join(
                [
                    'source_file: "[[raw/report.md]]"',
                    "renditions: []",
                    "source_type: unknown",
                ]
            ),
            rendered,
        )

    def test_source_schema_backfill_preserves_crlf_and_is_idempotent(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'source_file: "[[raw/report.md]]"',
            'attribution: "Research Team"',
            body_lines=("# Report", "", "Body text."),
            newline="\r\n",
            include_source_schema=False,
        )

        first_plan = migrate_v2.build_migration_plan(self.entities_dir)
        self.assertEqual(migrate_v2.apply_migration(first_plan), (source_path,))
        migrated = source_path.read_bytes()
        second_plan = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertIn(b"renditions: []\r\n", migrated)
        self.assertIn(b"source_type: unknown\r\n", migrated)
        self.assertNotIn(b"\n", migrated.replace(b"\r\n", b""))
        self.assertTrue(second_plan.is_valid)
        self.assertEqual(migrate_v2.apply_migration(second_plan), ())
        self.assertEqual(source_path.read_bytes(), migrated)

    def test_source_preserves_populated_renditions_and_allowed_type(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'source_file: "[[raw/report.md]]"',
            "renditions:",
            '  - "[[raw/report.pdf]]"',
            '  - "[[raw/report.pptx]]"',
            "source_type: presentation",
            'attribution: "Research Team"',
            include_source_schema=False,
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        source_plan = next(
            page for page in migration.pages if page.path == source_path
        )

        self.assertTrue(migration.is_valid)
        self.assertEqual(source_plan.missing_source_fields, ())
        self.assertFalse(source_plan.needs_change)
        self.assertEqual(migrate_v2.apply_migration(migration), ())

    def test_source_adds_each_missing_schema_field_independently(self) -> None:
        cases = (
            (("renditions: []",), ("source_type",), "source_type: unknown"),
            (("source_type: report",), ("renditions",), "renditions: []"),
        )
        for index, (existing, missing, expected) in enumerate(cases):
            with self.subTest(existing=existing):
                self.entities_dir.mkdir(exist_ok=True)
                source_path = self.write_source_page(
                    'source_file: "[[raw/report.md]]"',
                    *existing,
                    'attribution: "Research Team"',
                    filename=f"article-{index}.md",
                    include_source_schema=False,
                )
                migration = migrate_v2.build_migration_plan(self.entities_dir)
                source_plan = next(
                    page for page in migration.pages if page.path == source_path
                )
                self.assertEqual(source_plan.missing_source_fields, missing)
                self.assertIn(expected, migrate_v2.render_page(source_plan))

    def test_source_rejects_invalid_new_schema_fields(self) -> None:
        cases = (
            (("renditions: not-a-list", "source_type: report"), "renditions"),
            (("renditions:", "source_type: report"), "renditions"),
            (("renditions:", "  -", "source_type: report"), "renditions"),
            (("renditions: []", "source_type: magazine"), "source_type"),
        )
        for index, (fields, expected_error) in enumerate(cases):
            with self.subTest(fields=fields):
                self.entities_dir.mkdir(exist_ok=True)
                source_path = self.write_source_page(
                    'source_file: "[[raw/report.md]]"',
                    *fields,
                    'attribution: "Research Team"',
                    filename=f"invalid-{index}.md",
                    include_source_schema=False,
                )
                migration = migrate_v2.build_migration_plan(self.entities_dir)
                source_plan = next(
                    page for page in migration.pages if page.path == source_path
                )
                self.assertFalse(migration.is_valid)
                self.assertFalse(source_plan.needs_change)
                self.assertTrue(
                    any(expected_error in error for error in source_plan.errors)
                )

    def test_source_accepts_every_documented_source_type(self) -> None:
        self.entities_dir.mkdir()
        for source_type in sorted(migrate_v2.SOURCE_TYPES):
            source_path = self.write_source_page(
                'source_file: "[[raw/report.md]]"',
                "renditions: []",
                f"source_type: {source_type}",
                'attribution: "Research Team"',
                filename=f"{source_type}.md",
                include_source_schema=False,
            )
            migration = migrate_v2.build_migration_plan(self.entities_dir)
            source_plan = next(
                page for page in migration.pages if page.path == source_path
            )
            self.assertTrue(migration.is_valid)
            self.assertFalse(source_plan.needs_change)

    def test_render_source_renames_author_to_attribution(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page('author: "John Smith"')

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        source_plan = next(
            page for page in migration.pages if page.path == source_path
        )
        rendered = migrate_v2.render_page(source_plan)

        self.assertIn('attribution: "John Smith"', rendered)
        self.assertNotIn('\nauthor: "John Smith"', rendered)

    def test_render_source_wraps_plain_raw_path_in_wikilink(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'attribution: "Research Team"',
            "source_file: raw/report.md",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        source_plan = next(
            page for page in migration.pages if page.path == source_path
        )

        self.assertTrue(migration.is_valid)
        self.assertTrue(source_plan.needs_change)
        rendered = migrate_v2.render_page(source_plan)
        self.assertIn('source_file: "[[raw/report.md]]"', rendered)
        self.assertNotIn("\nsource_file: raw/report.md\n", rendered)

    def test_build_plan_rejects_invalid_source_attribution(self) -> None:
        invalid_values = (
            ("", "attribution must not be empty"),
            ("null", "attribution must not be null"),
            ("[]", "attribution must be a scalar"),
        )

        for value, expected_error in invalid_values:
            with self.subTest(value=value):
                self.entities_dir.mkdir(exist_ok=True)
                source_path = self.write_source_page(f"attribution: {value}")

                migration = migrate_v2.build_migration_plan(self.entities_dir)
                source_plan = next(
                    page for page in migration.pages if page.path == source_path
                )

                self.assertFalse(migration.is_valid)
                self.assertFalse(source_plan.needs_change)
                self.assertTrue(
                    any(expected_error in error for error in source_plan.errors)
                )

    def test_render_source_prefers_existing_attribution(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'author: "Old Author"',
            'attribution: "Research Team"',
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        source_plan = next(
            page for page in migration.pages if page.path == source_path
        )
        rendered = migrate_v2.render_page(source_plan)

        self.assertTrue(migration.is_valid)
        self.assertEqual(source_plan.proposed_attribution, '"Research Team"')
        self.assertEqual(rendered.count("\nattribution:"), 1)
        self.assertIn('attribution: "Research Team"', rendered)
        self.assertNotIn('\nauthor: "Old Author"', rendered)
        self.assertNotIn('attribution: "Old Author"', rendered)

    def test_attribution_only_source_does_not_need_migration(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'attribution: "Garibaldi Capital Advisors"'
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        source_plan = next(
            page for page in migration.pages if page.path == source_path
        )

        self.assertTrue(migration.is_valid)
        self.assertFalse(source_plan.needs_change)
        self.assertEqual(source_plan.proposed_attribution, '"Garibaldi Capital Advisors"')
        self.assertEqual(migrate_v2.apply_migration(migration), ())

    def test_build_plan_rejects_invalid_legacy_author(self) -> None:
        invalid_values = (
            ("", "author must not be empty"),
            ("null", "author must not be null"),
            ("[]", "author must be a scalar"),
        )

        for value, expected_error in invalid_values:
            with self.subTest(value=value):
                self.entities_dir.mkdir(exist_ok=True)
                source_path = self.write_source_page(f"author: {value}")

                migration = migrate_v2.build_migration_plan(self.entities_dir)
                source_plan = next(
                    page for page in migration.pages if page.path == source_path
                )

                self.assertFalse(migration.is_valid)
                self.assertFalse(source_plan.needs_change)
                self.assertTrue(
                    any(expected_error in error for error in source_plan.errors)
                )

    def test_source_apply_preserves_metadata_body_crlf_and_is_idempotent(self) -> None:
        self.entities_dir.mkdir()
        source_path = self.write_source_page(
            'title: "Market Notes"',
            "slug: summary-market-notes",
            "source_file: raw/market-notes.md",
            'author: "Garibaldi Capital Advisors (Brendan Lochead, drafted with Claude)"',
            "date_published: 2026-07-18",
            "date_ingested: 2026-07-19",
            "confidence: high",
            body_lines=("# Market Notes", "", "Analysis with café text."),
            newline="\r\n",
        )

        first_plan = migrate_v2.build_migration_plan(self.entities_dir)
        first_changed = migrate_v2.apply_migration(first_plan)
        after_first_apply = source_path.read_bytes()
        second_plan = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertEqual(first_changed, (source_path,))
        self.assertIn(
            b'attribution: "Garibaldi Capital Advisors (Brendan Lochead, drafted with Claude)"\r\n',
            after_first_apply,
        )
        self.assertIn(b"date_published: 2026-07-18\r\n", after_first_apply)
        self.assertIn("Analysis with café text.".encode(), after_first_apply)
        self.assertNotIn(b"\n", after_first_apply.replace(b"\r\n", b""))
        self.assertEqual(migrate_v2.apply_migration(second_plan), ())
        self.assertEqual(source_path.read_bytes(), after_first_apply)

    def test_invalid_source_prevents_all_migration_writes(self) -> None:
        entity_path = self.write_entity_page('title: "Acme Corporation"')
        concept_path = self.write_concept_page('title: "Knowledge Graph"')
        source_path = self.write_source_page("attribution: []")
        originals = {
            path: path.read_bytes()
            for path in (entity_path, concept_path, source_path)
        }

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        with self.assertRaisesRegex(ValueError, "invalid migration"):
            migrate_v2.apply_migration(migration)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_build_plan_finds_entity_and_concept_pages(self) -> None:
        entity_path = self.write_entity_page('title: "Acme Corporation"')
        concept_path = self.write_concept_page('title: "Knowledge Graph"')

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertEqual(
            {page.path for page in migration.pages},
            {entity_path, concept_path},
        )

    def test_build_plan_prepares_legacy_concept_name_fields(self) -> None:
        self.entities_dir.mkdir()
        concept_path = self.write_concept_page('title: "Knowledge Graph"')

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        concept_plan = next(
            page for page in migration.pages if page.path == concept_path
        )

        self.assertTrue(migration.is_valid)
        self.assertEqual(concept_plan.existing_title, '"Knowledge Graph"')
        self.assertEqual(
            concept_plan.proposed_canonical_name,
            '"Knowledge Graph"',
        )
        self.assertEqual(concept_plan.missing_name_fields, migrate_v2.NAME_FIELDS)

    def test_render_page_migrates_legacy_concept_name_fields(self) -> None:
        self.entities_dir.mkdir()
        concept_path = self.write_concept_page('title: "Knowledge Graph"')

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        concept_plan = next(
            page for page in migration.pages if page.path == concept_path
        )
        rendered = migrate_v2.render_page(concept_plan)

        expected_name_block = "\n".join(
            [
                'canonical_name: "Knowledge Graph"',
                "aliases: []",
                "abbreviations: []",
                "known_variants: []",
                "known_errors: []",
            ]
        )
        self.assertIn(expected_name_block, rendered)
        self.assertNotIn('\ntitle: "Knowledge Graph"', rendered)

    def test_render_concept_preserves_aliases_metadata_and_body(self) -> None:
        self.entities_dir.mkdir()
        concept_path = self.write_concept_page(
            'title: "Knowledge Graph"',
            "aliases:",
            '  - "Semantic Network"',
            '  - "Knowledge Representation Graph"',
            "sources:",
            '  - "[[source-one]]"',
            "related:",
            '  - "[[linked-data]]"',
            "created: 2026-07-01",
            "updated: 2026-07-18",
            "confidence: high",
            body_lines=("# Knowledge Graph", "", "Concept body."),
        )
        original = concept_path.read_bytes()

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        concept_plan = next(
            page for page in migration.pages if page.path == concept_path
        )
        rendered = migrate_v2.render_page(concept_plan)

        self.assertIn(
            'aliases:\n  - "Semantic Network"\n'
            '  - "Knowledge Representation Graph"',
            rendered,
        )
        self.assertIn("abbreviations: []", rendered)
        self.assertIn("known_variants: []", rendered)
        self.assertIn("known_errors: []", rendered)
        self.assertIn('sources:\n  - "[[source-one]]"', rendered)
        self.assertIn('related:\n  - "[[linked-data]]"', rendered)
        self.assertIn("created: 2026-07-01", rendered)
        self.assertIn("updated: 2026-07-18", rendered)
        self.assertIn("confidence: high", rendered)
        self.assertTrue(rendered.endswith("# Knowledge Graph\n\nConcept body."))
        self.assertEqual(concept_path.read_bytes(), original)

    def test_render_concept_prefers_existing_canonical_name(self) -> None:
        self.entities_dir.mkdir()
        concept_path = self.write_concept_page(
            'title: "Old Knowledge Graph Name"',
            'canonical_name: "Knowledge Graph"',
            "aliases: []",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        concept_plan = next(
            page for page in migration.pages if page.path == concept_path
        )
        rendered = migrate_v2.render_page(concept_plan)

        self.assertEqual(
            concept_plan.proposed_canonical_name,
            '"Knowledge Graph"',
        )
        self.assertEqual(rendered.count("\ncanonical_name:"), 1)
        self.assertIn('canonical_name: "Knowledge Graph"', rendered)
        self.assertNotIn('\ntitle: "Old Knowledge Graph Name"', rendered)
        self.assertNotIn('canonical_name: "Old Knowledge Graph Name"', rendered)

    def test_build_plan_rejects_non_list_concept_name_field(self) -> None:
        self.entities_dir.mkdir()
        concept_path = self.write_concept_page(
            'canonical_name: "Knowledge Graph"',
            "aliases: not-a-list",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        concept_plan = next(
            page for page in migration.pages if page.path == concept_path
        )

        self.assertFalse(migration.is_valid)
        self.assertFalse(concept_plan.needs_change)
        self.assertTrue(
            any(
                "aliases must be a list" in error
                for error in concept_plan.errors
            )
        )

    def test_invalid_concept_prevents_entity_and_concept_writes(self) -> None:
        entity_path = self.write_entity_page('title: "Acme Corporation"')
        concept_path = self.write_concept_page(
            'canonical_name: "Knowledge Graph"',
            "aliases: not-a-list",
            "abbreviations: []",
            "known_variants: []",
            "known_errors: []",
        )
        originals = {
            entity_path: entity_path.read_bytes(),
            concept_path: concept_path.read_bytes(),
        }

        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        with self.assertRaisesRegex(ValueError, "invalid migration"):
            migrate_v2.apply_migration(migration)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_cli_preview_json_reports_entity_and_concept_pages(self) -> None:
        entity_path = self.write_entity_page('title: "Acme Corporation"')
        concept_path = self.write_concept_page('title: "Knowledge Graph"')
        originals = {
            entity_path: entity_path.read_bytes(),
            concept_path: concept_path.read_bytes(),
        }

        result = run_cli("--wiki-dir", str(self.wiki_dir), "--json")
        report = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(report["page_count"], 2)
        self.assertEqual(report["pending_count"], 2)
        self.assertEqual(report["changed_count"], 0)
        self.assertEqual(
            report["pending_paths"],
            [str(entity_path), str(concept_path)],
        )
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_cli_description_mentions_all_supported_page_types(self) -> None:
        parser = migrate_v2.build_arg_parser()

        self.assertIn("entit", parser.description.casefold())
        self.assertIn("concept", parser.description.casefold())
        self.assertIn("source", parser.description.casefold())

    def test_apply_migration_writes_entity_and_concept_pages(self) -> None:
        entity_path = self.write_entity_page('title: "Acme Corporation"')
        concept_path = self.write_concept_page('title: "Knowledge Graph"')

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        changed = migrate_v2.apply_migration(migration)

        self.assertEqual(changed, (entity_path, concept_path))
        for path, canonical_name in (
            (entity_path, "Acme Corporation"),
            (concept_path, "Knowledge Graph"),
        ):
            migrated = path.read_text(encoding="utf-8")
            self.assertIn(f'canonical_name: "{canonical_name}"', migrated)
            self.assertNotIn("\ntitle:", migrated)
            for field in migrate_v2.NAME_FIELDS:
                self.assertIn(f"{field}: []", migrated)

    def test_concept_apply_is_idempotent_and_preserves_crlf(self) -> None:
        self.entities_dir.mkdir()
        concept_path = self.write_concept_page(
            'title: "Knowledge Graph"',
            newline="\r\n",
        )

        first_plan = migrate_v2.build_migration_plan(self.entities_dir)
        first_changed = migrate_v2.apply_migration(first_plan)
        after_first_apply = concept_path.read_bytes()

        second_plan = migrate_v2.build_migration_plan(self.entities_dir)
        second_changed = migrate_v2.apply_migration(second_plan)

        self.assertEqual(first_changed, (concept_path,))
        self.assertIn(
            b'canonical_name: "Knowledge Graph"\r\n',
            after_first_apply,
        )
        self.assertNotIn(b"\n", after_first_apply.replace(b"\r\n", b""))
        self.assertEqual(second_changed, ())
        self.assertEqual(concept_path.read_bytes(), after_first_apply)

    def test_module_description_explains_all_migrations(self) -> None:
        module_docstring = migrate_v2.__doc__
        if module_docstring is None:
            self.fail("migrate_v2 must have a module docstring")
        description = module_docstring.casefold()

        self.assertIn("entit", description)
        self.assertIn("concept", description)
        self.assertIn("source", description)
        self.assertIn("author", description)
        self.assertIn("attribution", description)

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
                "canonical_name must be a scalar" in error for error in migration.errors
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
                "canonical_name must be a scalar" in error for error in migration.errors
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
            any("aliases must be a list" in error for error in migration.errors)
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
            any("aliases must be a list" in error for error in migration.errors)
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
            any("duplicate field: aliases" in error for error in migration.errors)
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
            any("duplicate field: aliases" in error for error in migration.errors)
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
            any("malformed frontmatter line" in error for error in migration.errors)
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

    def test_build_plan_ignores_markdown_files_outside_supported_directories(
        self,
    ) -> None:
        self.entities_dir.mkdir()
        unsupported_dir = self.wiki_dir / "notes"
        unsupported_dir.mkdir()
        comparison_path = unsupported_dir / "options.md"
        comparison_path.write_text(
            "\n".join(
                [
                    "---",
                    "type: comparison",
                    "comparison_id: comparison:options",
                    'title: "Comparing Options"',
                    "---",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        original = comparison_path.read_bytes()

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        changed = migrate_v2.apply_migration(migration)

        self.assertTrue(migration.is_valid)
        self.assertEqual(migration.pages, ())
        self.assertEqual(changed, ())
        self.assertEqual(comparison_path.read_bytes(), original)

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
        self.assertIn("entities directory does not exist", report["errors"][0])
        self.assertNotIn("Traceback", result.stdout)

    def test_comparison_migrates_legacy_provenance_and_defaults(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "comparison",
            'title: "Options"',
            "sources: []",
            "filed_from_query: true",
            "created: 2026-01-01",
            "updated: 2026-01-02",
            body_lines=("# Options", "", "Café body."),
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        rendered = migrate_v2.render_page(
            next(page for page in migration.pages if page.path == path)
        )

        self.assertTrue(migration.is_valid)
        for expected in (
            "origin: query",
            "status: active",
            "subjects: []",
            "related: []",
            'question: ""',
        ):
            self.assertIn(expected, rendered)
        self.assertNotIn("filed_from_query", rendered)
        self.assertTrue(rendered.endswith("# Options\n\nCafé body."))

    def test_work_page_preserves_existing_origin_and_status(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "comparison",
            'title: "Options"',
            "origin: ingest",
            "filed_from_query: true",
            "status: superseded",
            "subjects: []",
            "sources: []",
            "related: []",
            'question: "Why?"',
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        page = next(page for page in migration.pages if page.path == path)
        rendered = migrate_v2.render_page(page)

        self.assertTrue(migration.is_valid)
        self.assertIn("origin: ingest", rendered)
        self.assertIn("status: superseded", rendered)
        self.assertNotIn("filed_from_query", rendered)

    def test_work_page_rejects_invalid_enums_and_field_shapes(self) -> None:
        self.entities_dir.mkdir()
        self.write_work_page(
            "comparison",
            'title: "Options"',
            "origin: robot",
            "status: archived",
            "subjects: not-a-list",
            "sources: []",
            "related: []",
            "question: []",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        joined = "\n".join(migration.errors)
        self.assertIn("origin must be one of", joined)
        self.assertIn("status must be one of", joined)
        self.assertIn("subjects must be a list", joined)
        self.assertIn("question must be a scalar", joined)

    def test_synthesis_adds_conservative_defaults(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "synthesis",
            'title: "Market"',
            "sources: []",
            "filed_from_query: false",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        page = next(page for page in migration.pages if page.path == path)
        rendered = migrate_v2.render_page(page)

        self.assertTrue(migration.is_valid)
        for expected in (
            "origin: manual",
            "status: active",
            "subjects: []",
            "related: []",
            'question: ""',
            "confidence: low",
        ):
            self.assertIn(expected, rendered)

    def test_trace_migrates_concept_and_ingest_range(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "trace",
            'concept: "Machine Learning"',
            "sources: []",
            "filed_from_query: true",
            "created: 2026-01-01",
            "updated: 2026-01-02",
            "ingest_range: 2026-01-01 → 2026-02-03",
            newline="\r\n",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        changed = migrate_v2.apply_migration(migration)
        migrated = path.read_bytes()

        self.assertTrue(migration.is_valid)
        self.assertEqual(changed, (path,))
        self.assertIn(b'title: "Machine Learning"\r\n', migrated)
        self.assertIn(b'subjects:\r\n  - "[[Machine Learning]]"\r\n', migrated)
        self.assertIn(
            b"ingest_start: 2026-01-01\r\ningest_end: 2026-02-03\r\n",
            migrated,
        )
        self.assertNotIn(b"ingest_range:", migrated)
        self.assertNotIn(b"\n", migrated.replace(b"\r\n", b""))
        self.assertNotIn(b"concept:", migrated)

    def test_trace_repairs_nested_ingest_range(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "trace",
            'concept: "Legacy Concept"',
            'title: "Evidence Trail"',
            "subjects:",
            '  - "[[Canonical Concept]]"',
            "sources: []",
            "related: []",
            'question: "How?"',
            "origin: manual",
            "status: active",
            "confidence: medium",
            "ingest_range:",
            "  start: 2026-01-01",
            "  end: 2026-02-01",
            "created: 2026-01-01",
            "updated: 2026-02-01",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        page = next(page for page in migration.pages if page.path == path)
        rendered = migrate_v2.render_page(page)

        self.assertTrue(migration.is_valid)
        self.assertIn('title: "Evidence Trail"', rendered)
        self.assertIn('  - "[[Canonical Concept]]"', rendered)
        self.assertNotIn("Legacy Concept", rendered)
        self.assertIn("ingest_start: 2026-01-01", rendered)
        self.assertIn("ingest_end: 2026-02-01", rendered)
        self.assertNotIn("ingest_range:", rendered)

    def test_trace_current_ingest_fields_are_idempotent(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "trace",
            'title: "Evidence Trail"',
            "sources: []",
            "subjects: []",
            "related: []",
            'question: "How?"',
            "origin: manual",
            "status: active",
            "confidence: medium",
            "ingest_start: 2026-01-01",
            "ingest_end: 2026-02-01",
            "created: 2026-01-01",
            "updated: 2026-02-01",
        )

        migration = migrate_v2.build_migration_plan(self.entities_dir)
        page = next(page for page in migration.pages if page.path == path)

        self.assertTrue(migration.is_valid)
        self.assertFalse(page.needs_change)

    def test_trace_adds_only_missing_flat_ingest_field(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_work_page(
            "trace",
            'title: "Evidence Trail"',
            "sources: []",
            "ingest_start: 2026-01-01",
            "created: 2026-01-01",
            "updated: 2026-02-01",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        page = next(page for page in migration.pages if page.path == path)
        rendered = migrate_v2.render_page(page)

        self.assertTrue(migration.is_valid)
        self.assertEqual(rendered.count("ingest_start:"), 1)
        self.assertIn("ingest_start: 2026-01-01", rendered)
        self.assertIn('ingest_end: ""', rendered)

    def test_trace_rejects_legacy_and_flat_ingest_fields_together(self) -> None:
        self.entities_dir.mkdir()
        self.write_work_page(
            "trace",
            'title: "Evidence Trail"',
            "sources: []",
            "ingest_range: 2026-01-01 → 2026-02-01",
            "ingest_start: 2026-01-01",
            "created: 2026-01-01",
            "updated: 2026-02-01",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(any("must not coexist" in error for error in migration.errors))

    def test_trace_rejects_malformed_legacy_range(self) -> None:
        self.entities_dir.mkdir()
        self.write_work_page(
            "trace",
            'concept: "Machine Learning"',
            "sources: []",
            "ingest_range: 2026-01-01 - 2026-02-01",
            "created: 2026-01-01",
            "updated: 2026-02-01",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(any("ingest_range must be START" in e for e in migration.errors))

    def test_directory_artifacts_preview_apply_and_idempotence(self) -> None:
        self.entities_dir.mkdir()
        traces_keep = self.wiki_dir / "traces" / ".gitkeep"
        contradiction_keep = (
            self.wiki_dir / "tasks" / "contradiction-resolutions" / ".gitkeep"
        )
        traces_keep.unlink()
        traces_keep.parent.rmdir()
        contradiction_keep.unlink()
        contradiction_keep.parent.rmdir()
        contradiction_keep.parent.parent.rmdir()
        legacy = self.wiki_dir / "contradictions" / "legacy.md"
        legacy.parent.mkdir()
        legacy.write_text("legacy", encoding="utf-8")

        first = migrate_v2.build_migration_plan(self.entities_dir)
        self.assertEqual(first.create_paths, (traces_keep, contradiction_keep))
        self.assertFalse(traces_keep.exists())
        changed = migrate_v2.apply_migration(first)
        second = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertEqual(changed, (traces_keep, contradiction_keep))
        self.assertTrue(traces_keep.is_file())
        self.assertTrue(contradiction_keep.is_file())
        self.assertEqual(second.create_paths, ())
        self.assertEqual(migrate_v2.apply_migration(second), ())
        self.assertEqual(legacy.read_text(encoding="utf-8"), "legacy")

    def test_contradiction_adds_stable_id(self) -> None:
        self.entities_dir.mkdir()
        path = self.write_contradiction_page(
            'title: "Resolve pricing"',
            "status: open",
            "priority: high",
            "subjects: []",
            "claims: []",
            'resolution_question: "Which is correct?"',
            "evidence: []",
            "log_references: []",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)
        page = next(page for page in migration.pages if page.path == path)
        rendered = migrate_v2.render_page(page)

        self.assertTrue(migration.is_valid)
        self.assertIn(
            "contradiction_resolution_id: contradiction-resolution:pricing-conflict",
            rendered,
        )

    def test_contradiction_conditional_fields_and_atomicity(self) -> None:
        self.entities_dir.mkdir()
        entity_path = self.write_entity_page('title: "Acme Corporation"')
        original = entity_path.read_bytes()
        traces_keep = self.wiki_dir / "traces" / ".gitkeep"
        traces_keep.unlink()
        traces_keep.parent.rmdir()
        self.write_contradiction_page(
            'title: "Resolve pricing"',
            "status: resolved",
            "priority: medium",
            "subjects: []",
            "claims: []",
            'resolution_question: "Which is correct?"',
            "evidence: []",
            "log_references: []",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(any("resolution is required" in e for e in migration.errors))
        with self.assertRaisesRegex(ValueError, "invalid migration"):
            migrate_v2.apply_migration(migration)
        self.assertEqual(entity_path.read_bytes(), original)
        self.assertFalse(traces_keep.exists())

    def test_contradiction_duplicate_effective_ids_are_rejected(self) -> None:
        self.entities_dir.mkdir()
        common = (
            'title: "Resolve pricing"',
            "status: open",
            "priority: medium",
            "subjects: []",
            "claims: []",
            'resolution_question: "Which is correct?"',
            "evidence: []",
            "log_references: []",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        self.write_contradiction_page(
            "contradiction_resolution_id: contradiction-resolution:same", *common
        )
        self.write_contradiction_page(
            "contradiction_resolution_id: contradiction-resolution:same",
            *common,
            filename="other.md",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(any("duplicate ID" in error for error in migration.errors))

    def test_contradiction_rejects_mapping_claim_and_missing_dismissal(self) -> None:
        self.entities_dir.mkdir()
        self.write_contradiction_page(
            'title: "Resolve pricing"',
            "status: dismissed",
            "priority: low",
            "subjects: []",
            "claims:",
            "  - text: Unsupported mapping",
            'resolution_question: "Which is correct?"',
            "evidence: []",
            "log_references: []",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        joined = "\n".join(migration.errors)
        self.assertIn("claims must contain non-empty scalar values", joined)
        self.assertIn("dismissal_reason is required", joined)

    def test_contradiction_rejects_empty_required_block_scalar(self) -> None:
        self.entities_dir.mkdir()
        self.write_contradiction_page(
            'title: "Resolve pricing"',
            "status: open",
            "priority: low",
            "subjects: []",
            "claims: []",
            "resolution_question: >-",
            "evidence: []",
            "log_references: []",
            "created: 2026-01-01",
            "updated: 2026-01-02",
        )
        migration = migrate_v2.build_migration_plan(self.entities_dir)

        self.assertFalse(migration.is_valid)
        self.assertTrue(
            any("resolution_question must not be empty" in e for e in migration.errors)
        )

    def test_cli_reports_directory_creation_actions(self) -> None:
        self.entities_dir.mkdir()
        traces_keep = self.wiki_dir / "traces" / ".gitkeep"
        contradiction_keep = (
            self.wiki_dir / "tasks" / "contradiction-resolutions" / ".gitkeep"
        )
        traces_keep.unlink()
        traces_keep.parent.rmdir()
        contradiction_keep.unlink()
        contradiction_keep.parent.rmdir()
        contradiction_keep.parent.parent.rmdir()

        preview = run_cli("--wiki-dir", str(self.wiki_dir))
        applied = run_cli("--wiki-dir", str(self.wiki_dir), "--apply", "--json")
        report = json.loads(applied.stdout)

        self.assertEqual(preview.returncode, 0)
        self.assertIn(f"would create: {traces_keep}", preview.stdout)
        self.assertIn(f"would create: {contradiction_keep}", preview.stdout)
        self.assertEqual(applied.returncode, 0)
        self.assertEqual(report["changed_count"], 2)
        self.assertEqual(
            report["changed_paths"], [str(traces_keep), str(contradiction_keep)]
        )
