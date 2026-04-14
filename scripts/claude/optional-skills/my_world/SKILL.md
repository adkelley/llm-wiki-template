---
name: my-world
description: Session startup briefing skill. Triggers when the user runs `/my-world` or asks Claude to "start a new session", "load my world", "give me a session briefing", or "read my vault". Reads VAULT-INDEX.md, wiki/index.md, and the last 10 entries from wiki/log.md, then produces a structured session briefing covering current state, open threads, and suggested next actions.
---

# My World — Session Briefing

Triggered by `/my-world` or equivalent phrasing.

## What to do

### 1. Read the three source files

In parallel, read:
- `VAULT-INDEX.md` — top-level index of the vault (people, projects, places, concepts)
- `wiki/index.md` — wiki table of contents / current state overview
- `wiki/log.md` — running log; extract only the **last 10 entries**

If any file is missing, note it in the briefing and continue with what's available.

### 2. Extract the last 10 log entries

Log entries are delimited by `## YYYY-MM-DD` headers (or similar date markers). 
Count from the bottom of the file. If the log uses a different delimiter, adapt.

### 3. Produce the session briefing

Output a structured briefing with these sections:

---

**🌍 World State**  
2–4 sentence summary of where things stand based on `VAULT-INDEX.md` and `wiki/index.md`.

**📋 Recent Activity** *(last 10 log entries)*  
Bullet list of key events, decisions, or changes — one line per entry, most recent first.

**🔴 Open Threads**  
Any unresolved items, open questions, or flagged TODOs surfaced from the logs or wiki.

**💡 Suggested Focus**  
1–3 suggested areas to work on this session, based on recency and open threads.

---

Keep the briefing scannable — headers, short bullets, no walls of text.
Invite the user to dive into any section or ask follow-up questions.