# Todoist Integration — Davo's Personal Fork

**Status: active spec** · Branch `davo/todoist` on `grandmamischief/nsls-personal-toolkit` (upstream: `thensls/nsls-personal-toolkit`)
**Scope: personal fork only — never PR'd upstream.** Bugs found in upstream behavior get reported to the team-repo agent, not fixed here.

## Goal

Todoist is the **single source of truth for what tasks exist and whether they're done**. The toolkit (open-day / close-day / companion) is the planning-and-progress layer on top. Any decision Davo makes in the companion (Plan Your Day or Command Center) about a Todoist-linked item is a decision *about Todoist* and must land there — batched at two sync points, with an audit report each time. Progress % stays local; Todoist never sees it.

Codex (another agent) and Davo also operate the same board — see `~/Documents/Claude/Projects/Personal Productivity/TODOIST_TASK_MANAGER_PLAN_AND_CLAUDE_HANDOFF.md` for the shared-agent rules and board structure. Key facts from it:

- Projects: NSLS, WhisprCoach, General, Habits, Personal, Inbox (capture), 3 Breaths.
- Lists are **labels**, not dates: `@today_priority`, `@today_bonus`, `@week_priority`, `@week_bonus`. Today is a *persistent working state* — items stay in Today across midnight until completed or explicitly removed. Never add fake due dates.
- Rules: ≤3 active `@today_priority` (excluding `@daily_anchor`); `@today_priority` implies `@week_priority`; search before creating; re-read a task immediately before changing it (human edits win); idempotent updates; audit after changes.

## Decisions (Davo, 2026-07-15)

1. **Delete = hard delete, everywhere.** Davo's intent is that 3 Breaths is *his* list (visibility-shared at most, not co-worked). **First-run check:** on the first real sync, fetch 3 Breaths collaborators; if anyone besides Davo is a member, flag it in the report so he can align Codex's rules. Until told otherwise afterward, deletes still apply there.
2. **Full mirror at plan time.** When the morning plan is finalized, the Top 3 become the *only* `@today_priority` tasks and the Bonus list maps to `@today_bonus`. Anything that held a today-label but wasn't chosen gets **bumped to week tier**: from `@today_priority` → keeps `@week_priority` (already implied), from `@today_bonus` → `@week_bonus`. *Tier-preserving on purpose: defer means deprioritize, not promote.* All removals are reported, never silent.
3. **New typed items get created in Todoist.** Confident about the project → file it there with the right labels. Not confident → **Inbox** + flag in the report. No blocking questions in chat at close.
4. **Fork convention:** GitHub fork under Davo's account (like the 7 other teammates' forks), `davo/todoist` branch, upstream = team repo. Public repo; a heads-up in the fork's README is fine.

## Architecture

**The companion never talks to Todoist.** It renders provenance, preserves ID markers through every item move, and records dispositions — all in the daily note, as today. **All Todoist reads/writes happen in the Claude session via the Todoist MCP server** (`https://ai.todoist.net/mcp`, user-scope config, OAuth — never a token in this repo) at exactly two sync points:

- **SYNC-A (morning):** after the builder finishes Plan Your Day (companion Done click / typed "done" resumes the open-day session).
- **SYNC-B (evening):** during close-day, after the fresh close confirmation and the Step 1 read of final dispositions.

Between sync points, companion changes accumulate locally. Mid-day edits made directly in Todoist (by Davo or Codex) are *absorbed* at the next sync: **Todoist wins on task existence and done/not-done; companion clicks win on dispositions; conflicts get flagged in the report, never silently resolved.**

### Gates

The Todoist steps run only when **both** hold:

- `todoist_sync: on` in `$OBSIDIAN_VAULT_PATH/50-reference/builder-profile.md` frontmatter (absent/off → skip silently; keeps `-t` demos and any future upstream merge inert), and
- **not** test mode (`-t`). `open day -t` is exactly the vanilla teammate experience.

If the MCP server is unreachable/unauthenticated at a sync point: one warning line in chat + in the report section, then continue the ritual normally without Todoist. Never block the ritual on Todoist.

## The marker

Todoist identity rides invisibly on item lines, same trick as the existing `<!--e:X-->` estimate marker:

```
- Ship the KB owners doc <!--e:1.5--> <!--td:8837261034|nsls|tp-->
```

`<!--td:ID|PROJECT|LIST-->` where:

- `ID` — Todoist task id (string).
- `PROJECT` — slug: `nsls` · `whisprcoach` · `general` · `personal` · `habits` · `3breaths` · `inbox`.
- `LIST` — which list it was seeded from / belongs to: `tp` (today_priority) · `tb` (today_bonus) · `wp` (week_priority) · `new` (created by sync).

Rules:

- Markers are stripped from all displayed/compared text and preserved through every move: suggestion → Top 3/Bonus slot, disposition records (`### Done` / `### Deleted` / `### Deferred` lines carry the marker — close-day depends on this), carry-overs across days, text edits.
- **Manual text edits:** if the new text still substantially overlaps the old (token Jaccard ≥ 0.5) the marker is kept (wording tweak); otherwise dropped (slot reused for a different task). Unlinked items are re-matched fuzzily at the next sync — a dropped link degrades to a match/create; a wrong link would mutate the wrong task. Safety wins.
- Companion `_norm_suggestion` dedup ignores markers; when a task arrives from two sources (yesterday's carry-over AND Todoist Today), **the marker-bearing copy wins**.

## Provenance UI

Chips rendered next to items in the suggestions grid, Top 3 / Bonus rows, and Command Center rows:

| Chip | Meaning | Color |
|------|---------|-------|
| Ⓣ | Lives in Todoist (has marker) | outlined, neutral |
| `NSLS` | project | navy `#1e3a5f` |
| `Wispr` | WhisprCoach project | violet `#7c3aed` |
| `Pers` | Personal project | green `#16a34a` |
| `3B` | 3 Breaths project | teal `#0d9488` |
| `Gen` | General project | slate `#64748b` |
| `Inbox` | Inbox project | amber `#d97706` |
| `wk` | seeded from `@week_priority` (taking it into Top 3 adds today labels) | outlined, subtle |
| `AI` | AI-suggested (existing `AI:` source, no marker) | dashed outline |

No chip at all = hand-typed, vault-only (until a sync links or creates it).

## SYNC-A — morning reconcile (open-day)

**Fetch** (new Step 2j, parallel with other collection): open tasks with `@today_priority`, `@today_bonus`, `@week_priority`. Exclude: Habits project (companion owns habit tracking), `@daily_anchor` tasks, completed tasks, `@week_bonus` (deliberately not surfaced — Davo 2026-07-15).

**Seed** (Step 6): Todoist items join the candidate pool (`### AI Suggested:` sections) with markers, today-priority items listed first. Normalized-dedup against carry-overs/AI items; marker-bearing copy wins. Everything stays a *priority candidate* per the Seeding Principle — no pre-bucketing into Bonus (the `tb`/`wp` origin shows as a chip, and the AI's suggested ordering can reflect it).

**Reconcile** (after the builder's Done):

1. Re-read today's note: final Top 3, Bonus, dispositions.
2. Re-read every involved Todoist task (handoff rule 3) — a task completed/deleted in Todoist mid-morning is reported, not resurrected.
3. Apply, idempotently:
   - Top 3 members: linked → ensure `@today_priority` (+`@week_priority`); unlinked → match against fetched open tasks (fuzzy); high-confidence → link (write marker into the note line) + label; no match → **create** (project per Decision 3) with `@today_priority` + `@week_priority`, write marker back.
   - Bonus members: same, with `@today_bonus`.
   - Suggestion-row **Done** (incl. items never taken into the plan): complete the task.
   - Suggestion-row **Delete**: hard-delete the task.
   - **Defer** / had-today-label-but-not-chosen: strip `@today_*`; bump per Decision 2 (`tp`→ keeps `wp`; `tb`→ add `@week_bonus`).
   - Cap check: after mirror, `@today_priority` count ≤3 by construction; if outside tasks reappeared mid-sync, flag.
4. Write the **`## Todoist Sync`** section (see Report) + one-line chat pointer. First run: 3 Breaths collaborator check result goes here.

## SYNC-B — evening sync (close-day)

After the fresh close confirmation and Step 1's read of final state (new step just before the daily-note write; audit section written with the note):

- Top 3 / Bonus items with markers: progress **100% → complete** in Todoist. **<100% → leave open** — Todoist's Today is persistent, so it carries to tomorrow by itself; the note's `## Carrying Over` seeding continues to work as today (and carries the `<!--td:-->` marker exactly like `<!--e:-->`).
- `### Deleted` items with markers → hard-delete.
- `### Deferred` items with markers → strip `@today_*`, bump to week tier (Decision 2).
- Items added during the day (Command Center bonus adds, etc.) without markers → match/create exactly like SYNC-A step 3 (Inbox fallback + flag).
- `### Unplanned` items: **out of scope v1** — they're a record of unplanned work done, not tasks. Revisit if Davo wants them logged as completed Todoist tasks.
- Write `## Todoist Sync` audit into the note; companion renders it; final chat summary includes the highlights + "flag anything wrong in chat."

## Report — `## Todoist Sync`

Skill-authored top-level section (companion renders it as a card in both Plan Your Day and Command Center modes; never companion-written). Format, one line per change, grouped:

```
## Todoist Sync

*Synced 07:42 — say the word in chat if any of these are wrong.*

- ✅ Completed: Reply to vendor thread (NSLS)
- 🗑 Deleted: Old draft cleanup (Personal)
- ⭐ Today priority: Ship KB owners doc (NSLS) · Prep roadshow deck (NSLS) · Wispr onboarding flow (Wispr)
- 🔖 Bonus today: …
- ⬇️ Bumped to week: Refactor signal config (was Today-Bonus → Week-Bonus)
- ➕ Created: Call the accountant → Inbox ⚠️ (wasn't sure of project — re-file if wrong)
- ⚠️ Conflict: "Draft LOP summary" was completed in Todoist at 11:02 but sits at 50% here — left completed in Todoist.
```

## Edge cases & self-healing

- **reset-day**: clears the note only; Todoist untouched. Re-opening re-seeds and the next reconcile re-mirrors — labels self-heal to the new plan. No special handling.
- **Re-running open-day / double sync**: all mutations are idempotent (label add/remove, complete, delete by id). A second reconcile of an unchanged plan is a no-op.
- **Past-date close** (`close day` catching up an old day): SYNC-B still applies — completions/deletions are still true; bumps skip (that "today" is gone) — noted in report.
- **Marker on a task deleted in Todoist mid-day**: re-read finds it gone → report line, no error.
- **MCP down**: skip + warn, ritual continues. Nothing queues; next sync point reconciles from current state.

## Out of scope (v1)

Open-week / close-week rituals · `### Unplanned` logging · live mid-day sync (would need a token in the companion — different auth path, race-prone; see Architecture) · progress % anywhere in Todoist · `@week_bonus` surfacing.

## Ops

- **Update from upstream**: `git fetch upstream && git merge upstream/main` on `davo/todoist` (this session owns conflict resolution). open-day prints a one-line nudge when upstream/main has new commits.
- **Live wiring**: the 20 skill shims in `~/.claude/skills/*/SKILL.md` point here (`~/Projects/pp-fork`); the companion venv lives at `companion/.venv` in this clone; `.env` is copied from the old checkout (gitignored).
- **Team-repo work**: still happens in `~/.claude/local-plugins/nsls-personal-toolkit` via the PP Viz session. Buffs meant for everyone go there; this fork merges them back via upstream/main once they land.
- **Todoist MCP**: `claude mcp add --scope user --transport http todoist https://ai.todoist.net/mcp` (done 2026-07-15) + one-time OAuth by Davo.
