"""End-to-end MICE MVP: collect → normalize → summary → tests."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date

from app.io_utils import ensure_dir, project_root
from app.mice_collectors.registry import DEFAULT_MVP_SOURCES
from app.mice_collectors.runtime_status import compute_mvp_exit_code
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
    for name in ("SONGDO_OPENAPI_KEY", "GG_OPENAPI_KEY", "GG_KINTEX_OPENAPI_SERVICE"):
        import os

        log(f"env {name}: {'SET' if os.environ.get(name) else 'UNSET'}")

    pipeline_ok = True
    try:
        sources = list(DEFAULT_MVP_SOURCES)
        collect_manifest = run_collect(sources=sources, today=today, root=root)
        log("=== collect ===")
        log(json.dumps(collect_manifest, ensure_ascii=False, indent=2))

        norm = run_normalize(today=today, root=root)
        log("=== normalize ===")
        log(json.dumps(norm, ensure_ascii=False, indent=2))

        summary = run_summary(day=today.isoformat(), root=root)
        log("=== summary ===")
        log(json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        log(f"PIPELINE FAILURE: {exc}")
        pipeline_ok = False
        collect_manifest = {"sources": []}
        norm = {"integrity_ok": False}

    test_rc = 0
    if pipeline_ok and not args.skip_tests:
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

    exit_code = compute_mvp_exit_code(
        source_rows=collect_manifest.get("sources") or [],
        integrity_ok=bool(norm.get("integrity_ok")) if pipeline_ok else False,
        test_rc=test_rc,
        pipeline_ok=pipeline_ok,
    )

    log(f"=== MICE MVP done exit={exit_code} ===")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
