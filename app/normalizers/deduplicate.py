"""Conservative duplicate detection and merging."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from app.normalizers.base import merge_fill_blanks, richness_score


def _occ_key(occ: dict[str, Any]) -> tuple[str, str]:
    return (str(occ.get("source") or ""), str(occ.get("source_id") or ""))


def _merge_occurrences(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {_occ_key(x) for x in a}
    out = list(a)
    for occ in b:
        k = _occ_key(occ)
        if k not in seen:
            out.append(occ)
            seen.add(k)
    return out


def _same_source_id(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("source") == b.get("source") and a.get("source_id") == b.get("source_id")


def _exact_high_prob(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a.get("title_normalized") or not b.get("title_normalized"):
        return False
    return (
        a["title_normalized"] == b["title_normalized"]
        and a.get("organization_normalized")
        and a.get("organization_normalized") == b.get("organization_normalized")
        and a.get("deadline")
        and a.get("deadline") == b.get("deadline")
    )


def _candidate_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a.get("title_normalized") or a["title_normalized"] != b.get("title_normalized"):
        return False
    org_match = (
        a.get("organization_normalized")
        and a.get("organization_normalized") == b.get("organization_normalized")
    )
    deadline_match = a.get("deadline") and a.get("deadline") == b.get("deadline")
    if not (org_match or deadline_match):
        return False
    url_a = a.get("url") or a.get("detail_url")
    url_b = b.get("url") or b.get("detail_url")
    url_same = bool(url_a and url_b and url_a == url_b)
    id_cross = a.get("source_id") and a.get("source_id") == b.get("source_id")
    return url_same or id_cross or (org_match and deadline_match)


def deduplicate(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (representatives, duplicate_log_rows).

    Auto-merge only: same source+source_id, or title+org+deadline exact match.
    Level-3 candidates are logged, not auto-merged.
    """
    if not records:
        return [], []

    n = len(records)
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

    # Index for faster exact matches
    by_source_id: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_title_org_deadline: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    by_title: dict[str, list[int]] = defaultdict(list)

    for i, rec in enumerate(records):
        by_source_id[(str(rec.get("source")), str(rec.get("source_id")))].append(i)
        t = rec.get("title_normalized") or ""
        o = rec.get("organization_normalized") or ""
        d = rec.get("deadline") or ""
        if t:
            by_title[t].append(i)
            if t and o and d:
                by_title_org_deadline[(t, o, d)].append(i)

    # 1) same source + source_id
    for idxs in by_source_id.values():
        if len(idxs) < 2:
            continue
        for j in idxs[1:]:
            union(idxs[0], j)

    # 2) title + org + deadline
    for idxs in by_title_org_deadline.values():
        if len(idxs) < 2:
            continue
        for j in idxs[1:]:
            union(idxs[0], j)

    # Build groups for auto-merge
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    duplicate_logs: list[dict[str, Any]] = []
    representatives: list[dict[str, Any]] = []
    merged_index_map: dict[int, str] = {}  # original index -> canonical_id

    for root, members in groups.items():
        member_recs = [records[i] for i in members]
        if len(members) == 1:
            rec = deepcopy(member_recs[0])
            rec["duplicate_group_id"] = None
            rec["duplicate_count"] = 1
            rec["canonical_id"] = rec["opportunity_id"]
            representatives.append(rec)
            merged_index_map[members[0]] = rec["canonical_id"]
            continue

        # Choose richest representative
        ranked = sorted(member_recs, key=richness_score, reverse=True)
        rep = deepcopy(ranked[0])
        all_conflicts: list[dict[str, Any]] = []
        for other in ranked[1:]:
            rep, conflicts = merge_fill_blanks(rep, other)
            all_conflicts.extend(conflicts)
            rep["source_occurrences"] = _merge_occurrences(
                rep.get("source_occurrences") or [],
                other.get("source_occurrences") or [],
            )

        group_id = f"dup:{rep['opportunity_id']}"
        rep["duplicate_group_id"] = group_id
        rep["duplicate_count"] = len(rep["source_occurrences"])
        rep["canonical_id"] = rep["opportunity_id"]
        representatives.append(rep)
        for i in members:
            merged_index_map[i] = rep["canonical_id"]

        duplicate_logs.append(
            {
                "type": "auto_merged",
                "duplicate_group_id": group_id,
                "canonical_id": rep["canonical_id"],
                "member_opportunity_ids": [records[i]["opportunity_id"] for i in members],
                "member_sources": [
                    {
                        "source": records[i].get("source"),
                        "source_id": records[i].get("source_id"),
                        "url": records[i].get("url"),
                        "raw_file": records[i].get("raw_file"),
                    }
                    for i in members
                ],
                "merge_reason": _merge_reason(member_recs),
                "conflicts": all_conflicts,
                "duplicate_count": rep["duplicate_count"],
            }
        )

    # 3) candidate duplicates across different auto-merge groups (no merge)
    # Compare representatives only, pairwise within same title_normalized buckets
    rep_by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in representatives:
        t = rec.get("title_normalized") or ""
        if t:
            rep_by_title[t].append(rec)

    seen_pairs: set[tuple[str, str]] = set()
    for title, bucket in rep_by_title.items():
        if len(bucket) < 2:
            continue
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                if a.get("canonical_id") == b.get("canonical_id"):
                    continue
                if not _candidate_duplicate(a, b):
                    # title already same; if org OR deadline match → candidate even without url/id
                    org_match = (
                        a.get("organization_normalized")
                        and a.get("organization_normalized") == b.get("organization_normalized")
                    )
                    deadline_match = a.get("deadline") and a.get("deadline") == b.get("deadline")
                    if not (org_match or deadline_match):
                        continue
                    # still require something beyond title alone: if only title matches with one of org/deadline
                    # user said: title exact AND (org OR deadline) AND (url same OR source_id cross OR ...)
                    # For title+org without deadline/url — treat as candidate (org matched)
                    pass
                # Prefer logging when title matches and (org or deadline)
                org_match = (
                    a.get("organization_normalized")
                    and a.get("organization_normalized") == b.get("organization_normalized")
                )
                deadline_match = a.get("deadline") and a.get("deadline") == b.get("deadline")
                if not (org_match or deadline_match):
                    continue
                # If already auto-merged condition (title+org+deadline), skip — should already be merged
                if org_match and deadline_match:
                    continue
                pair = tuple(sorted([a["canonical_id"], b["canonical_id"]]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                duplicate_logs.append(
                    {
                        "type": "candidate_duplicate",
                        "canonical_ids": list(pair),
                        "titles": [a.get("title"), b.get("title")],
                        "organizations": [a.get("organization"), b.get("organization")],
                        "deadlines": [a.get("deadline"), b.get("deadline")],
                        "urls": [a.get("url"), b.get("url")],
                        "sources": [
                            {"source": a.get("source"), "source_id": a.get("source_id")},
                            {"source": b.get("source"), "source_id": b.get("source_id")},
                        ],
                        "reason": "title_normalized match with org or deadline; not auto-merged",
                    }
                )

    representatives.sort(key=lambda r: (r.get("source") or "", r.get("source_id") or ""))
    return representatives, duplicate_logs


def _merge_reason(recs: list[dict[str, Any]]) -> str:
    sources = {(r.get("source"), r.get("source_id")) for r in recs}
    if len(sources) == 1:
        return "same_source_and_source_id"
    titles = {r.get("title_normalized") for r in recs}
    orgs = {r.get("organization_normalized") for r in recs}
    deadlines = {r.get("deadline") for r in recs}
    if len(titles) == 1 and len(orgs) == 1 and len(deadlines) == 1:
        return "title_org_deadline_exact"
    return "union_of_exact_rules"
