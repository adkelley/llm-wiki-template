---
name: recall
description:  Queries the wiki for pages related to the specified `topic`. It is triggered when the user runs `/recall [topic]` or asks Claude to “reload [topic]” or “query [topic].” The command uses `qmd` to perform the search, parses the output, and preloads the five most relevant wiki pages into context before generating a response. This helps ensure responses are grounded in existing wiki content rather than inferred from prior training alone.
---
# Recall — Query a Topic from the Wiki

Triggered by `/recall <topic>` or equivalent phrasing, where `<topic>` is the search topic to query. It uses `qmd` an on-device search engine for markdown files that combinines three strategies:

- BM25 full-text search — keyword precision.
- Vector semantic search — finds conceptually related pages even without keyword match.
- LLM re-ranking — highest quality; LLM scores results for relevance.
- All models run locally via node-llama-cpp with GGUF models. No data leaves your machine.

## What to do

### 1. Run qmd

run:
`npx qmd query "{topic}" --json`

If `qmd` fails to run (e.g., not in user's path), then 1) inform the user that `qmd` doesn't exist or is not in their path.  Moreover, inform the user that information on `qmd`, including installation information, can be found at: [tobi/qmd](https://github.com/tobi/qmd). 2) Stop

### 2. Parse the output

Parse the output and pre-load the top 5 most relevant wiki pages
into context before responding. This ensures answers are grounded
in existing wiki knowledge rather than hallucinated from training data.

### 3. Respond to the user

Respond to the user with an answer that's grounded in existing wiki knowledge as described in the previous step
