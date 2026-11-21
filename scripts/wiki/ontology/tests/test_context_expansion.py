from __future__ import annotations

import json
import unittest
from pathlib import Path

from pyld import jsonld

CONTEXT_PATH = Path(__file__).resolve().parents[1] / "context.example.jsonld"

WIKI_NAMESPACE = "https://example.org/llm-wiki/"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
PROV_WAS_DERIVED_FROM = "http://www.w3.org/ns/prov#wasDerivedFrom"
PAGE_TYPE = f"{WIKI_NAMESPACE}pageType"
RELATED = f"{WIKI_NAMESPACE}related"
SDO_NAMESPACE = "https://schema.org/"
PROV_NAMESPACE = "http://www.w3.org/ns/prov#"


class ContextExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        context_document = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
        self.context = context_document["@context"]

        document = {
            "@context": context_document["@context"],
            "concept_id": "concept:knowledge-graph",
            "type": "concept",
            "title": "Knowledge Graph",
            "related": [
                "concept:ontology",
                "entity:acme",
            ],
            "derived_from": [
                "source:graph-report",
            ],
            "related_links": [
                "[[wiki/concepts/ontology|Ontology]]",
            ],
        }

        expanded = jsonld.expand(document)

        self.assertEqual(len(expanded), 1)
        self.node = expanded[0]

    def iri_values(self, predicate: str) -> set[str]:
        return {value["@id"] for value in self.node[predicate]}

    def literal_values(self, predicate: str) -> list[str]:
        return [value["@value"] for value in self.node[predicate]]

    def test_expands_every_page_id_to_absolute_iri(self) -> None:
        cases = (
            (
                "source_id",
                "source:annual-report",
                f"{WIKI_NAMESPACE}source/annual-report",
            ),
            (
                "concept_id",
                "concept:knowledge-graph",
                f"{WIKI_NAMESPACE}concept/knowledge-graph",
            ),
            (
                "entity_id",
                "entity:acme",
                f"{WIKI_NAMESPACE}entity/acme",
            ),
            (
                "comparison_id",
                "comparison:graph-vs-vector",
                f"{WIKI_NAMESPACE}comparison/graph-vs-vector",
            ),
            (
                "synthesis_id",
                "synthesis:market-overview",
                f"{WIKI_NAMESPACE}synthesis/market-overview",
            ),
            (
                "trace_id",
                "trace:knowledge-graph-adoption",
                f"{WIKI_NAMESPACE}trace/knowledge-graph-adoption",
            ),
        )

        for field, compact_iri, expected_iri in cases:
            with self.subTest(field=field):
                document = {
                    "@context": self.context,
                    field: compact_iri,
                    "title": "Example Page",
                }

                expanded = jsonld.expand(document)

                self.assertEqual(len(expanded), 1)
                self.assertEqual(expanded[0]["@id"], expected_iri)

    def test_expands_title_to_rdfs_label(self) -> None:
        self.assertEqual(
            self.literal_values(RDFS_LABEL),
            ["Knowledge Graph"],
        )

    def test_expands_page_type_as_vault_metadata(self) -> None:
        self.assertEqual(
            self.literal_values(PAGE_TYPE),
            ["concept"],
        )

    def test_expands_related_targets_to_absolute_iris(self) -> None:
        self.assertEqual(
            self.iri_values(RELATED),
            {
                f"{WIKI_NAMESPACE}concept/ontology",
                f"{WIKI_NAMESPACE}entity/acme",
            },
        )

    def test_expands_provenance_to_prov_o(self) -> None:
        self.assertEqual(
            self.iri_values(PROV_WAS_DERIVED_FROM),
            {
                f"{WIKI_NAMESPACE}source/graph-report",
            },
        )

    def test_excludes_obsidian_companion_fields(self) -> None:
        expected_keys = {
            "@id",
            RDFS_LABEL,
            PROV_WAS_DERIVED_FROM,
            PAGE_TYPE,
            RELATED,
        }

        self.assertEqual(set(self.node), expected_keys)

    def test_expands_every_semantic_relationship(self) -> None:
        cases = (
            (
                "related",
                "concept:ontology",
                f"{WIKI_NAMESPACE}related",
                f"{WIKI_NAMESPACE}concept/ontology",
            ),
            (
                "derived_from",
                "source:graph-report",
                f"{PROV_NAMESPACE}wasDerivedFrom",
                f"{WIKI_NAMESPACE}source/graph-report",
            ),
            (
                "about",
                "concept:knowledge-graph",
                f"{SDO_NAMESPACE}about",
                f"{WIKI_NAMESPACE}concept/knowledge-graph",
            ),
            (
                "mentions",
                "entity:acme",
                f"{SDO_NAMESPACE}mentions",
                f"{WIKI_NAMESPACE}entity/acme",
            ),
            (
                "implements",
                "concept:ontology",
                f"{WIKI_NAMESPACE}implements",
                f"{WIKI_NAMESPACE}concept/ontology",
            ),
            (
                "depends_on",
                "concept:knowledge-graph",
                f"{WIKI_NAMESPACE}dependsOn",
                f"{WIKI_NAMESPACE}concept/knowledge-graph",
            ),
            (
                "part_of",
                "concept:knowledge-representation",
                f"{SDO_NAMESPACE}isPartOf",
                f"{WIKI_NAMESPACE}concept/knowledge-representation",
            ),
        )

        for field, target, predicate_iri, target_iri in cases:
            with self.subTest(field=field):
                document = {
                    "@context": self.context,
                    "concept_id": "concept:test-page",
                    "title": "Test Page",
                    field: [target],
                }

                expanded = jsonld.expand(document)

                self.assertEqual(len(expanded), 1)
                self.assertEqual(
                    {value["@id"] for value in expanded[0][predicate_iri]},
                    {target_iri},
                )


if __name__ == "__main__":
    unittest.main()
