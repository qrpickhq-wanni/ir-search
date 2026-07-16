"""Normalize raw G2B OpenAPI rows into procurement opportunity records."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.normalizers.text_utils import normalize_title
from app.procurement_normalizers.schema import empty_procurement_record


_YEAR_RE = re.compile(r"(19|20)\d{2}")


def strip_year_title(title: str | None) -> str:
    t = normalize_title(title) or ""
    t = _YEAR_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _parse_dt(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _money(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    return str(raw).strip()


def _urls(*vals: Any) -> list[str]:
    out: list[str] = []
    for v in vals:
        if not v:
            continue
        s = str(v).strip()
        if s.startswith("http") and s not in out:
            out.append(s)
    return out


def normalize_bid_notice(row: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    rec = empty_procurement_record()
    no = str(row.get("bidNtceNo") or "").strip()
    ord_ = str(row.get("bidNtceOrd") or "00").strip() or "00"
    title = row.get("bidNtceNm")
    rec["procurement_id"] = f"g2b:notice:{no}:{ord_}" if no else None
    rec["lifecycle_group_id"] = f"g2b:lg:{no}" if no else None
    rec["notice_number"] = no or None
    rec["notice_revision"] = ord_
    rec["original_notice_number"] = str(row.get("reNtceYn") and row.get("bidNtceNo") or no) or None
    # Change notices often include refrnc / related fields when present
    if row.get("ntceKindNm"):
        rec["procurement_status"] = str(row.get("ntceKindNm"))
    rec["procurement_stage"] = "BID_NOTICE"
    rec["title"] = title
    rec["title_normalized"] = normalize_title(title)
    rec["ordering_organization"] = row.get("ntceInsttNm") or row.get("orderInsttNm")
    rec["demand_organization"] = row.get("dminsttNm")
    rec["announcement_date"] = _parse_dt(row.get("bidNtceDate") or row.get("rgstDt") or row.get("bidNtceDt"))
    rec["proposal_deadline"] = _parse_dt(row.get("bidClseDate") or row.get("bidClseDt"))
    rec["estimated_amount"] = _money(row.get("asignBdgtAmt") or row.get("presmptPrce"))
    rec["base_amount"] = _money(row.get("bssamt"))
    detail = row.get("bidNtceDtlUrl") or row.get("bidNtceUrl")
    rec["detail_url"] = detail
    rec["source_url"] = detail or row.get("_source_url")
    atts = _urls(
        row.get("ntceSpecDocUrl1"),
        row.get("ntceSpecDocUrl2"),
        row.get("ntceSpecDocUrl3"),
        row.get("ntceSpecDocUrl4"),
        row.get("ntceSpecDocUrl5"),
    )
    rec["attachment_urls"] = atts
    rfp: list[str] = []
    for i in range(1, 6):
        name = str(row.get(f"ntceSpecFileNm{i}") or "")
        url = row.get(f"ntceSpecDocUrl{i}")
        if url and ("제안" in name or "RFP" in name.upper() or "과업" in name):
            rfp.append(str(url))
    rec["request_for_proposal_urls"] = rfp or list(atts)
    rec["public_contact_department"] = row.get("ntceInsttOfclDeptNm") or row.get("ofclDeptNm")
    rec["public_contact_name"] = row.get("ntceInsttOfclNm") or row.get("ofclNm")
    rec["public_contact_email"] = row.get("ntceInsttOfclEmailAdrs") or row.get("ofclEmailAdrs")
    rec["public_contact_phone"] = row.get("ntceInsttOfclTel") or row.get("ofclTelNo")
    rec["contract_method"] = row.get("cntrctCnclsMthdNm")
    rec["collected_at"] = row.get("_collected_at")
    rec["raw_file"] = "g2b_bid_notices.jsonl"
    if today and rec.get("proposal_deadline"):
        try:
            dl = date.fromisoformat(str(rec["proposal_deadline"])[:10])
            rec["days_to_deadline"] = (dl - today).days
            rec["dday"] = (dl - today).days
            rec["deadline"] = rec["proposal_deadline"]
        except ValueError:
            pass
    # Fields for bid_assessment haystack compatibility
    rec["organization"] = rec["ordering_organization"] or rec["demand_organization"]
    rec["url"] = rec["detail_url"] or rec["source_url"]
    rec["detail_verification_status"] = "NOT_FETCHED"
    return rec


def normalize_pre_notice(row: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    rec = empty_procurement_record()
    no = str(row.get("bfSpecRgstNo") or "").strip()
    title = row.get("prdctClsfcNoNm") or row.get("bidNtceNm") or row.get("orderPlanNm")
    rec["procurement_id"] = f"g2b:pre:{no}" if no else None
    rec["lifecycle_group_id"] = f"g2b:prelg:{no}" if no else None
    rec["notice_number"] = no or None
    rec["procurement_stage"] = "PRE_NOTICE"
    rec["title"] = title
    rec["title_normalized"] = normalize_title(title)
    rec["ordering_organization"] = row.get("orderInsttNm") or row.get("ntceInsttNm")
    rec["demand_organization"] = row.get("rludInsttNm") or row.get("dminsttNm")
    rec["announcement_date"] = _parse_dt(row.get("rgstDt") or row.get("bfSpecRgstDt"))
    rec["proposal_deadline"] = _parse_dt(row.get("opninRgstClseDt"))
    rec["estimated_amount"] = _money(row.get("asignBdgtAmt"))
    atts = _urls(
        row.get("specDocFileUrl1"),
        row.get("specDocFileUrl2"),
        row.get("specDocFileUrl3"),
        row.get("specDocFileUrl4"),
        row.get("specDocFileUrl5"),
    )
    rec["attachment_urls"] = atts
    rec["request_for_proposal_urls"] = list(atts)
    rec["detail_url"] = row.get("_source_url")
    rec["source_url"] = row.get("_source_url")
    rec["collected_at"] = row.get("_collected_at")
    rec["raw_file"] = "g2b_pre_notices.jsonl"
    rec["organization"] = rec["ordering_organization"]
    rec["url"] = rec["source_url"]
    rec["detail_verification_status"] = "NOT_FETCHED"
    return rec


def normalize_award_result(row: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    rec = empty_procurement_record()
    no = str(row.get("bidNtceNo") or "").strip()
    ord_ = str(row.get("bidNtceOrd") or "00").strip() or "00"
    title = row.get("bidNtceNm")
    rec["procurement_id"] = f"g2b:award:{no}:{ord_}" if no else None
    rec["lifecycle_group_id"] = f"g2b:lg:{no}" if no else None
    rec["notice_number"] = no or None
    rec["notice_revision"] = ord_
    rec["procurement_stage"] = "AWARD_RESULT"
    rec["title"] = title
    rec["title_normalized"] = normalize_title(title)
    rec["ordering_organization"] = row.get("ntceInsttNm") or row.get("orderInsttNm")
    rec["demand_organization"] = row.get("dminsttNm")
    rec["opening_date"] = _parse_dt(row.get("opengDate") or row.get("opengDt"))
    rec["award_date"] = _parse_dt(row.get("fnlSucsfDate") or row.get("opengDate") or row.get("opengDt"))
    awardee = row.get("bidwinnrNm") or row.get("prcbdrBiznoeNm")
    if awardee:
        rec["awardee_organizations"] = [str(awardee)]
    rec["contract_amount"] = _money(row.get("sucsfbidAmt") or row.get("sumAmt"))
    rec["detail_url"] = row.get("bidNtceDtlUrl")
    rec["source_url"] = rec["detail_url"] or row.get("_source_url")
    rec["collected_at"] = row.get("_collected_at")
    rec["raw_file"] = "g2b_award_results.jsonl"
    rec["organization"] = rec["ordering_organization"]
    rec["url"] = rec["source_url"]
    rec["detail_verification_status"] = "NOT_FETCHED"
    return rec


def normalize_contract_result(row: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    rec = empty_procurement_record()
    cno = str(row.get("untyCntrctNo") or row.get("cntrctNo") or "").strip()
    no = str(row.get("bidNtceNo") or "").strip()
    title = row.get("cntrctNm") or row.get("bidNtceNm")
    rec["procurement_id"] = f"g2b:contract:{cno}" if cno else (f"g2b:contract-notice:{no}" if no else None)
    rec["lifecycle_group_id"] = f"g2b:lg:{no}" if no else (f"g2b:clg:{cno}" if cno else None)
    rec["notice_number"] = no or None
    rec["procurement_stage"] = "CONTRACT_RESULT"
    rec["title"] = title
    rec["title_normalized"] = normalize_title(title)
    rec["ordering_organization"] = row.get("cntrctInsttNm") or row.get("ntceInsttNm")
    rec["demand_organization"] = row.get("dminsttNm")
    rec["contract_date"] = _parse_dt(row.get("cntrctCnclsDate") or row.get("cntrctDate"))
    rec["contract_amount"] = _money(row.get("totCntrctAmt") or row.get("cntrctAmt"))
    awardee = row.get("corpNm") or row.get("bidwinnrNm")
    if awardee:
        rec["awardee_organizations"] = [str(awardee)]
    rec["contract_method"] = row.get("cntrctMthdNm") or row.get("cntrctCnclsMthdNm")
    rec["source_url"] = row.get("_source_url")
    rec["detail_url"] = row.get("_source_url")
    rec["collected_at"] = row.get("_collected_at")
    rec["raw_file"] = "g2b_contract_results.jsonl"
    rec["organization"] = rec["ordering_organization"]
    rec["url"] = rec["source_url"]
    rec["detail_verification_status"] = "NOT_FETCHED"
    return rec
