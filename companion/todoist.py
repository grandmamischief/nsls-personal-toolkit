"""Todoist provenance layer — PERSONAL FORK (davo/todoist).

Items that live in Todoist carry an invisible HTML-comment marker on their
markdown line, the same round-trip trick as the ``<!--e:X-->`` estimate and
``<!--p:NN-->`` progress markers:

    - Ship the KB owners doc <!--e:1.5--> <!--td:8837261034|nsls|tp-->

``<!--td:ID|PROJECT|LIST-->`` where ID is the Todoist task id, PROJECT is a
slug from PROJECTS below, and LIST records which Todoist list the item was
seeded from (``tp``=today_priority, ``tb``=today_bonus, ``wp``=week_priority,
``new``=created by a sync).

The companion NEVER talks to Todoist. It only (a) strips the marker from all
displayed/compared text, (b) preserves it through every item move, and
(c) renders provenance chips. The open-day/close-day skills read the raw
markdown (markers intact) and do the actual Todoist mutations via MCP.
See docs/plans/todoist-personal-fork.md.
"""

import re

TD_RE = re.compile(r"\s*<!--\s*td:([^>|\s]+)\|([a-z0-9]+)\|([a-z]+)\s*-->")

# Accepted shape for the raw payload ("ID|proj|list") when it round-trips
# through a form field. Rejecting anything else keeps hand-crafted POSTs from
# injecting arbitrary comment text into the note.
TD_PAYLOAD_RE = re.compile(r"^[^>|\s]{1,64}\|[a-z0-9]{1,24}\|[a-z]{1,8}$")

PROJECTS = {
    "nsls": {"label": "NSLS", "cls": "pp-chip--nsls"},
    "whisprcoach": {"label": "Wispr", "cls": "pp-chip--wispr"},
    "personal": {"label": "Pers", "cls": "pp-chip--pers"},
    "3breaths": {"label": "3B", "cls": "pp-chip--3b"},
    "general": {"label": "Gen", "cls": "pp-chip--gen"},
    "inbox": {"label": "Inbox", "cls": "pp-chip--inbox"},
    "habits": {"label": "Habit", "cls": "pp-chip--gen"},
}


def strip_td(text: str) -> tuple[str, str | None]:
    """Remove every ``<!--td:...-->`` marker from item text.

    Returns (clean_text, payload) where payload is the raw ``ID|proj|list``
    string (last marker wins, all are removed) or None.
    """
    payload: str | None = None
    m = TD_RE.search(text)
    while m:
        payload = f"{m.group(1)}|{m.group(2)}|{m.group(3)}"
        text = text[: m.start()] + text[m.end():]
        m = TD_RE.search(text)
    return (text.strip(), payload) if payload is not None else (text, None)


def parse_td(payload: str | None) -> dict | None:
    """``"8837|nsls|tp"`` → ``{"id": "8837", "proj": "nsls", "list": "tp"}``."""
    if not payload:
        return None
    parts = payload.split("|")
    if len(parts) != 3:
        return None
    return {"id": parts[0], "proj": parts[1], "list": parts[2]}


def fmt_td(payload: str) -> str:
    """Payload → the marker text to append to a line (leading space included)."""
    return f" <!--td:{payload}-->"


def valid_payload(payload: str) -> bool:
    return bool(TD_PAYLOAD_RE.match(payload))


def decorate(item: dict) -> dict:
    """Add template-facing chip fields to an item dict that has a ``td`` key.

    Fields: ``td_id``, ``td_list``, ``td_wk`` (seeded from week_priority),
    ``td_proj_label`` / ``td_proj_cls`` (None when project unknown).
    Safe to call on items without a marker — fields default falsy.
    """
    info = parse_td(item.get("td"))
    if info is None:
        item.setdefault("td", None)
        item["td_id"] = None
        item["td_list"] = None
        item["td_wk"] = False
        item["td_proj_label"] = None
        item["td_proj_cls"] = None
        return item
    proj = PROJECTS.get(info["proj"])
    item["td_id"] = info["id"]
    item["td_list"] = info["list"]
    item["td_wk"] = info["list"] == "wp"
    item["td_proj_label"] = proj["label"] if proj else info["proj"][:6]
    item["td_proj_cls"] = proj["cls"] if proj else "pp-chip--gen"
    return item


_WORD_RE = re.compile(r"[a-z0-9']+")


def similar(a: str, b: str, threshold: float = 0.5) -> bool:
    """Token-Jaccard similarity — is a text edit a wording tweak (True) or a
    slot reused for a different task (False)?

    Used to decide whether a manually edited line keeps its Todoist link.
    Keeping a link on a genuine replacement would make the next sync mutate
    the WRONG Todoist task, so ties break toward dropping (the sync re-links
    fuzzily or creates; safety wins).
    """
    ta = set(_WORD_RE.findall(a.lower()))
    tb = set(_WORD_RE.findall(b.lower()))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold
