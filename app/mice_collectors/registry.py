"""Registered MICE collectors for collect/normalize runners."""
from __future__ import annotations

from app.mice_collectors.coex import CoexCollector
from app.mice_collectors.k_mice import KMiceCollector
from app.mice_collectors.kintex import KintexCollector
from app.mice_collectors.mice_or_kr import MiceOrKrCollector
from app.mice_collectors.mice_seoul_cvb import MiceSeoulCvbCollector
from app.mice_collectors.opendata_kintex_gg import OpendataKintexGgCollector
from app.mice_collectors.songdo_convenia import SongdoConveniaCollector

# Order: existing MVP sources first, then 1B-1B expansions
COLLECTOR_MAP = {
    "opendata_kintex_gg": OpendataKintexGgCollector,
    "songdo_convenia": SongdoConveniaCollector,
    "k_mice": KMiceCollector,
    "mice_or_kr": MiceOrKrCollector,
    "coex": CoexCollector,
    "kintex": KintexCollector,
    "mice_seoul_cvb": MiceSeoulCvbCollector,
}

DEFAULT_MVP_SOURCES = list(COLLECTOR_MAP.keys())
