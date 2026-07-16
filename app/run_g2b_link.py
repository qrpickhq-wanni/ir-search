"""Link G2B lifecycle, previous cycles, MICE events; apply sales windows."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, load_yaml, project_root, read_jsonl, write_jsonl
from app.procurement_normalizers.event_linker import link_events
from app.procurement_normalizers.lifecycle_linker import link_lifecycle
from app.procurement_normalizers.previous_cycle_matcher import match_previous_cycles
from app.procurement_normalizers.sales_window import apply_sales_windows


def _latest_mice_events() -> list[dict]:
    root = project_root() / "data" / "normalized" / "mice"
    if not root.exists():
        return []
    days = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not days:
        return []
    path = days[-1] / "events.jsonl"
    if not path.exists():
        # try alternate names
        for cand in days[-1].glob("*.jsonl"):
            return read_jsonl(cand)
        return []
    return read_jsonl(path)


def run_g2b_link(
    *,
    normalized_dir: Path,
    out_dir: Path | None = None,
    today: date | None = None,
    config: dict | None = None,
) -> dict:
    today = today or date.today()
    cfg = config or load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
    bid_rules = load_yaml(project_root() / "config" / "bid-assessment-rules.yaml")
    profile = load_yaml(project_root() / "config" / "qrpick-profile.yaml")
    out_dir = out_dir or ensure_dir(normalized_dir)
    ensure_dir(out_dir)

    pre = read_jsonl(normalized_dir / "pre_notices.jsonl") if (normalized_dir / "pre_notices.jsonl").exists() else []
    notices = read_jsonl(normalized_dir / "bid_notices.jsonl") if (normalized_dir / "bid_notices.jsonl").exists() else []
    awards = read_jsonl(normalized_dir / "award_results.jsonl") if (normalized_dir / "award_results.jsonl").exists() else []
    contracts = (
        read_jsonl(normalized_dir / "contract_results.jsonl")
        if (normalized_dir / "contract_results.jsonl").exists()
        else []
    )

    linked, life_stats = link_lifecycle(notices, awards, contracts, pre_notices=pre)

    # Previous cycle: use awards+contracts+older notices as history pool
    history = [r for r in linked if r.get("procurement_stage") in {"AWARD_RESULT", "CONTRACT_RESULT"}]
    history += notices + awards + contracts
    with_prev, prev_stats = match_previous_cycles(linked, history, today=today)

    events = _latest_mice_events()
    with_events, event_stats = link_events(with_prev, events)

    scored = [
        apply_sales_windows(r, config=cfg, bid_rules=bid_rules, profile=profile, today=today)
        for r in with_events
    ]

    write_jsonl(out_dir / "procurements.jsonl", scored)
    stats = {
        "normalized_dir": str(normalized_dir),
        "procurement_count": len(scored),
        "lifecycle": life_stats,
        "previous_cycle": prev_stats,
        "event_links": event_stats,
        "mice_events_available": len(events),
    }
    (out_dir / "link_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--normalized-dir", required=True)
    ap.add_argument("--today", default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    stats = run_g2b_link(normalized_dir=Path(args.normalized_dir), today=today)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
