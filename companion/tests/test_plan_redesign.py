"""Plan-Your-Day redesign (2026-07-15, Davo): every unfinished item from the
previous close surfaces as a suggestion (AI picks + carry-overs UNIONED, not
either/or), progress carries with the item, deferred items come back, and the
row detail (source day / % done / hours left) lives in hover tooltips instead
of visible clutter."""

from datetime import date, timedelta
import pytest
from companion.server import create_app, _extract_carryovers, _build_plan_context
from companion.parsers import parse_daily_note_sections


TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
WEEKDAY = (date.today() - timedelta(days=1)).strftime("%A")


YESTERDAY_NOTE = """---
status: closed
---
# Daily Note

## Morning Check-in

### My Top 3
1. [ ] Prep the board update <!--p:75--> <!--e:2.5-->
2. [x] Finished thing <!--e:1-->

### Bonus
1. [ ] P Jarvis <!--p:50--> <!--e:0.5-->
2. [ ] P inbox build <!--p:25-->
3. [x] Shipped bonus

### Done
- Old done item

### Deferred
- P Governance Agreement <!--e:0.5-->
"""

TODAY_NOTE = """---
status: planning
---
# Daily Note

## Morning Check-in

### AI Suggested: Top 3
1. Prep the board update <!--e:2.5-->
2. Brand new AI idea

### My Top 3
1. [ ]
2. [ ]
3. [ ]

### Bonus

### Habits
- [ ] **Walk**
"""


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "01-daily").mkdir(parents=True)
    habits = vault / "30-habits"
    habits.mkdir(parents=True)
    (habits / "habits.md").write_text("# Daily Habits\n\n## Active\n\n- id: walk\n  name: Walk\n")
    (habits / "log.md").write_text("# Daily habit log\n")
    (vault / "01-daily" / f"{YESTERDAY}.md").write_text(YESTERDAY_NOTE)
    (vault / "01-daily" / f"{TODAY}.md").write_text(TODAY_NOTE)
    app = create_app(vault_path=str(vault))
    app.config["TESTING"] = True
    try:
        yield (app.test_client(), vault)
    finally:
        app.config["WATCHER"].stop()


def _plan(vault):
    md = (vault / "01-daily" / f"{TODAY}.md").read_text()
    morning = parse_daily_note_sections(md).get("Morning Check-in", "")
    from companion.server import _extract_top_3, _extract_bonus
    return _build_plan_context(md, vault, TODAY,
                               _extract_top_3(morning), _extract_bonus(morning))


# --- carry-over extraction ---

def test_carryovers_include_progress_and_deferred(client):
    _, vault = client
    items = {i["text"]: i for i in _extract_carryovers(vault, TODAY)}
    # unchecked Top 3 + Bonus carry with progress AND estimate
    assert items["Prep the board update"]["progress"] == 75
    assert items["Prep the board update"]["est"] == 2.5
    assert items["P Jarvis"]["progress"] == 50
    assert items["P inbox build"]["progress"] == 25
    # deferred items come back (defer = "not today", not "never")
    assert items["P Governance Agreement"]["deferred"] is True
    assert items["P Governance Agreement"]["est"] == 0.5
    # checked items don't carry
    assert "Finished thing" not in items
    assert "Shipped bonus" not in items


# --- union + metadata merge ---

def test_suggestions_union_ai_and_carryovers(client):
    _, vault = client
    plan = _plan(vault)
    texts = [s["text"] for s in plan["suggestions"]]
    # AI picks first, then every remaining unfinished item — nothing dropped
    assert texts[0] == "Prep the board update"
    assert "Brand new AI idea" in texts
    assert "P Jarvis" in texts
    assert "P inbox build" in texts
    assert "P Governance Agreement" in texts
    # deduped: the AI-worded twin absorbs the carry-over, one row only
    assert texts.count("Prep the board update") == 1


def test_ai_item_inherits_carryover_progress(client):
    _, vault = client
    by_text = {s["text"]: s for s in _plan(vault)["suggestions"]}
    merged = by_text["Prep the board update"]
    assert merged["progress"] == 75          # from yesterday's marker
    assert merged["est"] == 2.5
    assert f"From {WEEKDAY}" in merged["tip"] or "Carried" in merged["tip"]
    assert "75% done" in merged["tip"]
    assert "~2.5h left" in merged["tip"]


def test_tips_cover_all_source_shapes(client):
    _, vault = client
    by_text = {s["text"]: s for s in _plan(vault)["suggestions"]}
    assert by_text["Brand new AI idea"]["tip"] == "AI: Top 3 — new today"
    assert f"Deferred {WEEKDAY}" in by_text["P Governance Agreement"]["tip"]
    assert "50% done" in by_text["P Jarvis"]["tip"]


def test_carried_days_streak_in_tip(client, tmp_path):
    _, vault = client
    # The same item open in 3 consecutive prior notes → "Carried 3 days".
    for back in (2, 3):
        d = (date.today() - timedelta(days=back)).isoformat()
        (vault / "01-daily" / f"{d}.md").write_text(
            "## Morning Check-in\n\n### My Top 3\n1. [ ] P Jarvis <!--p:25-->\n")
    by_text = {s["text"]: s for s in _plan(vault)["suggestions"]}
    assert "Carried 3 days" in by_text["P Jarvis"]["tip"]


# --- taking a suggestion carries the progress marker ---

def test_plan_action_carries_progress_marker(client):
    c, vault = client
    resp = c.post("/plan-action", data={"action": "pri", "text": "Prep the board update",
                                        "est": "2.5", "p": "75"})
    assert resp.status_code == 200
    note = (vault / "01-daily" / f"{TODAY}.md").read_text()
    top3_block = note.split("### My Top 3")[1].split("###")[0]
    line = next(l for l in top3_block.splitlines() if "Prep the board update" in l)
    assert "<!--p:75-->" in line
    assert "<!--e:2.5-->" in line


def test_plan_action_bonus_carries_progress(client):
    c, vault = client
    c.post("/plan-action", data={"action": "bonus", "text": "P Jarvis",
                                 "est": "0.5", "p": "50"})
    note = (vault / "01-daily" / f"{TODAY}.md").read_text()
    assert "P Jarvis <!--p:50--> <!--e:0.5-->" in note


def test_plan_action_bad_progress_still_takes(client):
    c, vault = client
    resp = c.post("/plan-action", data={"action": "pri", "text": "P inbox build", "p": "banana"})
    assert resp.status_code == 400  # non-numeric rejected outright
    resp = c.post("/plan-action", data={"action": "pri", "text": "P inbox build", "p": "100"})
    assert resp.status_code == 200  # 100 isn't a carryable partial — dropped
    note = (vault / "01-daily" / f"{TODAY}.md").read_text()
    assert "P inbox build" in note
    assert "P inbox build <!--p:100-->" not in note


# --- rendering: clean rows, tooltips, aligned grid, pre-lit taken state ---

def test_plan_page_rows_are_clean_with_tooltips(client):
    c, _ = client
    html = c.get("/?mode=coach-morning").get_data(as_text=True)
    # new heading + instruction, old table gone
    assert "Decide today" in html
    assert "Allocate each task." in html
    assert "Suggestions &amp; carry-overs" not in html
    # segmented action cluster, not five checkbox columns
    assert 'class="sug-seg"' in html
    assert html.count("sug-row") >= 5
    # est/progress detail rides in tooltips, never as visible row text
    assert 'title="' in html and "~2.5h left" in html
    assert ">~2.5h left<" not in html
    assert ">75% done<" not in html
    # progress circle carries the % via the conic-gradient var
    assert "nsls-disc--partial" in html and "--p: 50" in html
    # take-buttons pass est AND progress along
    assert '"est": "2.5"' in html
    assert '"p": "75"' in html


def test_taken_suggestion_lights_segment_and_dims_row(client):
    c, _ = client
    c.post("/plan-action", data={"action": "pri", "text": "P Jarvis", "p": "50"})
    html = c.get("/?mode=coach-morning").get_data(as_text=True)
    assert "sug-row taken" in html
    assert 'class="on"' in html


def test_bonus_rows_have_estimate_inputs_and_carried_disc(client):
    c, _ = client
    c.post("/plan-action", data={"action": "bonus", "text": "P Jarvis",
                                 "est": "0.5", "p": "50"})
    html = c.get("/?mode=coach-morning").get_data(as_text=True)
    assert '"section":"bonus"' in html          # bonus est input wired
    assert "Carried at 50%" in html             # mini disc on the bonus row
    assert 'id="bonus-list" class="plan-grid"' in html


def test_header_swap_and_energy_words(client):
    c, _ = client
    html = c.get("/?mode=coach-morning").get_data(as_text=True)
    # "Plan your day" is the big heading; the date is the small line under it
    assert html.index(">Plan your day") < html.index("Today — ")
    # energy control uses full words in the word-width segmented control
    assert "Medium" in html
    assert "nsls-seg--words" in html
    # timeboxing info icon sits on the est column header
    assert "Est. remaining" in html
    assert "timeboxing" in html.lower()
