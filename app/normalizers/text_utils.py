"""Text normalization helpers for comparison keys (never mutate original titles)."""
from __future__ import annotations

import re
import unicodedata


_QUOTE_MAP = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "＇": "'",
        "＂": '"',
        "「": '"',
        "」": '"',
        "『": '"',
        "』": '"',
    }
)

_SPACE_RE = re.compile(r"\s+")
_PAREN_RE = re.compile(r"[()\[\]{}（）【】]")
_PUNCT_RE = re.compile(r"[·ㆍ~/\\|,_=+\-–—:：;；!?？。.…\*#@]+")

# Soften common announcement suffixes for duplicate comparison only
_SUFFIX_RE = re.compile(
    r"(모집\s*공고|신규\s*모집\s*공고|모집\s*안내|공고|안내|공모)$"
)

_ORG_PREFIX_RE = re.compile(
    r"^(재단법인|사단법인|주식회사|유한회사|\(재\)|\(사\)|\(주\)|㈜)\s*"
)
_ORG_SUFFIX_RE = re.compile(
    r"\s*(재단법인|사단법인|주식회사|유한회사|\(재\)|\(사\)|\(주\)|㈜)\s*$"
)


def collapse_whitespace(text: str | None) -> str:
    if not text:
        return ""
    return _SPACE_RE.sub(" ", str(text).strip())


def normalize_title(text: str | None) -> str:
    """Comparison-oriented title key. Original title must remain unchanged elsewhere."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = s.translate(_QUOTE_MAP)
    s = re.sub(r"[\"'`]", " ", s)
    s = collapse_whitespace(s)
    s = _PAREN_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    s = collapse_whitespace(s)
    soft = _SUFFIX_RE.sub("", s).strip()
    soft = collapse_whitespace(soft)
    return soft.casefold() if soft else s.casefold()


def normalize_organization(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = collapse_whitespace(s)
    s = _ORG_PREFIX_RE.sub("", s)
    s = _ORG_SUFFIX_RE.sub("", s)
    s = _PAREN_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    s = collapse_whitespace(s)
    return s.casefold()


def haystack(*parts: str | None) -> str:
    return " ".join(collapse_whitespace(p) for p in parts if p).casefold()
