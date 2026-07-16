"""Link procurement records to existing normalized MICE events (conservative)."""
from __future__ import annotations

from typing import Any

from app.normalizers.text_utils import normalize_title


def link_events(
    procurements: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Attach matched_event_ids only on strong evidence.

    Strong: normalized event name contained in title (or vice versa) AND
    (same year if both have dates) AND (organizer overlap when both present).
    Otherwise leave empty and do not auto-merge.
    """
    stats = {"linked": 0, "skipped_ambiguous": 0}
    event_index: list[tuple[str, dict[str, Any]]] = []
    for ev in events:
        name = normalize_title(ev.get("event_name") or ev.get("title") or "")
        if name and len(name) >= 4:
            event_index.append((name, ev))

    out: list[dict[str, Any]] = []
    for rec in procurements:
        title = normalize_title(rec.get("title") or "") or ""
        annotated = dict(rec)
        matches: list[dict[str, Any]] = []
        basis: list[str] = []
        for ename, ev in event_index:
            if ename in title or (title and title in ename):
                year_ok = True
                ev_date = str(ev.get("start_date") or ev.get("event_date") or "")[:4]
                ann = str(rec.get("announcement_date") or rec.get("proposal_deadline") or "")[:4]
                if ev_date.isdigit() and ann.isdigit() and abs(int(ev_date) - int(ann)) > 1:
                    year_ok = False
                org_ok = True
                ev_org = str(ev.get("organizer") or ev.get("host_organization") or "").strip()
                rec_org = str(
                    rec.get("ordering_organization") or rec.get("demand_organization") or ""
                ).strip()
                if ev_org and rec_org and ev_org not in rec_org and rec_org not in ev_org:
                    # soft: still allow name match but mark weaker
                    org_ok = False
                if year_ok and (org_ok or not ev_org or not rec_org):
                    eid = ev.get("event_id") or ev.get("canonical_id") or ev.get("source_id")
                    if eid:
                        matches.append({"event_id": eid, "event_name": ev.get("event_name") or ev.get("title")})
                        basis.append(f"title_contains_event:{ename[:40]}")
                        if org_ok and ev_org:
                            basis.append("organizer_overlap")
                        if ev.get("start_date") or ev.get("event_date"):
                            annotated["event_date"] = ev.get("start_date") or ev.get("event_date")
                            annotated["event_name"] = ev.get("event_name") or ev.get("title")
        if len(matches) == 1:
            annotated["matched_event_ids"] = [matches[0]["event_id"]]
            annotated["matched_event_link_basis"] = basis
            annotated["registration_open_status"] = "UNKNOWN"
            stats["linked"] += 1
        elif len(matches) > 1:
            annotated["matched_event_ids"] = []
            annotated["matched_event_link_basis"] = ["ambiguous_multiple_events"]
            annotated["lifecycle_candidate_links"] = list(
                annotated.get("lifecycle_candidate_links") or []
            ) + [{"type": "event_link", "candidates": matches, "confidence": "WEAK"}]
            annotated["registration_open_status"] = "UNKNOWN"
            stats["skipped_ambiguous"] += 1
        else:
            annotated["matched_event_ids"] = annotated.get("matched_event_ids") or []
            annotated["registration_open_status"] = "UNKNOWN"
        # Never assert system supplier from list data
        annotated["system_supplier_status"] = "UNKNOWN"
        out.append(annotated)
    return out, stats
