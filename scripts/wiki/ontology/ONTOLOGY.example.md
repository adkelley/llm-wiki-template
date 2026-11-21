# Wiki Ontology Profile

This vault uses the optional LLM Wiki ontology profile.

The Markdown wiki is the primary knowledge representation. RDF and OWL files
are generated artifacts and must not be edited as the source of truth.

## Semantic Context

The shared JSON-LD context is:

```text
context.jsonld
```

The context maps compact identifiers and frontmatter fields to absolute IRIs.

The placeholder namespace in a newly installed vault is:

```text
https://example.org/llm-wiki/
```

Replace it with a permanent namespace before publishing or exchanging RDF.
Once published, do not change the namespace without an explicit IRI migration.

## Stable Page Identity

Every supported wiki page must have its existing type-specific stable ID:

```yaml
type: source
source_id: source:annual-report
```

```yaml
type: concept
concept_id: concept:knowledge-graph
```

```yaml
type: entity
entity_id: entity:acme
```

Supported ID prefixes are:

- `source:`
- `concept:`
- `entity:`
- `comparison:`
- `synthesis:`
- `trace:`

Stable IDs are permanent. Do not change an ID when a page title, filename, or
folder changes.

## Semantic Relationships

Relationship targets must use stable compact IRIs:

```yaml
related:
  - concept:knowledge-graph
  - entity:acme
derived_from:
  - source:annual-report
```

Every relationship field must be a YAML list, including when it has only one
target.

Approved predicates are:

- `related` — a general association.
- `derived_from` — knowledge derived from a source page.
- `about` — the primary subject of a page.
- `mentions` — a subject discussed by a page.
- `implements` — something implemented by the originating page.
- `depends_on` — something required by the originating page.
- `part_of` — a larger thing containing the originating page’s subject.

Store only the relationship direction asserted by the page. Do not add reverse
relationships automatically.

Do not use `supports` or `contradicts` until the vault defines stable identities
for claims.

## Relationship Constraints

Every relationship target must:

- Match a supported stable-ID format.
- Resolve to exactly one existing wiki page.
- Refer to a page whose declared stable ID matches the target.
- Appear no more than once within the same predicate.
- Not refer to the originating page itself.

Additional constraints:

- `derived_from` must target `source:*`.
- `about` must initially target `concept:*`.

Missing, ambiguous, malformed, and incorrectly typed relationships are errors.

## Obsidian Navigation

Semantic relationship fields are authoritative:

```yaml
related:
  - concept:knowledge-graph
```

Obsidian navigation is stored in generated companion fields:

```yaml
related_links:
  - "[[wiki/concepts/knowledge-graph|Knowledge Graph]]"
```

Fields ending in `_links` are generated views.

Do not edit them manually. Regenerate them from stable IDs after pages are
renamed or moved.

The JSON-LD context excludes these presentation fields from generated RDF.

## Page Examples

### Concept page

```yaml
---
type: concept
concept_id: concept:knowledge-graph
title: "Knowledge Graph"
aliases:
  - semantic graph
derived_from:
  - source:graph-report
related:
  - concept:ontology
mentions:
  - entity:acme
related_links:
  - "[[wiki/concepts/ontology|Ontology]]"
derived_from_links:
  - "[[wiki/sources/graph-report|Graph Report]]"
mentions_links:
  - "[[wiki/entities/acme|Acme]]"
created: 2026-07-13
updated: 2026-07-13
confidence: high
---
```

### Source page

```yaml
---
type: source
source_id: source:graph-report
title: "Graph Report"
source_file: raw/graph-report.pdf
about:
  - concept:knowledge-graph
about_links:
  - "[[wiki/concepts/knowledge-graph|Knowledge Graph]]"
date_ingested: 2026-07-13
confidence: high
---
```

## Agent Workflow

When creating or updating a wiki page:

1. Preserve its stable ID.
2. Use only approved semantic predicates.
3. Use stable compact IRIs as relationship targets.
4. Verify every target exists.
5. Update semantic relationships before regenerating companion links.
6. Never infer a narrow predicate when the source only supports a general
   relationship.
7. Record provenance using `derived_from` whenever a source page supports the
   knowledge.
8. Run ontology validation before committing changes.

## Synchronize Obsidian Links

Preview generated companion-link changes:

```bash
python3 scripts/wiki/ontology/sync_links.py --wiki-dir wiki
```

Apply them:

```bash
python3 scripts/wiki/ontology/sync_links.py --wiki-dir wiki --apply
```

A fully synchronized wiki should report: `pending=0`

## Validation

Validate the ontology profile:

```bash
python3 scripts/wiki/ontology/validate.py --wiki-dir wiki
```

Validation is read-only. A valid wiki reports `valid=True`.
Validation failures block ontology generation.

## RDF Generation

RDF and OWL outputs are generated from:

- Wiki page frontmatter.
- Stable IDs.
- Semantic relationships.
- `context.jsonld`.

Generated files are disposable. Regenerate them rather than editing them
directly.

The generator must not infer unsupported facts merely to produce a more
connected graph.

## Ontology Evolution

As the wiki grows, repeated patterns may suggest:

- New predicates.
- More precise relationship types.
- Candidate ontology classes.
- Subclass relationships.
- Property domains and ranges.
- Constraints and consistency rules.

Treat these as proposals first. Changes to `context.jsonld` affect the semantic
meaning of the entire vault and require explicit review.

The ontology becomes stronger through accumulated evidence, greater precision,
and validated structure—not through silent schema changes.

## Non-Goals

This profile does not currently provide:

- RDF-to-Markdown roundtripping.
- Exact preservation of imported Turtle syntax.
- Automatic approval of ontology schema changes.
- Native Notion relations.
- Stable identities for individual claims.
