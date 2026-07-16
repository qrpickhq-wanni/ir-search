"""Conservative MICE event deduplication."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _norm_url(url: str | None) -> str | None:
    if not url:
        return None
    u = str(url).strip().rstrip("/")
    return u or None


def is_confirmed_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    url_a = _norm_url(a.get("official_event_url"))
    url_b = _norm_url(b.get("official_event_url"))
    if url_a and url_b and url_a == url_b:
        return True
    if (
        a.get("source_id")
        and a.get("source_id") == b.get("source_id")
        and a.get("source_event_id")
        and a.get("source_event_id") == b.get("source_event_id")
    ):
        return True
    if (
        a.get("title_normalized")
        and a.get("title_normalized") == b.get("title_normalized")
        and a.get("start_date")
        and a.get("start_date") == b.get("start_date")
        and a.get("venue_normalized")
        and a.get("venue_normalized") == b.get("venue_normalized")
    ):
        return True
    return False


def is_candidate_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if is_confirmed_duplicate(a, b):
        return False
    if not a.get("title_normalized") or a.get("title_normalized") != b.get("title_normalized"):
        return False
    # Same title + start, but venue/org unclear — candidate only
    if a.get("start_date") and a.get("start_date") == b.get("start_date"):
        return True
    # Same title different year/edition — candidate note, no merge
    if a.get("start_date") and b.get("start_date"):
        if a["start_date"][:4] != b["start_date"][:4]:
            return True
    return False


def _merge_list(a: list[Any], b: list[Any]) -> list[Any]:
    out = list(a or [])
    for x in b or []:
        if x not in out:
            out.append(x)
    return out


def _richness(e: dict[str, Any]) -> int:
    score = 0
    for k in (
        "official_event_url",
        "contact_email",
        "contact_phone",
        "venue_name",
        "host_organizations",
        "organizer_organizations",
        "description_summary",
        "title_en",
    ):
        v = e.get(k)
        if isinstance(v, list):
            score += len(v)
        elif v:
            score += 1
    score += len(e.get("source_occurrences") or [])
    return score


def _merge_occurrences(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve all occurrence rows; only drop exact same tracking key."""
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for occ in list(a or []) + list(b or []):
        key = (
            str(occ.get("source_id") or ""),
            str(occ.get("source_event_id") or ""),
            str(occ.get("source_url") or ""),
            str(occ.get("collected_at") or ""),
            str(occ.get("occurrence_uid") or ""),
        )
        if key in seen and any(key):
            # Allow collapse only when a non-empty uid/event_id exists; otherwise keep
            if key[1] or key[4]:
                continue
        # Distinct rows without event_id: keep all by using list position in seen via object identity fallback
        if not key[1] and not key[4]:
            key = key + (str(len(out)),)
        if key in seen:
            continue
        seen.add(key)
        out.append(occ)
    return out


def _merge_events(primary: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(primary)
    for k, v in other.items():
        if k in {"event_id", "canonical_event_id", "duplicate_group_id", "duplicate_count"}:
            continue
        if k == "source_occurrences":
            out[k] = _merge_occurrences(out.get(k) or [], v or [])
            continue
        if k in {"sales_signal_types", "sales_signal_basis", "qrpick_service_matches"}:
            out[k] = _merge_list(out.get(k) or [], v or [])
            continue
        if isinstance(v, list):
            out[k] = _merge_list(out.get(k) or [], v)
            continue
        if (out.get(k) in (None, "", [], False)) and v not in (None, "", []):
            out[k] = v
    rank = {"DIRECT_OPPORTUNITY": 0, "CONTACTABLE": 1, "RESEARCH": 2, "WATCH": 3, "NONE": 4}
    if rank.get(other.get("sales_readiness") or "NONE", 9) < rank.get(out.get("sales_readiness") or "NONE", 9):
        out["sales_readiness"] = other.get("sales_readiness")
        if other.get("suggested_sales_action"):
            out["suggested_sales_action"] = other.get("suggested_sales_action")
    out["duplicate_count"] = len(out.get("source_occurrences") or [])
    return out


def deduplicate_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (representatives, duplicate_log). Confirmed merges only."""
    if not events:
        return [], []

    n = len(events)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    dup_log: list[dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = events[i], events[j]
            if is_confirmed_duplicate(a, b):
                union(i, j)
                dup_log.append(
                    {
                        "relation": "CONFIRMED_MERGE",
                        "left_event_id": a.get("event_id"),
                        "right_event_id": b.get("event_id"),
                        "reason": _confirm_reason(a, b),
                    }
                )
            elif is_candidate_duplicate(a, b):
                dup_log.append(
                    {
                        "relation": "CANDIDATE",
                        "left_event_id": a.get("event_id"),
                        "right_event_id": b.get("event_id"),
                        "reason": "title_start_or_year_ambiguity",
                        "left_title": a.get("title"),
                        "right_title": b.get("title"),
                        "left_start": a.get("start_date"),
                        "right_start": b.get("start_date"),
                    }
                )

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    reps: list[dict[str, Any]] = []
    for root, idxs in groups.items():
        members = [events[i] for i in idxs]
        members.sort(key=_richness, reverse=True)
        merged = deepcopy(members[0])
        for other in members[1:]:
            merged = _merge_events(merged, other)
        gid = f"dup:{merged.get('event_id')}"
        merged["duplicate_group_id"] = gid if len(members) > 1 else merged.get("event_id")
        merged["duplicate_count"] = len(merged.get("source_occurrences") or [])
        # Prefer richest event_id as canonical
        merged["canonical_event_id"] = merged.get("event_id")
        reps.append(merged)

    return reps, dup_log


def _confirm_reason(a: dict[str, Any], b: dict[str, Any]) -> str:
    if _norm_url(a.get("official_event_url")) and _norm_url(a.get("official_event_url")) == _norm_url(
        b.get("official_event_url")
    ):
        return "same_official_event_url"
    if (
        a.get("source_id") == b.get("source_id")
        and a.get("source_event_id")
        and a.get("source_event_id") == b.get("source_event_id")
    ):
        return "same_source_id_and_source_event_id"
    return "same_title_normalized_start_date_venue_normalized"
