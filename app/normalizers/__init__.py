"""Normalizer package."""

from app.normalizers.deduplicate import deduplicate
from app.normalizers.kstartup import normalize_kstartup_row
from app.normalizers.sources import normalize_sources_row

__all__ = [
    "deduplicate",
    "normalize_kstartup_row",
    "normalize_sources_row",
]
