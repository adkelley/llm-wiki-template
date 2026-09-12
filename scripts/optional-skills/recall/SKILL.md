---
name: recall
description: Query the maintained wiki for pages related to a topic using a configured qmd collection. Use when the user runs `/recall` with a topic or asks to recall, reload, or query existing wiki knowledge.
---

# Recall wiki knowledge

Use qmd to retrieve relevant maintained wiki pages before answering.

## Read the configuration

Locate `config.md` in the same skill directory as this `SKILL.md`. Read exactly one nonempty setting in this form:

```text
qmd_collection: collection-name
```

If `config.md` is missing, the setting is empty or malformed, or more than one `qmd_collection` setting exists, explain that recall is not configured and tell the user to rerun the appropriate Codex or Claude `setup.sh`. Stop without running qmd. Never fall back to querying all collections.

## Query the configured collection

Use BM25 search by default:

```bash
# Keyword search — fastest (~0.2s), best default for named-entity/proper-noun
# queries; can miss when the query's wording doesn't overlap the source text
qmd search "$topic" --collection "$qmd_collection" --json
```

Use a different mode only when it better fits the request:

```bash
# Hybrid retrieval without reranking — ~1s; use when BM25 comes up empty or
# the question is more conceptual/paraphrased than keyword-matchable
qmd query "$topic" --collection "$qmd_collection" --no-rerank --json

# Vector-only semantic search — timing is inconsistent (~1-17s) and it has
# returned a wrong top result in testing; use as a secondary fallback, not
# a first choice
qmd vsearch "$topic" --collection "$qmd_collection" --json

# Full hybrid retrieval with LLM reranking — slowest (~16-20s) and did not
# outperform --no-rerank in testing, occasionally ranked worse; reserve for
# cases specifically validated to need it
qmd query "$topic" --collection "$qmd_collection" --json
```

Always pass `--collection "$qmd_collection"`. Never issue a query, search, or vector search without the configured collection.

If qmd is missing or any retrieval command fails, report the failure and stop. Tell the user to verify `qmd --version`, inspect `qmd collection list`, and rerun setup if the configured collection is unavailable.

## Answer from retrieved pages

Parse the JSON results and load the five most relevant wiki pages into context. Answer from that wiki knowledge, distinguish retrieved facts from inference, and say when the wiki does not contain enough information.

## Maintain the index

After wiki content changes, run:

```bash
qmd update
qmd embed --collection "$qmd_collection"
```

`qmd update` incrementally checks all configured collections because it has no
collection filter. Always restrict `qmd embed` to the configured recall
collection.
