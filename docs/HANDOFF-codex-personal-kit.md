# Handoff: Davo's Personal Day Kit — built and owned by Codex

You (Codex) are being handed ownership of a NEW personal productivity system for
Davo. This document is the spec. It was written by the Claude agent that
maintains the current system, with Davo's explicit decisions inlined.

## Mission

A standalone personal productivity kit: **open-day** and **close-day** rituals
(open-week/close-week later), a local **Visual Companion** web app, and
**Todoist as the single source of truth for tasks**. You run the rituals, you
serve the companion, and you are the ONLY agent that ever writes to Todoist.

## The reference repo — READ-ONLY

`/Users/claw/Projects/pp-fork` (branch `davo/todoist`) is a working fork of the
NSLS personal toolkit with a Todoist layer and a freshly redesigned plan
screen. **Never modify it.** Build in a fresh directory of your own (propose a
name/location to Davo). It will be abandoned once your kit is live — you are
its successor, not its maintainer.

What to mine from it:

| Path | What it is |
|---|---|
| `companion/server.py` | Flask routes + context builders — suggestion pipeline (union of AI picks + carry-overs, dedupe, tombstones, tooltips), plan-action, progress/estimate writers |
| `companion/templates/` | The whole UI: `_components/plan_your_day.html` (redesigned rows), `bonus_list.html`, `coach_morning.html`, `energy_row.html`, `task_table/task_rows` (command center), `command_banner.html`, `results.html` |
| `companion/static/tailwind.css` + `todoist.css` | The visual language: navy shell, gold accents, `.nsls-disc` progress circles, `.nsls-seg` segmented controls, `.sug-row`/`.plan-grid` redesign classes, `.pp-chips` provenance chips |
| `companion/todoist.py` | Marker format + `decorate()` for provenance chips |
| `companion/tests/` | A year of encoded bug fixes — read before re-deriving lessons (deleted items resurrecting, Enter double-fires, decoy headings, raw-vs-compacted index drift, estimate round-trips) |
| `skills/open-day/SKILL.md`, `skills/close-day/SKILL.md` | The ritual logic to reinterpret in your own agent-instruction format |
| `docs/plans/todoist-personal-fork.md` | The fork's Todoist design rationale |

## Davo's decisions (fixed — don't relitigate)

1. **Your kit is his only daily ritual.** The NSLS team toolkit continues to
   exist for his job, but he only runs it to test/improve team skills — and it
   never touches Todoist. No coordination needed beyond: stay off its turf.
2. **Todoist is the ultimate source of truth for tasks.** Single-writer rule:
   every Todoist write — from your chat ritual AND from the companion's
   buttons — goes through ONE shared write module. Two independent writers is
   the exact failure mode this project exists to end.
3. **Not in this kit, ever:** Obsidian vault, Familiar screen-capture,
   Airtable, Google Calendar ("this kit plans tasks, not meetings").
4. **Non-task ritual pieces** — morning energy, gratitude, daily insight,
   closing note, AI-suggestion text — live in **small local day files** (one
   per day, e.g. `data/days/YYYY-MM-DD.json`), not in Todoist, not in any
   vault. Todoist stays pure tasks.
5. **Phasing:** core loop first. Habits + streaks = Phase 2 (Todoist recurring
   tasks + the streak view; see `companion/streak.py` for the gap-aware streak
   rule). Open-week/close-week = Phase 3.
6. **Keep — these are the loved, non-negotiable features:**
   - Click-only companion UX. **Port the Flask/HTMX app and templates; do not
     rebuild from scratch.** UI stays, storage swaps.
   - The Plan-your-day redesign: EVERY unfinished item from the last close
     surfaces as a suggestion row — progress circle on the left, detail in
     hover tooltips ("From Tuesday · 50% done · ~0.5h left", "Deferred
     Wednesday", "Carried 4 days"), one compact Top 3 / Bonus / Defer / ✓ / ✕
     cluster per row. Nothing unfinished ever falls off the radar.
   - Taking an item carries its estimate AND its progress; the Command Center
     circle starts where yesterday stopped.
   - Pre-selects: the AI's #1 pick lands in Top 3 slot 1 and the top
     in-progress item in Bonus slot 1 at open — each one click to undo.
   - Provenance chips (which Todoist project/list an item came from). In your
     world these are native — the chip IS the Todoist project/label.
   - Estimated-remaining-hours boxes with the Timeboxing ⓘ explainer; the
     0/25/50/75/100 progress segments; "I'm done — close my day" as an
     all-day click; the closing note rendered on the page after close.
   - Heading hierarchy: the action is the headline ("Plan your day"), the
     full date ("Today — Wednesday, July 15, 2026") is the line under it.

## Architecture recommendation (deviate only with a stated reason)

- Port `companion/` wholesale. Replace the markdown/vault parser layer with
  two backends: **TodoistStore** (REST API, token from env) and **DayStore**
  (the local day files).
- Suggested Todoist modeling — your call on specifics, but every capability
  must round-trip: Top 3 = due today + `top3` label (or a Today section);
  Bonus = due today + `bonus`; Defer = reschedule to tomorrow; ✓ = complete;
  ✕ = delete PLUS a 7-day tombstone in the day files so close-day never
  re-suggests something Davo killed. Estimate → Todoist's native task
  **duration**. Progress % → no native field: pick a convention (label set or
  description marker) that survives the full loop.
- **Companion port: NOT 7777** (NSLS team companion) and **not 7788** (its
  test mode). Suggest 7787.
- Close click stays the close gate: a durable flag with transition-only
  semantics (a stale flag from days ago must never fire a close), and close
  never auto-runs without the click or an explicit "close day" from Davo.
- Port the relevant pytest suites (plan redesign, dispositions, estimate
  carry-forward) and adapt them to the new stores.

## Working rules

- `TODOIST_API_TOKEN` lives in an env file; source it by name. Never inline a
  secret in a command, log, or transcript.
- Never modify `pp-fork` or the NSLS toolkit; never write to the Obsidian
  vault; never bind 7777/7788; never add a second Todoist write path.
- Davo approves anything user-visible before it ships: show him a mockup or a
  screenshot of your own work (inspect it yourself first), then build on his
  green light. He will test personally before anything is called done.
- Communication: short, lead with the answer, plain language over jargon.

## Ask Davo before building (your open questions, not ours)

1. Name + location for your new repo/directory.
2. His current Todoist layout (projects, labels, sections he already uses) —
   model around what exists, don't invent a parallel taxonomy.
3. Anything he wants renamed in the ritual language now that it's personal
   (e.g. the "P " personal-prefix convention likely dies — everything here is
   personal).

Then propose your build plan (phases, file layout, Todoist mapping) and get
his sign-off before writing code.
