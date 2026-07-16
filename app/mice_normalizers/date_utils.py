"""Date parsing for MICE events (single day, ranges, year-boundary, TBD)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.normalizers.date_utils import parse_date as parse_iso_fragment


_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_RANGE_SPLIT = re.compile(r"\s*(?:~|～|〜|-|–|—|～|부터|까지|to)\s*", re.I)
_YMD = re.compile(
    r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]?\s*(\d{1,2}|미정|00)?\s*일?"
)
_YM_TBD = re.compile(r"(\d{4})\s*[.\-/년]?\s*(\d{1,2})\s*[.\-/월]?\s*(?:미정|00)?")


def _safe(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_mice_date(value: str | None) -> str | None:
    """Parse a single date token to YYYY-MM-DD. TBD day → None (keep date_text)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in {"-", "—", "미정"}:
        return None
    m = _COMPACT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if d == 0:
            return None
        return _safe(y, mo, d)
    # Hidden K-MICE values like 202607미정
    m2 = re.match(r"^(\d{4})(\d{2})미정$", s)
    if m2:
        return None
    m3 = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m3:
        return _safe(int(m3.group(1)), int(m3.group(2)), int(m3.group(3)))
    # Reject pure TBD month spans without day for single-date parse
    if "미정" in s and not re.search(r"\d{1,2}\s*일", s):
        # Still try full parse_date below for forms like 2026.07.01
        pass
    frag = parse_iso_fragment(s)
    if frag:
        return frag
    m = _YMD.search(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        day_raw = m.group(3)
        if day_raw in (None, "미정", "00"):
            return None
        return _safe(y, mo, int(day_raw))
    return None


def parse_mice_date_range(
    start_raw: str | None = None,
    end_raw: str | None = None,
    date_text: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return (start_iso, end_iso, preserved_date_text)."""
    preserved = (date_text or "").strip() or None
    start = parse_mice_date(start_raw)
    end = parse_mice_date(end_raw)

    text = date_text or ""
    if (not start or not end) and text:
        # Split range
        parts = _RANGE_SPLIT.split(text.strip())
        parts = [p.strip() for p in parts if p and p.strip()]
        if len(parts) >= 2:
            left, right = parts[0], parts[1]
            if not start:
                start = parse_mice_date(left)
            if not end:
                # Prefer year inheritance when the right token has no 4-digit year
                if start and not re.search(r"\d{4}", right):
                    end = _complete_end(start, right)
                else:
                    end = parse_mice_date(right)
            if start and not end:
                end = _complete_end(start, right)
            if end and not start:
                start = parse_mice_date(left)
        elif len(parts) == 1 and not start:
            start = parse_mice_date(parts[0])
            end = start

    if start and not end:
        end = start
    if end and not start:
        start = end

    if not preserved:
        if start and end and start != end:
            preserved = f"{start} ~ {end}"
        elif start:
            preserved = start

    return start, end, preserved


def _complete_end(start_iso: str, end_token: str) -> str | None:
    direct = parse_mice_date(end_token)
    if direct:
        return direct
    m = re.search(r"(\d{1,2})\s*[.\-/월]\s*(\d{1,2})", end_token)
    if not m:
        return None
    y = int(start_iso[:4])
    mo, d = int(m.group(1)), int(m.group(2))
    cand = _safe(y, mo, d)
    if cand and cand < start_iso:
        cand = _safe(y + 1, mo, d)
    return cand


def in_collection_window(
    start_iso: str | None,
    end_iso: str | None,
    *,
    today: date,
    past_days: int,
    future_days: int,
) -> bool:
    """Keep events overlapping [today-past, today+future]. Unknown dates kept."""
    win_start = today - timedelta(days=past_days)
    win_end = today + timedelta(days=future_days)
    if not start_iso and not end_iso:
        return True
    try:
        s = date.fromisoformat(start_iso) if start_iso else None
        e = date.fromisoformat(end_iso) if end_iso else s
    except ValueError:
        return True
    if s is None and e is None:
        return True
    if s is None:
        s = e
    if e is None:
        e = s
    assert s is not None and e is not None
    return e >= win_start and s <= win_end
