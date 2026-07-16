"""MICE collector runtime status and exit-code policy.

Statuses
-------
OK                 Normal collect with in-window records
OK_EMPTY           Reachable + parse OK, but zero in-window records
PARTIAL_EXPECTED   Documented limitation; run completed as expected
HOLD_CONFIGURED    Intentionally excluded (no HTTP / out of scope)
PARTIAL_UNEXPECTED Unexpected partial failure on an otherwise healthy source
FAILED             Source run substantially failed

Exit codes
----------
0  All active sources in {OK, OK_EMPTY, PARTIAL_EXPECTED}; HOLD_CONFIGURED ignored
2  Any active source is PARTIAL_UNEXPECTED or FAILED (other results may exist)
1  Pipeline/test failure or empty run with no evaluable sources that succeeded
"""
from __future__ import annotations

from typing import Any

from app.mice_collectors.base import CollectResult

OK = "OK"
OK_EMPTY = "OK_EMPTY"
PARTIAL_EXPECTED = "PARTIAL_EXPECTED"
HOLD_CONFIGURED = "HOLD_CONFIGURED"
PARTIAL_UNEXPECTED = "PARTIAL_UNEXPECTED"
FAILED = "FAILED"

EXIT_OK = frozenset({OK, OK_EMPTY, PARTIAL_EXPECTED})
EXIT_WARN = frozenset({PARTIAL_UNEXPECTED, FAILED})


def registry_runtime_defaults(entry: dict[str, Any] | None) -> dict[str, Any]:
    e = entry or {}
    enabled = e.get("runtime_enabled")
    if enabled is None:
        enabled = True
    expected = e.get("expected_runtime_status") or OK
    affects = e.get("failure_affects_exit_code")
    if affects is None:
        affects = expected != HOLD_CONFIGURED
    return {
        "runtime_enabled": bool(enabled),
        "expected_runtime_status": str(expected),
        "failure_affects_exit_code": bool(affects),
        "runtime_notes": str(e.get("runtime_notes") or ""),
    }


def status_is_expected(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if expected == PARTIAL_EXPECTED and actual in {OK, OK_EMPTY, PARTIAL_EXPECTED}:
        return True
    if expected == OK_EMPTY and actual in {OK, OK_EMPTY}:
        return True
    if expected == OK and actual in {OK, OK_EMPTY}:
        return True
    if expected == HOLD_CONFIGURED and actual == HOLD_CONFIGURED:
        return True
    return False


def warning_message(warnings: list[str] | None, errors: list[str] | None = None) -> str:
    parts = list(warnings or [])
    if errors:
        parts.extend(errors)
    return "; ".join(parts)[:1000]


def enrich_collect_result(result: CollectResult, entry: dict[str, Any] | None) -> CollectResult:
    rt = registry_runtime_defaults(entry)
    expected = rt["expected_runtime_status"]
    actual = result.status
    result.metadata = {
        **(result.metadata or {}),
        "runtime_status": actual,
        "expected_runtime_status": expected,
        "status_is_expected": status_is_expected(actual, expected),
        "failure_affects_exit_code": rt["failure_affects_exit_code"],
        "runtime_enabled": rt["runtime_enabled"],
        "runtime_notes": rt["runtime_notes"],
        "warning_message": warning_message(result.warnings, result.errors),
    }
    return result


def hold_configured_result(
    source_id: str,
    *,
    entry: dict[str, Any],
    raw_output_path: str | None = None,
) -> CollectResult:
    """HOLD_CONFIGURED without HTTP."""
    rt = registry_runtime_defaults(entry)
    notes = rt["runtime_notes"] or (
        "HOLD_CONFIGURED: runtime_enabled=false; no HTTP requests issued."
    )
    result = CollectResult(
        source_id=source_id,
        success=True,
        status=HOLD_CONFIGURED,
        fetched_count=0,
        parsed_count=0,
        error_count=0,
        raw_output_path=raw_output_path,
        errors=[],
        warnings=[notes],
        request_log=[],
        metadata={"implementation_status": HOLD_CONFIGURED},
    )
    return enrich_collect_result(result, entry)


def compute_collect_exit_code(source_rows: list[dict[str, Any]]) -> int:
    """Exit from collect source rows (HOLD_CONFIGURED does not degrade)."""
    if not source_rows:
        return 1

    statuses: list[str] = []
    for s in source_rows:
        st = s.get("status") or FAILED
        if st == HOLD_CONFIGURED:
            continue
        # Respect failure_affects_exit_code=false only for neutral/hold-like rows
        meta = s.get("metadata") or {}
        if meta.get("failure_affects_exit_code") is False and st in EXIT_OK | {HOLD_CONFIGURED}:
            continue
        statuses.append(st)

    if not statuses:
        return 0
    if any(st in EXIT_WARN for st in statuses):
        return 2
    if all(st in EXIT_OK for st in statuses):
        return 0
    return 1


def compute_mvp_exit_code(
    *,
    source_rows: list[dict[str, Any]],
    integrity_ok: bool,
    test_rc: int = 0,
    pipeline_ok: bool = True,
) -> int:
    if test_rc != 0 or not pipeline_ok:
        return 1
    if not integrity_ok:
        return 1
    return compute_collect_exit_code(source_rows)


def result_to_manifest_dict(result: CollectResult) -> dict[str, Any]:
    d = result.to_dict()
    meta = d.get("metadata") or {}
    d["runtime_status"] = meta.get("runtime_status") or d.get("status")
    d["expected_runtime_status"] = meta.get("expected_runtime_status")
    d["status_is_expected"] = meta.get("status_is_expected")
    d["failure_affects_exit_code"] = meta.get("failure_affects_exit_code")
    d["warning_message"] = meta.get("warning_message") or warning_message(
        result.warnings, result.errors
    )
    return d
