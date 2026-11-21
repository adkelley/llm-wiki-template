from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ontology.py"
SPEC = importlib.util.spec_from_file_location("ontology", SCRIPT_PATH)
assert SPEC is not None, "Failed to load ontology module"
assert SPEC.loader is not None, "Failed to load ontology module"

ontology = importlib.util.module_from_spec(SPEC)
sys.modules["ontology"] = ontology
SPEC.loader.exec_module(ontology)


PAGE_CASES = (
    ("sources", "source", "source_id", "source:example-source"),
    ("concepts", "concept", "concept_id", "concept:example-concept"),
    ("entities", "entity", "entity_id", "entity:example-entity"),
    (
        "comparisons",
        "comparison",
        "comparison_id",
        "comparison:example-comparison",
    ),
    (
        "syntheses",
        "synthesis",
        "synthesis_id",
        "synthesis:example-synthesis",
    ),
    ("traces", "trace", "trace_id", "trace:example-trace"),
)


class OntologyCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.wiki_dir = Path(self.temporary_directory.name) / "wiki"
        self.wiki_dir.mkdir()

        for directory in ontology.PAGE_DIRECTORIES:
            (self.wiki_dir / directory).mkdir()

    def write_page(
        self,
        directory: str,
        filename: str,
        page_type: str,
        id_field: str,
        stable_id: str,
        *,
        title: str = "Example Page",
        nested_directory: str | None = None,
        include_id: bool = True,
    ) -> Path:
        parent = self.wiki_dir / directory
        if nested_directory is not None:
            parent /= nested_directory
        parent.mkdir(parents=True, exist_ok=True)

        lines = ["---", f"type: {page_type}"]
        if include_id:
            lines.append(f"{id_field}: {stable_id}")
        lines.extend([f"title: {title}", "---", "", "Body text.", ""])

        path = parent / filename
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_valid_page_is_discovered_and_indexed_by_id(self) -> None:
        path = self.write_page(
            "concepts",
            "knowledge-graph.md",
            "concept",
            "concept_id",
            "concept:knowledge-graph",
            title="Knowledge Graph",
        )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertTrue(catalog.is_valid)
        self.assertEqual(len(catalog.pages), 1)
        self.assertEqual(catalog.pages[0].path, path)
        self.assertEqual(catalog.pages[0].title, "Knowledge Graph")
        self.assertIs(catalog.pages_by_id["concept:knowledge-graph"], catalog.pages[0])

    def test_discovers_all_supported_page_types(self) -> None:
        for directory, page_type, id_field, stable_id in PAGE_CASES:
            self.write_page(
                directory,
                f"example-{page_type}.md",
                page_type,
                id_field,
                stable_id,
            )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertTrue(catalog.is_valid)
        self.assertEqual(len(catalog.pages), len(PAGE_CASES))
        self.assertEqual(
            {page.page_type for page in catalog.pages},
            {case[1] for case in PAGE_CASES},
        )

    def test_discovers_nested_markdown_pages_recursively(self) -> None:
        path = self.write_page(
            "traces",
            "adoption.md",
            "trace",
            "trace_id",
            "trace:adoption",
            nested_directory="archive/2026",
        )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertTrue(catalog.is_valid)
        self.assertEqual(tuple(page.path for page in catalog.pages), (path,))

    def test_ignores_markdown_files_outside_supported_directories(self) -> None:
        (self.wiki_dir / "index.md").write_text("# Wiki Index\n", encoding="utf-8")

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertTrue(catalog.is_valid)
        self.assertEqual(catalog.pages, ())

    def test_missing_stable_id_makes_catalog_invalid(self) -> None:
        self.write_page(
            "concepts",
            "missing-id.md",
            "concept",
            "concept_id",
            "concept:missing-id",
            include_id=False,
        )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertFalse(catalog.is_valid)
        self.assertTrue(any("concept_id" in error for error in catalog.errors))

    def test_directory_and_frontmatter_type_mismatch_is_invalid(self) -> None:
        self.write_page(
            "concepts",
            "wrong-type.md",
            "entity",
            "concept_id",
            "concept:wrong-type",
        )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertFalse(catalog.is_valid)
        self.assertTrue(any("expected type" in error for error in catalog.errors))

    def test_malformed_stable_id_is_invalid(self) -> None:
        self.write_page(
            "concepts",
            "bad-id.md",
            "concept",
            "concept_id",
            "source:not-a-concept",
        )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertFalse(catalog.is_valid)
        self.assertTrue(any("expected id" in error for error in catalog.errors))

    def test_duplicate_stable_ids_are_invalid_and_not_indexed(self) -> None:
        stable_id = "concept:duplicate"
        self.write_page(
            "concepts",
            "first.md",
            "concept",
            "concept_id",
            stable_id,
        )
        self.write_page(
            "concepts",
            "second.md",
            "concept",
            "concept_id",
            stable_id,
            nested_directory="archive",
        )

        catalog = ontology.build_catalog(self.wiki_dir)

        self.assertFalse(catalog.is_valid)
        self.assertTrue(any("duplicate ID" in error for error in catalog.errors))
        self.assertNotIn(stable_id, catalog.pages_by_id)

    def test_missing_wiki_directory_returns_invalid_catalog(self) -> None:
        missing_wiki = self.wiki_dir / "missing"

        catalog = ontology.build_catalog(missing_wiki)

        self.assertFalse(catalog.is_valid)
        self.assertEqual(catalog.pages, ())
        self.assertEqual(catalog.pages_by_id, {})
        self.assertTrue(
            any("wiki directory does not exist" in error for error in catalog.errors)
        )


if __name__ == "__main__":
    unittest.main()
