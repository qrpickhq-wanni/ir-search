"""Link notice → award → contract into lifecycle groups."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


def _org_key(rec: dict[str, Any]) -> str:
    return "||".join(
        [
            str(rec.get("ordering_organization") or "").strip(),
            str(rec.get("demand_organization") or "").strip(),
        ]
    )


def link_lifecycle(
    notices: list[dict[str, Any]],
    awards: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    *,
    pre_notices: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return representative lifecycle records + stats.

    Strong links only: notice_number (+ revision), contract→notice_number.
    Change/re-notices share lifecycle_group_id by base notice_number and are
    not duplicated as separate sales opportunities (highest revision kept as
    representative; history preserved on lifecycle_link_basis).
    """
    by_notice: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in notices:
        no = n.get("notice_number")
        if no:
            by_notice[str(no)].append(n)

    awards_by_notice: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in awards:
        no = a.get("notice_number")
        if no:
            awards_by_notice[str(no)].append(a)

    contracts_by_notice: dict[str, list[dict[str, Any]]] = defaultdict(list)
    orphan_contracts: list[dict[str, Any]] = []
    for c in contracts:
        no = c.get("notice_number")
        if no:
            contracts_by_notice[str(no)].append(c)
        else:
            orphan_contracts.append(c)

    linked: list[dict[str, Any]] = []
    stats = {
        "notice_to_award_links": 0,
        "award_to_contract_links": 0,
        "change_revision_groups": 0,
        "candidate_links": 0,
        "awardee_confirmed": 0,
        "contract_amount_confirmed": 0,
    }

    all_notice_nos = set(by_notice) | set(awards_by_notice) | set(contracts_by_notice)
    for no in sorted(all_notice_nos):
        revs = sorted(
            by_notice.get(no, []),
            key=lambda r: str(r.get("notice_revision") or "00"),
        )
        if len(revs) > 1:
            stats["change_revision_groups"] += 1
        base = deepcopy(revs[-1]) if revs else empty_from_award_or_contract(
            awards_by_notice.get(no, []), contracts_by_notice.get(no, []), no
        )
        if not base:
            continue

        basis = [f"notice_number:{no}"]
        if len(revs) > 1:
            basis.append(
                "revisions:" + ",".join(str(r.get("notice_revision")) for r in revs)
            )
            basis.append("representative_revision:" + str(base.get("notice_revision")))

        aw_list = awards_by_notice.get(no, [])
        if aw_list:
            stats["notice_to_award_links"] += 1
            aw = aw_list[0]
            basis.append("award_by_notice_number")
            base["procurement_stage"] = "AWARD_RESULT"
            base["opening_date"] = aw.get("opening_date") or base.get("opening_date")
            base["award_date"] = aw.get("award_date") or base.get("award_date")
            if aw.get("awardee_organizations"):
                base["awardee_organizations"] = list(aw["awardee_organizations"])
            if aw.get("contract_amount") and not base.get("contract_amount"):
                base["contract_amount"] = aw.get("contract_amount")
            if aw.get("detail_url") and not base.get("detail_url"):
                base["detail_url"] = aw.get("detail_url")

        ct_list = contracts_by_notice.get(no, [])
        if ct_list:
            if aw_list:
                stats["award_to_contract_links"] += 1
            basis.append("contract_by_notice_number")
            ct = ct_list[0]
            base["procurement_stage"] = "CONTRACT_RESULT"
            base["contract_date"] = ct.get("contract_date") or base.get("contract_date")
            if ct.get("contract_amount"):
                base["contract_amount"] = ct.get("contract_amount")
            if ct.get("awardee_organizations") and not base.get("awardee_organizations"):
                base["awardee_organizations"] = list(ct["awardee_organizations"])
            if ct.get("contract_method"):
                base["contract_method"] = ct.get("contract_method")

        if base.get("awardee_organizations"):
            stats["awardee_confirmed"] += 1
        if base.get("contract_amount"):
            stats["contract_amount_confirmed"] += 1

        base["lifecycle_group_id"] = f"g2b:lg:{no}"
        base["lifecycle_link_basis"] = basis
        base["lifecycle_candidate_links"] = []
        linked.append(base)

    # Orphan contracts → candidate only (no auto merge without notice number)
    for c in orphan_contracts:
        cand = deepcopy(c)
        cand["lifecycle_candidate_links"] = [
            {
                "type": "orphan_contract",
                "reason": "missing_notice_number",
                "confidence": "WEAK",
            }
        ]
        cand["lifecycle_link_basis"] = ["orphan_contract"]
        stats["candidate_links"] += 1
        linked.append(cand)

    # Pre-notices stay separate unless notice_number appears (rare in pre stage)
    for p in pre_notices or []:
        if not p.get("notice_number"):
            linked.append(deepcopy(p))

    return linked, stats


def empty_from_award_or_contract(
    awards: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    notice_no: str,
) -> dict[str, Any] | None:
    if awards:
        return deepcopy(awards[0])
    if contracts:
        return deepcopy(contracts[0])
    return None
