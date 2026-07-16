"""Tests for MICE deduplication policy."""
from __future__ import annotations

import unittest

from app.mice_normalizers.deduplicate import deduplicate_events
from app.mice_normalizers.schema import new_event


def _ev(**kw):
    base = new_event(
        event_id=kw.pop("event_id", "e1"),
        source_id=kw.get("source_id", "k_mice"),
        source_event_id=kw.get("source_event_id"),
        title=kw.get("title", "행사"),
        title_normalized=kw.get("title_normalized", "행사"),
        start_date=kw.get("start_date", "2026-08-01"),
        venue_normalized=kw.get("venue_normalized", "킨텍스"),
        official_event_url=kw.get("official_event_url"),
        source_occurrences=kw.get(
            "source_occurrences",
            [{"source_id": kw.get("source_id", "k_mice"), "source_event_id": kw.get("source_event_id")}],
        ),
    )
    base.update(kw)
    return base


class MiceDedupTests(unittest.TestCase):
    def test_different_edition_not_merged(self):
        a = _ev(event_id="a", title="월드쇼", title_normalized="월드쇼", start_date="2025-06-01", source_event_id="1")
        b = _ev(event_id="b", title="월드쇼", title_normalized="월드쇼", start_date="2026-06-01", source_event_id="2")
        reps, log = deduplicate_events([a, b])
        self.assertEqual(len(reps), 2)
        self.assertTrue(any(x.get("relation") == "CANDIDATE" for x in log))

    def test_same_title_date_venue_merged(self):
        a = _ev(event_id="a", source_event_id="10", source_id="k_mice")
        b = _ev(event_id="b", source_event_id="99", source_id="songdo_convenia")
        reps, log = deduplicate_events([a, b])
        self.assertEqual(len(reps), 1)
        self.assertEqual(len(reps[0]["source_occurrences"]), 2)
        self.assertTrue(any(x.get("relation") == "CONFIRMED_MERGE" for x in log))

    def test_same_official_url_merged(self):
        a = _ev(
            event_id="a",
            title_normalized="알파",
            start_date="2026-01-01",
            venue_normalized="a",
            official_event_url="https://example.com/evt",
            source_event_id="1",
        )
        b = _ev(
            event_id="b",
            title_normalized="베타",
            start_date="2026-02-01",
            venue_normalized="b",
            official_event_url="https://example.com/evt",
            source_event_id="2",
            source_id="songdo_convenia",
        )
        reps, _ = deduplicate_events([a, b])
        self.assertEqual(len(reps), 1)


if __name__ == "__main__":
    unittest.main()
