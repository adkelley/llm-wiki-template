from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "frontmatter_check.py"
SPEC = importlib.util.spec_from_file_location("frontmatter_check", SCRIPT_PATH)
assert SPEC is not None, "Failed to load frontmatter_check module"
assert SPEC.loader is not None, "Failed to load frontmatter_check module"

frontmatter_check = importlib.util.module_from_spec(SPEC)
sys.modules["frontmatter_check"] = frontmatter_check
SPEC.loader.exec_module(frontmatter_check)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


VALID_PAGES = {
    "source": """
        type: source
        source_id: source:annual-report
        title: Annual Report
        source_file: "[[raw/annual-report.md]]"
        renditions: []
        source_type: report
        attribution: Example Corporation
        key_claims: []
        related: []
        confidence: high
    """,
    "concept": """
        type: concept
        concept_id: concept:knowledge-graph
        canonical_name: Knowledge Graph
        aliases: []
        abbreviations: []
        known_variants: []
        known_errors: []
        sources: []
        related: []
        confidence: high
    """,
    "entity": """
        type: entity
        entity_id: entity:acme
        entity_type: company
        canonical_name: Acme
        aliases: []
        abbreviations: []
        known_variants: []
        known_errors: []
        sources: []
        related: []
    """,
    "comparison": """
        type: comparison
        comparison_id: comparison:acme-vs-globex
        title: Acme vs Globex
        status: active
        subjects: []
        sources: []
        related: []
        question: How do they compare?
        origin: query
    """,
    "synthesis": """
        type: synthesis
        synthesis_id: synthesis:market-overview
        title: Market Overview
        question: What do we know?
        origin: ingest
        status: active
        subjects: []
        sources: []
        related: []
        confidence: medium
    """,
    "trace": """
        type: trace
        trace_id: trace:adoption
        title: Adoption Trace
        question: How did adoption develop?
        origin: query
        status: active
        subjects: []
        sources: []
        related: []
        ingest_start: 2026-01-01
        ingest_end: 2026-02-01
        confidence: high
    """,
    "contradiction-resolution": """
        type: contradiction-resolution
        contradiction_resolution_id: contradiction-resolution:pricing
        title: Resolve pricing conflict
        status: open
        priority: medium
        subjects: []
        claims:
          - "The price is $10 -- [[pricing-report]]"
        resolution_question: Which price is current?
        evidence: []
        log_references: []
    """,
}


class FrontmatterCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "wiki"
        self.root.mkdir()

    def write_page(
        self,
        frontmatter: str,
        *,
        relative_path: str = "example.md",
        close_frontmatter: bool = True,
    ) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        closing = "---\n" if close_frontmatter else ""
        path.write_text(
            f"---\n{textwrap.dedent(frontmatter).strip()}\n{closing}\nBody.\n",
            encoding="utf-8",
        )
        return path

    def check(self, frontmatter: str) -> tuple[list[str], list[str]]:
        return frontmatter_check.check_file(self.write_page(frontmatter))

    def test_accepts_valid_page_for_every_documented_type(self) -> None:
        for page_type, frontmatter in VALID_PAGES.items():
            with self.subTest(page_type=page_type):
                path = self.write_page(
                    frontmatter,
                    relative_path=f"{page_type}/example.md",
                )
                self.assertEqual(frontmatter_check.check_file(path), ([], []))

    def test_trace_requires_both_flat_ingestion_boundaries(self) -> None:
        for missing_field in ("ingest_start", "ingest_end"):
            with self.subTest(missing_field=missing_field):
                frontmatter = "\n".join(
                    line
                    for line in textwrap.dedent(VALID_PAGES["trace"]).splitlines()
                    if not line.strip().startswith(f"{missing_field}:")
                )
                issues, _ = self.check(frontmatter)
                self.assertTrue(
                    any(
                        f"missing required field '{missing_field}'" in issue
                        for issue in issues
                    )
                )

    def test_trace_rejects_empty_or_collection_ingestion_boundaries(self) -> None:
        cases = {
            "empty": '""',
            "null": "null",
            "list": "[2026-01-01]",
            "mapping": "{start: 2026-01-01}",
        }
        for field, original in (
            ("ingest_start", "2026-01-01"),
            ("ingest_end", "2026-02-01"),
        ):
            for name, value in cases.items():
                with self.subTest(field=field, name=name):
                    frontmatter = textwrap.dedent(VALID_PAGES["trace"]).replace(
                        f"{field}: {original}", f"{field}: {value}"
                    )
                    issues, _ = self.check(frontmatter)
                    self.assertTrue(any(field in issue for issue in issues))

    def test_trace_rejects_scalar_and_nested_legacy_range(self) -> None:
        legacy_values = (
            '"2026-01-01 → 2026-02-01"',
            "{start: 2026-01-01, end: 2026-02-01}",
        )
        for value in legacy_values:
            with self.subTest(value=value):
                frontmatter = (
                    textwrap.dedent(VALID_PAGES["trace"]).strip()
                    + f"\ningest_range: {value}"
                )
                issues, _ = self.check(frontmatter)
                self.assertTrue(
                    any("obsolete field 'ingest_range'" in issue for issue in issues)
                )

    def test_reports_representative_page_schema_failures(self) -> None:
        cases = {
            "id": (
                "concept_id: concept:knowledge-graph",
                "concept_id: source:wrong",
                "concept_id",
            ),
            "enum": ("source_type: report", "source_type: pdf", "source_type"),
            "wikilink-list": ("related: []", "related: not-a-list", "related"),
            "canonical-name": (
                "canonical_name: Knowledge Graph",
                "title: Knowledge Graph",
                "canonical_name",
            ),
            "source-file": (
                'source_file: "[[raw/annual-report.md]]"',
                "source_file: raw/report.md",
                "source_file",
            ),
        }
        page_for_case = {
            "id": "concept",
            "enum": "source",
            "wikilink-list": "source",
            "canonical-name": "concept",
            "source-file": "source",
        }
        for name, (old, new, expected) in cases.items():
            with self.subTest(name=name):
                frontmatter = textwrap.dedent(
                    VALID_PAGES[page_for_case[name]]
                ).replace(old, new)
                issues, _ = self.check(frontmatter)
                self.assertTrue(any(expected in issue for issue in issues), issues)

    def test_contradiction_resolution_requires_conditional_fields(self) -> None:
        for status, field in (
            ("resolved", "resolution"),
            ("dismissed", "dismissal_reason"),
        ):
            with self.subTest(status=status):
                frontmatter = textwrap.dedent(
                    VALID_PAGES["contradiction-resolution"]
                ).replace("status: open", f"status: {status}")
                issues, _ = self.check(frontmatter)
                self.assertTrue(any(field in issue for issue in issues))

    def test_reports_mapping_embedded_in_any_list(self) -> None:
        frontmatter = textwrap.dedent(VALID_PAGES["source"]).replace(
            "key_claims: []", "key_claims:\n  - label: corrupted text"
        )
        issues, _ = self.check(frontmatter)
        self.assertTrue(any("list contains a mapping" in issue for issue in issues))

    def test_reports_yaml_and_frontmatter_structure_errors(self) -> None:
        malformed_yaml = self.write_page("type: [source")
        missing_delimiter = self.write_page(
            VALID_PAGES["source"],
            relative_path="missing-delimiter.md",
            close_frontmatter=False,
        )

        yaml_issues, _ = frontmatter_check.check_file(malformed_yaml)
        delimiter_issues, _ = frontmatter_check.check_file(missing_delimiter)

        self.assertTrue(any("YAML parse error" in issue for issue in yaml_issues))
        self.assertTrue(
            any(
                "no closing frontmatter delimiter" in issue
                for issue in delimiter_issues
            )
        )

    def test_claim_without_wikilink_is_warning_not_issue(self) -> None:
        frontmatter = textwrap.dedent(VALID_PAGES["contradiction-resolution"]).replace(
            '"The price is $10 -- [[pricing-report]]"', '"The price is $10"'
        )
        issues, warnings = self.check(frontmatter)

        self.assertEqual(issues, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("has no [[wikilink]]", warnings[0])

    def test_cli_recursively_scans_valid_pages(self) -> None:
        self.write_page(VALID_PAGES["trace"], relative_path="traces/nested/example.md")

        result = run_cli(str(self.root))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK -- no frontmatter schema issues found.", result.stdout)

    def test_cli_reports_issues_and_returns_nonzero(self) -> None:
        invalid = textwrap.dedent(VALID_PAGES["trace"]).replace(
            "ingest_end: 2026-02-01",
            "ingest_range: {start: 2026-01-01, end: 2026-02-01}",
        )
        self.write_page(invalid, relative_path="traces/example.md")

        result = run_cli(str(self.root))

        self.assertEqual(result.returncode, 1)
        self.assertIn("issue(s) found", result.stdout)
        self.assertIn("obsolete field 'ingest_range'", result.stdout)


if __name__ == "__main__":
    unittest.main()
