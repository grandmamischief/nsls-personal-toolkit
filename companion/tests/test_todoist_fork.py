"""Personal-fork tests: Todoist markers, provenance chips, and the sync card.

The companion never talks to Todoist — these tests cover the local contract
the open-day/close-day skills depend on:
  - `<!--td:ID|proj|list-->` markers are stripped from all displayed text
    and preserved through every item move (take, disposition, carry-over)
  - dispositions (`### Done` / `### Deleted` / `### Deferred`) keep the
    marker so close-day can sync the canonical task
  - a wording tweak keeps the link; a slot reused for a new task drops it
  - the skill-authored `## Todoist Sync` section renders as a card
"""

from datetime import date, timedelta

import pytest

from companion.parsers import parse_daily_note_sections
from companion.server import (
    create_app,
    _build_plan_context,
    _extract_ai_suggestions,
    _extract_subsection_items,
    _extract_todoist_sync,
    _extract_top_3,
    _norm_suggestion,
    _set_nth_item_text,
)
from companion.todoist import decorate, parse_td, similar, strip_td, valid_payload

TD = "8837261034|nsls|tp"
MARK = f"<!--td:{TD}-->"


# --- todoist module unit tests ---

def test_strip_td_roundtrip():
    text, td = strip_td(f"Ship the KB owners doc <!--e:1.5--> {MARK}")
    assert td == TD
    assert "td:" not in text and "<!--e:1.5-->" in text  # only td is stripped

def test_strip_td_none():
    assert strip_td("Plain item") == ("Plain item", None)

def test_strip_td_duplicates_last_wins():
    text, td = strip_td(f"Task <!--td:1|nsls|tp--> {MARK}")
    assert td == TD and "td:" not in text

def test_parse_td():
    assert parse_td(TD) == {"id": "8837261034", "proj": "nsls", "list": "tp"}
    assert parse_td(None) is None
    assert parse_td("garbage") is None

def test_valid_payload():
    assert valid_payload(TD)
    assert valid_payload("abc123|3breaths|wp")
    assert not valid_payload("no pipes here")
    assert not valid_payload("id|proj|list|extra")
    assert not valid_payload("id|Proj|tp")  # uppercase project slug

def test_decorate_known_project():
    it = decorate({"td": "99|whisprcoach|wp"})
    assert it["td_proj_label"] == "Wispr"
    assert it["td_proj_cls"] == "pp-chip--wispr"
    assert it["td_wk"] is True

def test_decorate_without_marker():
    it = decorate({"text": "typed"})
    assert it["td"] is None and not it["td_wk"] and it["td_proj_label"] is None

def test_similar_wording_tweak_vs_replacement():
    assert similar("Ship the KB owners doc", "Ship KB owners doc today")
    assert not similar("Ship the KB owners doc", "Call the accountant")


# --- extraction ---

def test_top3_extraction_strips_marker_and_keeps_est():
    morning = f"### My Top 3\n1. [ ] Ship the doc <!--e:2--> {MARK}\n2. [ ] Plain task\n"
    items = _extract_top_3(morning)
    assert items[0]["text"] == "Ship the doc"
    assert items[0]["td"] == TD
    assert items[0]["est"] == 2
    assert items[0]["td_proj_label"] == "NSLS"
    assert items[1]["td"] is None

def test_ai_suggestions_carry_marker():
    # AI Suggested items are NUMBERED lines (the _AI_ITEM_LEAD_RE contract) —
    # the open-day skill must seed Todoist candidates the same way.
    morning = f"### AI Suggested: Todoist\n1. Ship the doc {MARK}\n2. Unlinked idea\n"
    items = _extract_ai_suggestions(morning)
    assert items[0]["td"] == TD and items[0]["text"] == "Ship the doc"
    assert items[1]["td"] is None

def test_subsection_items_and_norm_ignore_markers():
    morning = f"### Deleted\n- Ship the doc {MARK}\n"
    assert _extract_subsection_items(morning, "Deleted") == {"Ship the doc"}
    assert _norm_suggestion(f"Ship the doc {MARK}") == _norm_suggestion("Ship the doc")


# --- _set_nth_item_text link retention ---

def test_rename_keeps_link_replacement_drops_it():
    md = f"## Morning Check-in\n\n### My Top 3\n1. [ ] Ship the KB owners doc {MARK}\n"
    tweaked = _set_nth_item_text(md, "### My Top 3", 0, "Ship KB owners doc (final)")
    assert MARK in tweaked
    replaced = _set_nth_item_text(md, "### My Top 3", 0, "Call the accountant")
    assert "td:" not in replaced


# --- endpoint round-trips ---

@pytest.fixture
def client_with_today(tmp_path):
    vault = tmp_path / "vault"
    daily = vault / "01-daily"
    daily.mkdir(parents=True)
    habits = vault / "30-habits"
    habits.mkdir(parents=True)

    today = date.today().isoformat()
    (daily / f"{today}.md").write_text(f"""# Daily Note

## Morning Check-in

### AI Suggested: Top 3
1. Ship the doc <!--e:2--> {MARK}
2. Unlinked idea

### My Top 3
1. [ ]{' '}
2. [ ]{' '}
3. [ ]{' '}

### Bonus

### Habits
- [ ] **Walk**

## Todoist Sync

*Synced 07:42 — say the word in chat if any of these are wrong.*
- ⭐ Today priority: Ship the doc (NSLS)
""")
    (habits / "habits.md").write_text("# Daily Habits\n\n## Active\n\n- id: walk\n  name: Walk\n")
    (habits / "log.md").write_text("# Daily habit log\n")

    app = create_app(vault_path=str(vault))
    app.config["TESTING"] = True
    try:
        yield (app.test_client(), vault)
    finally:
        app.config["WATCHER"].stop()


def _note(vault):
    return (vault / "01-daily" / f"{date.today().isoformat()}.md").read_text()


def test_take_as_priority_carries_marker(client_with_today):
    client, vault = client_with_today
    resp = client.post("/plan-action", data={"text": "Ship the doc", "action": "pri",
                                             "est": "2", "td": TD})
    assert resp.status_code == 200
    morning = parse_daily_note_sections(_note(vault))["Morning Check-in"]
    top3_lines = [l for l in morning.splitlines() if l.startswith("1.")]
    assert top3_lines and "Ship the doc" in top3_lines[0]
    assert MARK in top3_lines[0] and "<!--e:2-->" in top3_lines[0]

def test_delete_disposition_carries_marker_and_untoggles(client_with_today):
    client, vault = client_with_today
    client.post("/plan-action", data={"text": "Ship the doc", "action": "delete", "td": TD})
    morning = parse_daily_note_sections(_note(vault))["Morning Check-in"]
    deleted_lines = [l for l in morning.splitlines() if l.strip().startswith("- Ship the doc")]
    assert any(MARK in l for l in deleted_lines), "tombstone must keep the Todoist link"
    # Untoggle: marker-tolerant match must find and remove the line.
    client.post("/plan-action", data={"text": "Ship the doc", "action": "delete", "td": TD})
    assert _extract_subsection_items(
        parse_daily_note_sections(_note(vault))["Morning Check-in"], "Deleted") == set()

def test_invalid_td_payload_rejected(client_with_today):
    client, _vault = client_with_today
    resp = client.post("/plan-action", data={"text": "Ship the doc", "action": "pri",
                                             "td": "<script>alert(1)</script>"})
    assert resp.status_code == 400

def test_command_center_delete_records_marker(client_with_today):
    client, vault = client_with_today
    client.post("/plan-action", data={"text": "Ship the doc", "action": "pri", "td": TD})
    resp = client.post("/delete-task", data={"section": "top_3", "index": "0"})
    assert resp.status_code == 200
    morning = parse_daily_note_sections(_note(vault))["Morning Check-in"]
    deleted = [l for l in morning.splitlines() if "- Ship the doc" in l and MARK in l]
    assert deleted, "command-center tombstone must keep the Todoist link"

def test_chips_render_in_plan_and_sync_card(client_with_today):
    client, _vault = client_with_today
    html = client.get("/?mode=coach-morning").get_data(as_text=True)
    assert "pp-chip--nsls" in html          # project chip on the suggestion row
    assert "pp-chip--t" in html             # Ⓣ linked chip
    assert MARK not in html.replace("&lt;", "<")  # marker never visible as text
    assert "Todoist sync" in html           # audit card renders in plan mode
    assert "Today priority: Ship the doc" in html

def test_sync_card_renders_in_command_center(client_with_today):
    client, _vault = client_with_today
    html = client.get("/?mode=command").get_data(as_text=True)
    assert "Todoist sync" in html


# --- carry-over persistence across days ---

def test_carryover_carries_marker(tmp_path):
    vault = tmp_path / "vault"
    daily = vault / "01-daily"
    daily.mkdir(parents=True)
    (vault / "30-habits").mkdir(parents=True)
    (vault / "30-habits" / "habits.md").write_text("# Daily Habits\n\n## Active\n")
    (vault / "30-habits" / "log.md").write_text("")

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (daily / f"{yesterday}.md").write_text(f"""# Daily Note

## Morning Check-in

### My Top 3
1. [ ] Ship the doc <!--e:1--> {MARK}
2. [x] Finished thing
""")
    (daily / f"{today}.md").write_text("# Daily Note\n\n## Morning Check-in\n")

    plan = _build_plan_context((daily / f"{today}.md").read_text(), vault, today, [], [])
    carried = [s for s in plan["suggestions"] if s["text"] == "Ship the doc"]
    assert carried and carried[0]["td"] == TD
    assert carried[0]["td_proj_label"] == "NSLS"


def test_dedup_marker_bearing_copy_wins(tmp_path):
    vault = tmp_path / "vault"
    (vault / "01-daily").mkdir(parents=True)
    today = date.today().isoformat()
    md = f"""# Daily Note

## Morning Check-in

### AI Suggested: Top 3
1. Ship the doc

### AI Suggested: Todoist
1. Ship the doc {MARK}
"""
    plan = _build_plan_context(md, vault, today, [], [])
    matches = [s for s in plan["suggestions"] if s["text"] == "Ship the doc"]
    assert len(matches) == 1, "same task from two sources must collapse to one row"
    assert matches[0]["td"] == TD, "the marker-bearing copy's link must survive dedup"


def test_extract_todoist_sync_section():
    md = "# N\n\n## Todoist Sync\n\n*Synced 07:42*\n- ✅ Completed: X\n\n## End of Day\n"
    assert _extract_todoist_sync(md) == ["*Synced 07:42*", "- ✅ Completed: X"]
    assert _extract_todoist_sync("# N\n\n## Morning Check-in\n") == []
