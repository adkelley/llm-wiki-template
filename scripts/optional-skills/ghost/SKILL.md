---
name: ghost
description: 
  Ghostwriter operation for LLM-wiki users. Reads 20+ wiki pages and raw notes to build a style
  profile of the user's voice, then writes or rewrites text that sounds like them — not like an LLM.
  Trigger whenever the user types `/ghost`, asks to "write this in my voice", "make this sound like
  me", "ghostwrite", "draft something that sounds like my notes", or any phrasing that implies
  generating text in the user's personal style. Also trigger for "rewrite this the way I'd say it",
  "match my tone", "write like I write", "clean this up but keep my voice", or requests to produce
  text (emails, essays, wiki pages, posts) that should read as authentically theirs. Always read the
  wiki before writing — never imitate a voice you haven't studied. If the wiki can't be found, say
  so and ask where it lives.
---

# /ghost

A **wiki-grounded ghostwriting operation**. You're not writing in a generic "casual" or "professional"
tone — you're studying the user's actual wiki pages and notes, extracting the specific patterns that
make their voice theirs, and producing text that a reader familiar with them would attribute to them,
not to an LLM.

LLM-default prose is the failure mode. Every sentence you write should pass the test: would this
survive in the user's wiki without looking like a foreign object?

---

## The Mental Model

In a properly maintained LLM-Wiki:

- **Raw sources** — immutable input documents (articles, papers, transcripts). Never modified.
- **The wiki** — LLM-maintained markdown pages: entity pages, concept pages, summaries, comparisons.
- **hot.md** — a compressed snapshot of recent context: decisions made, concepts under active
  investigation, open questions, and recent actions. The fastest entry point.
- **index.md** — a catalog of all wiki pages with one-line summaries. Shows what exists and its status.
- **log.md** — append-only chronological record of every ingest, query, and lint pass. Shows
  what has been worked on, when, and what questions have been asked.

`/ghost` reads the wiki layer to learn *how* the user thinks and writes, not just *what* they think
about. It then produces new text in that voice — or rewrites supplied text to match it.

The wiki is your style corpus. The more pages you read, the more precise the voice.

---

## Step 1 — Orient via hot.md, index.md, and log.md

Read these files first. They are the entry points.

```bash
cat wiki/hot.md      # compressed recent context — read this first if it exists
cat wiki/index.md    # full catalog of pages and their status
cat wiki/log.md      # chronological record of what's been done
```

**From hot.md**, extract:
- What the user is currently thinking about (so the ghostwritten text can draw on the right
  concepts without being told)
- The register and language hot.md itself uses — it was likely co-written by the user

**From index.md**, identify candidate pages to sample:
- Pages the user has likely edited or guided most closely (concept pages, opinion pieces,
  journal entries, personal notes — not pure source summaries)
- Pages spanning different topics and time periods (voice is more than one mood)
- Pages with substantial prose, not just lists or tables

**From log.md**, understand the user's recent queries:
- The phrasing of their questions reveals voice: terse or elaborate? Technical or colloquial?
- Recent ingests suggest what vocabulary and framing they're currently immersed in

Log entry format (adapt to whatever prefix convention the wiki uses):
```
## [YYYY-MM-DD] ingest | Source Title
## [YYYY-MM-DD] query  | Query text
## [YYYY-MM-DD] lint   | Notes
```

If none of these files exist, skip to the Fallback section.

---

## Step 2 — Read 20+ Pages to Build the Style Profile

This is the core investment. Read at least 20 wiki pages — more is better. You are reading for
**voice**, not content. The goal is to internalize the user's writing patterns so thoroughly that
you can produce text they'd recognize as their own.

```bash
# Start with pages most likely to reflect personal voice
# Concept pages, journal entries, opinion/analysis pages — not source summaries
cat wiki/page-1.md wiki/page-2.md wiki/page-3.md ...
```

As you read, extract signals across these dimensions:

### Sentence-Level Patterns

| Dimension | What to look for | Examples |
|-----------|-----------------|----------|
| **Length** | Short and punchy? Long and subordinate-clause-heavy? Mixed? | "This matters." vs. "This matters, though not for the reasons you'd expect, which I'll get to." |
| **Openings** | Does the user lead with assertions, questions, context-setting, or hedges? | "The key insight is..." vs. "I've been thinking about..." vs. "So here's the thing." |
| **Transitions** | Explicit connectives or implicit? Em-dashes, semicolons, or new paragraphs? | "However," vs. "—" vs. just starting the next thought |
| **Punctuation habits** | Em-dash heavy? Parenthetical asides? Colon-driven lists? Oxford comma? | "X — and this is critical — Y" vs. "X (though Y)" |

### Voice-Level Patterns

| Dimension | What to look for |
|-----------|-----------------|
| **Register** | Academic? Conversational? Technical-but-casual? Switches between registers? |
| **Person** | First person ("I think")? Impersonal ("one might argue")? Direct second person ("you")? |
| **Certainty gradient** | How do they express doubt vs. confidence? "Seems like" vs. "clearly" vs. "I'd bet"? |
| **Humor and tone** | Dry? Earnest? Self-deprecating? Absent? Where does it appear — asides, openings, never? |
| **Jargon comfort** | Do they define terms inline, use them without explanation, or avoid them? |

### Structural Patterns

| Dimension | What to look for |
|-----------|-----------------|
| **Paragraph length** | Dense blocks or frequent breaks? One-sentence paragraphs for emphasis? |
| **Headers** | Frequent and hierarchical? Rare and informal? Question-as-header? |
| **Lists vs. prose** | Does the user prefer bullet points, numbered lists, or flowing paragraphs? |
| **Wikilink density** | Heavy cross-referencing or self-contained pages? |
| **How they open a page** | Thesis-first? Context-first? In-medias-res? |
| **How they close** | Summary? Open question? Just... stop? Call to action? |

### Vocabulary Fingerprints

Note specific words and phrases the user gravitates toward. Every writer has them:
- Favorite qualifiers ("genuinely", "fundamentally", "sort of")
- Characteristic verbs ("unpack", "surface", "lean into", "sit with")
- Recurring metaphors or analogies (do they reach for spatial, mechanical, biological, musical?)
- Words they conspicuously avoid (some writers never say "utilize", "leverage", "synergy")

Do not list these back to the user. Internalize them.

---

## Step 3 — Compile the Style Profile (Internal)

Synthesize your observations into a compact internal profile. This is not output — it is your
working reference for generating text. Structure it as:

```
VOICE PROFILE (internal — do not show to user)
- Sentence rhythm: [e.g., "Short declarative followed by longer elaboration. Rarely more than
  two clauses. Frequent em-dashes for parenthetical asides."]
- Register: [e.g., "Technical vocabulary used casually — no hedging around jargon, but also
  no formality. Reads like a smart person talking to peers."]
- Person: [e.g., "First person dominant. 'I think' and 'I'd argue' are load-bearing. Rarely
  impersonal."]
- Certainty style: [e.g., "States views directly, then qualifies. 'X is true — though Y
  complicates it.' Not tentative but acknowledges complexity."]
- Paragraph shape: [e.g., "2–4 sentence paragraphs. Occasional one-liner for emphasis.
  Never walls of text."]
- Structural habits: [e.g., "Opens with the claim, not the context. Headers are short noun
  phrases. Closes with an open question."]
- Vocabulary fingerprints: [e.g., "'the thing is', 'non-trivial', 'surface' (as verb),
  avoids 'utilize' and 'leverage'"]
- What they DON'T do: [e.g., "No exclamation marks. No rhetorical questions as emphasis.
  No bullet lists for prose content. Never starts with 'In this document...'"]
```

The "what they DON'T do" section is as important as the rest. LLM-default habits that the user
avoids are the fastest way to sound fake.

---

## Step 4 — Write or Rewrite

Now produce the text the user asked for, governed entirely by the style profile.

### If generating new text:
- Write as if you are the user, drafting in their wiki
- Draw on the wiki's content and cross-references for substance — the user's voice includes
  the concepts they use and how they connect them
- Match their structural habits: if they open with claims, open with a claim; if they use
  em-dashes, use em-dashes; if they never use headers in short pieces, don't add headers

### If rewriting supplied text:
- Preserve the meaning and information exactly
- Transform the voice: sentence rhythm, word choice, register, structural habits
- Remove anything the user would never write (LLM-isms, filler, excessive hedging,
  corporate register — whatever the profile says they avoid)

### LLM-isms to Actively Suppress

These are the default patterns that make LLM-generated text immediately recognizable.
Suppress them unless the user's own writing actually uses them:

| LLM default | What to do instead |
|------------|-------------------|
| "Great question!" / "Absolutely!" | Match the user's actual response style |
| "Let's dive in" / "Let's explore" | Match the user's actual transition style |
| "It's important to note that..." | State the thing directly |
| "In conclusion," / "To summarize," | Match how the user actually closes |
| "Here are some key takeaways:" | Use the user's actual list/summary pattern |
| Tricolon lists ("X, Y, and Z") in every paragraph | Match the user's actual rhythm |
| Excessive hedging ("It's worth noting", "One might argue") | Match the user's certainty gradient |
| "This is a great [tool/approach/idea]" | Match the user's actual evaluative language |
| Starting paragraphs with "Additionally," / "Furthermore," / "Moreover," | Match the user's actual transitions |
| Exclamation marks for enthusiasm | Match the user's actual punctuation |

---

## Step 5 — Verify Against the Corpus

Before presenting the output, re-read 2–3 of the user's wiki pages and compare. Ask yourself:

- If this text appeared in the wiki alongside the user's real pages, would it blend in or
  stand out as foreign?
- Are the sentence lengths in the right range?
- Are the transitions the right kind?
- Is the register consistent — not drifting toward LLM-formal or LLM-casual?
- Are there any vocabulary fingerprints I missed or any I injected that aren't theirs?

If something feels off, revise before presenting. The user should not have to say "make it
sound more like me" — that means Step 2 wasn't thorough enough.

---

## Behavior Guidelines

**Read before writing.** Never imitate a voice you haven't studied. 20 pages is the minimum.
If the wiki is sparse, say so and ask the user to point you to more samples.

**Be specific about what you absorbed.** When presenting the output, you can briefly note
2–3 stylistic patterns you keyed on (e.g., "I noticed you tend to open with the conclusion
and work backward, so I followed that here"). Don't over-explain — just enough to show the
voice is grounded, not guessed.

**The profile is internal.** Don't dump the full style analysis on the user unless they ask.
The output is the proof; the profile is the scaffolding.

**Don't blend voices.** If the user asks you to ghostwrite a reply to someone, write in the
user's voice, not a hybrid of theirs and the recipient's.

**Respect the wiki's structure.** If the output is a wiki page, match the user's page
conventions: their frontmatter habits, header style, wikilink density, and how they cite sources.

**The user's voice includes their ideas.** Voice isn't just syntax. If the user consistently
frames problems through a particular lens (systems thinking, historical analogy, first-principles),
the ghostwritten text should reach for those same frames — not generic ones.

**Iterate on request.** If the user says "not quite" or "too formal" or "I wouldn't say it that
way," don't start over — adjust the specific dimension they're flagging. The profile is a living
document within the conversation.

---

## Fallback: Wiki Not Found

If hot.md, index.md, and log.md can't be located:

```
👻 I can't ghostwrite without studying your voice first.

Could you point me to your wiki or notes directory? I need to read at least
20 pages of your writing to build a reliable style profile.

If your notes live somewhere specific, just let me know where —
or paste a few samples of your writing into the conversation and I'll work from those.
```

Do not attempt to ghostwrite without a corpus. Writing without a voice profile is just writing.
