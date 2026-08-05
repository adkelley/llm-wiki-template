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

Use hybrid retrieval by default:

```bash
qmd query "$topic" --collection "$qmd_collection" --json
```

Use a different mode only when it better fits the request:

```bash
# Faster keyword lookup
qmd search "$topic" --collection "$qmd_collection" --json

# Faster semantic lookup
qmd vsearch "$topic" --collection "$qmd_collection" --json
```

Always pass `--collection "$qmd_collection"`. Never issue a query, search, or vector search without the configured collection.

If qmd is missing or any retrieval command fails, report the failure and stop. Tell the user to verify `qmd --version`, inspect `qmd collection list`, and rerun setup if the configured collection is unavailable.

## Answer from retrieved pages

Parse the JSON results and load the five most relevant wiki pages into context. Answer from that wiki knowledge, distinguish retrieved facts from inference, and say when the wiki does not contain enough information.

## Maintain the index

After wiki content changes, run:

```bash
qmd update
qmd embed
```

These commands update all configured collections, but incrementally process changed or unembedded content.
