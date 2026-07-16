"""Text helpers for MICE normalization (comparison only — originals preserved)."""
from __future__ import annotations

import re
import unicodedata

from app.normalizers.text_utils import collapse_whitespace, normalize_organization, normalize_title

__all__ = [
    "collapse_whitespace",
    "normalize_title",
    "normalize_organization",
    "normalize_venue",
    "split_org_list",
    "extract_email",
    "extract_phone",
]


_VENUE_RE = re.compile(r"\s+")


def normalize_venue(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = collapse_whitespace(s)
    if s in {"-", "—", "N/A", "n/a"}:
        return ""
    return s.casefold()


def split_org_list(text: str | None) -> list[str]:
    if not text:
        return []
    s = collapse_whitespace(str(text))
    if not s or s in {"-", "—"}:
        return []
    parts = re.split(r"[,/·]| 및 | & ", s)
    out: list[str] = []
    for p in parts:
        p = collapse_whitespace(p)
        if p and p not in out:
            out.append(p)
    return out


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\-().\s]{7,}\d)")


def extract_email(text: str | None) -> str | None:
    if not text:
        return None
    m = _EMAIL_RE.search(str(text))
    return m.group(0) if m else None


def extract_phone(text: str | None) -> str | None:
    if not text:
        return None
    # Prefer digit sequences looking like phone numbers; do not invent.
    s = str(text)
    if extract_email(s) and s.strip() == extract_email(s):
        return None
    m = _PHONE_RE.search(s)
    if not m:
        return None
    cand = collapse_whitespace(m.group(0))
    digits = re.sub(r"\D", "", cand)
    if len(digits) < 8:
        return None
    return cand
