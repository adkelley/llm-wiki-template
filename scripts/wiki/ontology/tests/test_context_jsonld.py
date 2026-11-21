from __future__ import annotations

import json
import unittest
from pathlib import Path

CONTEXT_PATH = Path(__file__).resolve().parents[1] / "context.example.jsonld"
PLACEHOLDER_NAMESPACE = "https://example.org/llm-wiki/"

STABLE_ID_PREFIXES = {
    "source",
    "concept",
    "entity",
    "comparison",
    "synthesis",
    "trace",
}

PAGE_ID_FIELDS = {
    "source_id",
    "concept_id",
    "entity_id",
    "comparison_id",
    "synthesis_id",
    "trace_id",
}

SEMANTIC_RELATIONSHIPS = {
    "related",
    "derived_from",
    "about",
    "mentions",
    "implements",
    "depends_on",
    "part_of",
}

COMPANION_FIELDS = {f"{relationship}_links" for relationship in SEMANTIC_RELATIONSHIPS}


class ContextJsonLdTests(unittest.TestCase):
    def setUp(self) -> None:
        text = CONTEXT_PATH.read_text(encoding="utf-8")
        self.document = json.loads(text)
        self.context = self.document["@context"]

    def test_file_is_valid_json_object(self) -> None:
        self.assertIsInstance(self.document, dict)
        self.assertIsInstance(self.context, dict)

    def test_uses_jsonld_1_1(self) -> None:
        self.assertEqual(self.context["@version"], 1.1)

    def test_stable_id_prefixes_are_prefix_definitions(self) -> None:
        for prefix in STABLE_ID_PREFIXES:
            with self.subTest(prefix=prefix):
                definition = self.context[prefix]
                self.assertIs(definition["@prefix"], True)

    def test_page_id_fields_alias_json_ld_id(self) -> None:
        for field in PAGE_ID_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(self.context[field], "@id")

    def test_relationships_are_sets_of_iri_references(self) -> None:
        for relationship in SEMANTIC_RELATIONSHIPS:
            with self.subTest(relationship=relationship):
                definition = self.context[relationship]
                self.assertEqual(definition["@type"], "@id")
                self.assertEqual(definition["@container"], "@set")

    def test_companion_fields_are_excluded_from_json_ld(self) -> None:
        actual_companion_fields = {
            field for field in self.context if field.endswith("_links")
        }

        self.assertEqual(actual_companion_fields, COMPANION_FIELDS)

        for field in COMPANION_FIELDS:
            with self.subTest(field=field):
                self.assertIsNone(self.context[field])

    def test_placeholder_namespace_is_used_consistently(self) -> None:
        self.assertEqual(
            self.context["wiki"]["@id"],
            PLACEHOLDER_NAMESPACE,
        )

        for prefix in STABLE_ID_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    self.context[prefix]["@id"],
                    f"{PLACEHOLDER_NAMESPACE}{prefix}/",
                )


if __name__ == "__main__":
    unittest.main()
