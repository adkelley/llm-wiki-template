---
name: recall
description: Triggers when the user runs `/recall [topic]` or asks Claude to "reload a <topic>"i, "query a <topic>. It parses the output from `qmd` and pre-loads the top 5 most relevant wiki pages into context before responding. This ensures answers are grounded in existing wiki knowledge rather than hallucinated from training data. 
---
# Recall — Query a Topic from the Wiki

Triggered by `/recall <topic>` or equivalent phrasing, where `<topic>` is the search topic to query. It uses `qmd` an on-device search engine for markdown files combining three strategies:

- BM25 full-text search — keyword precision.
- Vector semantic search — finds conceptually related pages even without keyword match.
- LLM re-ranking — highest quality; LLM scores results for relevance.
- All models run locally via node-llama-cpp with GGUF models. No data leaves your machine.

## What to do

### 1. Run qmd

run:
`npx qmd query "{topic}" --json`

### 2. Parse the output

Parse the output and pre-load the top 5 most relevant wiki pages
into context before responding. This ensures answers are grounded
in existing wiki knowledge rather than hallucinated from training data.

### 3. Respond to the user

Respond to the user with an answer that's grounded in existing wiki knowledge as described in the previous step
