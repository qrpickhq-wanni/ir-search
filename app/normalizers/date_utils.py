"""Date parsing helpers — preserve original strings separately."""
from __future__ import annotations

import re
from datetime import date, datetime


_YMD = re.compile(r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})")
_YMD_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_MD_SHORT = re.compile(r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def parse_date(value: str | None) -> str | None:
    """Return YYYY-MM-DD or None if not parseable."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _YMD.search(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _safe_iso(y, mo, d)
    m = _YMD_COMPACT.match(s)
    if m:
        return _safe_iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _MD_SHORT.search(s)
    if m:
        return _safe_iso(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _safe_iso(y: int, mo: int, d: int) -> str | None:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def dday_from_deadline(deadline_iso: str | None, today: date | None = None) -> str | None:
    if not deadline_iso:
        return None
    today = today or date.today()
    try:
        dl = date.fromisoformat(deadline_iso)
    except ValueError:
        return None
    delta = (dl - today).days
    if delta > 0:
        return f"D-{delta}"
    if delta == 0:
        return "D-Day"
    return f"D+{abs(delta)}"


def is_expired(deadline_iso: str | None, today: date | None = None) -> bool:
    if not deadline_iso:
        return False
    today = today or date.today()
    try:
        return date.fromisoformat(deadline_iso) < today
    except ValueError:
        return False
