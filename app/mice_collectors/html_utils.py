"""Shared HTML parsing helpers for MICE SSR collectors."""
from __future__ import annotations

import re
from html import unescape
from typing import Any


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_tags(html: str | None) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub(" ", unescape(html))
    return _WS_RE.sub(" ", text).strip()


def attr(html: str, name: str) -> str | None:
    m = re.search(rf"""{name}=['"]([^'"]+)['"]""", html, re.I)
    return unescape(m.group(1)).strip() if m else None


def first_http_url(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"https?://[^\s<>\"']+", text)
    if not m:
        return None
    url = m.group(0).rstrip(").,;]")
    url = re.sub(r"^https?://https?://", "https://", url, flags=re.I)
    return url


def labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    """Extract '라벨: 값' from free text."""
    for lab in labels:
        m = re.search(rf"{re.escape(lab)}\s*[:：]\s*(.+?)(?:\n|$)", text)
        if m:
            val = strip_tags(m.group(1))
            if val and val not in {"-", "—"}:
                return val
    return None


def is_venue_not_host(name: str | None, venue_names: tuple[str, ...] = ()) -> bool:
    if not name:
        return False
    n = name.strip()
    defaults = ("KINTEX", "킨텍스", "COEX", "코엑스", "송도컨벤시아", "BEXCO", "벡스코")
    for v in venue_names + defaults:
        if n.casefold() == v.casefold():
            return True
    return False
