"""End-to-end MICE MVP: collect → normalize → summary → tests."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from app.io_utils import ensure_dir, project_root
from app.run_mice_collect import run_collect
from app.run_mice_normalize import run_normalize
from app.run_mice_summary import run_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MICE MVP pipeline")
    parser.add_argument("--today", default=None)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)

    root = project_root()
    today = date.fromisoformat(args.today) if args.today else date.today()
    log_dir = ensure_dir(root / "logs")
    log_path = log_dir / f"{today.isoformat()}_mice_mvp.log"

    def log(msg: str) -> None:
        line = msg if msg.endswith("\n") else msg + "\n"
        print(msg)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    log(f"=== MICE MVP start {today.isoformat()} ===")
    # Env checklist (do not print secret values)
    for name in ("SONGDO_OPENAPI_KEY", "GG_OPENAPI_KEY", "GG_KINTEX_OPENAPI_SERVICE"):
        import os

        log(f"env {name}: {'SET' if os.environ.get(name) else 'UNSET'}")

    sources = ["opendata_kintex_gg", "songdo_convenia", "k_mice"]
    collect_manifest = run_collect(sources=sources, today=today, root=root)
    log("=== collect ===")
    log(json.dumps(collect_manifest, ensure_ascii=False, indent=2))

    norm = run_normalize(today=today, root=root)
    log("=== normalize ===")
    log(json.dumps(norm, ensure_ascii=False, indent=2))

    summary = run_summary(day=today.isoformat(), root=root)
    log("=== summary ===")
    log(json.dumps(summary, ensure_ascii=False, indent=2))

    test_rc = 0
    if not args.skip_tests:
        log("=== tests ===")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_mice_*.py", "-v"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        log(proc.stdout)
        log(proc.stderr)
        test_rc = proc.returncode
        log(f"tests exit={test_rc}")

    statuses = [s.get("status") for s in collect_manifest.get("sources") or []]
    if test_rc != 0:
        exit_code = 1
    elif all(s == "OK" for s in statuses) and norm.get("integrity_ok"):
        exit_code = 0
    elif any(s in {"OK", "PARTIAL"} for s in statuses):
        exit_code = 2
    else:
        exit_code = 1

    log(f"=== MICE MVP done exit={exit_code} ===")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
