"""Export a sanitized, read-only Top 30 snapshot for the static web UI."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NORMALIZED_ROOT = ROOT / "data" / "normalized"
DEFAULT_OUTPUT = ROOT / "web" / "data" / "latest.json"
RUN_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

OUTPUT_FIELDS = (
    "unified_opportunity_id",
    "domain_type",
    "title",
    "organization",
    "opportunity_stage",
    "primary_opportunity_route",
    "priority_band",
    "unified_priority_score",
    "relevance_reasons",
    "expected_qrpick_role",
    "recommended_next_action",
    "blocking_unknowns",
    "posted_at",
    "deadline",
    "source_urls",
)
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "client_secret",
    "key",
    "servicekey",
    "service_key",
    "secret",
    "token",
}
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(service[_-]?key|api[_-]?key|apikey|access[_-]?token|"
    r"client[_-]?secret|secret|bearer)\b\s*[:=]\s*[^\s&;,]+"
)
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
WINDOWS_PATH_RE = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:\\[^\r\n\t|<>\"?*]+")
UNC_PATH_RE = re.compile(r"\\\\[^\\\s]+\\[^\r\n\t|<>\"?*]+")
POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:])/(?:home|Users|private|var|tmp|opt|mnt)/[^\s|<>]+"
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?0\d{1,2}[-.\s]\d{3,4}[-.\s]\d{4}(?!\d)"
)


class ExportError(RuntimeError):
    """Raised when source validation or safe publication fails."""


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ExportError(f"manifest missing: {path.resolve()}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"manifest unreadable: {path.resolve()}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ExportError(f"manifest root must be an object: {path.resolve()}")
    if manifest.get("status") != "OK":
        raise ExportError(
            f"manifest status must be OK: {path.resolve()}: "
            f"{manifest.get('status')!r}"
        )
    return manifest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ExportError(f"unified JSONL missing: {path.resolve()}")
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ExportError(
                        f"JSONL row must be an object: {path.resolve()}:{line_number}"
                    )
                rows.append(row)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"unified JSONL unreadable: {path.resolve()}: {exc}") from exc
    if not rows:
        raise ExportError(f"unified JSONL has zero rows: {path.resolve()}")
    return rows


def _select_run_dir(normalized_root: Path, run_day: str | None) -> Path:
    normalized_root = normalized_root.resolve()
    if run_day:
        if not RUN_DAY_RE.fullmatch(run_day):
            raise ExportError(f"invalid run day: {run_day}")
        return normalized_root / run_day
    if not normalized_root.exists():
        raise ExportError(f"normalized root missing: {normalized_root}")
    candidates = sorted(
        (
            path
            for path in normalized_root.iterdir()
            if path.is_dir() and RUN_DAY_RE.fullmatch(path.name)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for candidate in candidates:
        manifest_path = candidate / "unified-opportunity-manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(manifest, dict) and manifest.get("status") == "OK":
            return candidate
    raise ExportError(f"no run with manifest status OK under: {normalized_root}")


def _sanitize_text(value: str) -> str:
    value = SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", value
    )
    value = BEARER_RE.sub("Bearer [REDACTED]", value)
    value = WINDOWS_PATH_RE.sub("[REDACTED_PATH]", value)
    value = UNC_PATH_RE.sub("[REDACTED_PATH]", value)
    value = POSIX_PATH_RE.sub("[REDACTED_PATH]", value)
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = PHONE_RE.sub("[REDACTED_PHONE]", value)
    return value


def _sanitize_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = f"{host}:{port}" if port else host
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in SENSITIVE_QUERY_KEYS
        ],
        doseq=True,
    )
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, query, ""))


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            _sanitize_text(str(key)): _sanitize_value(item)
            for key, item in value.items()
        }
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_text(str(value))


def _safe_opportunity(row: dict[str, Any], rank: int) -> dict[str, Any]:
    missing = [field for field in OUTPUT_FIELDS if field not in row]
    if missing:
        raise ExportError(
            f"Top 30 row missing required fields "
            f"{missing}: {row.get('unified_opportunity_id')!r}"
        )
    if not str(row.get("unified_opportunity_id") or "").strip():
        raise ExportError("Top 30 row has an empty unified_opportunity_id")
    output = {"rank": rank}
    for field in OUTPUT_FIELDS:
        if field == "source_urls":
            urls = row.get(field)
            if not isinstance(urls, list):
                urls = [urls] if urls else []
            output[field] = [
                safe_url
                for safe_url in (_sanitize_url(url) for url in urls)
                if safe_url is not None
            ]
        else:
            output[field] = _sanitize_value(row.get(field))
    return output


def _assert_safe_payload(payload: dict[str, Any]) -> None:
    expected_top_fields = {"rank", *OUTPUT_FIELDS}
    opportunities = payload.get("opportunities")
    if not isinstance(opportunities, list) or not opportunities:
        raise ExportError("deployment payload has zero opportunities")
    if len(opportunities) > 30:
        raise ExportError(f"deployment payload exceeds Top 30: {len(opportunities)}")
    for expected_rank, row in enumerate(opportunities, start=1):
        if set(row) != expected_top_fields:
            raise ExportError(f"deployment row fields invalid at rank {expected_rank}")
        if row["rank"] != expected_rank:
            raise ExportError(f"deployment rank is unstable at rank {expected_rank}")
        for url in row["source_urls"]:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"}:
                raise ExportError(f"unsafe source URL remained: {url}")
    serialized = json.dumps(payload, ensure_ascii=False)
    if WINDOWS_PATH_RE.search(serialized) or UNC_PATH_RE.search(serialized):
        raise ExportError("local Windows path remained in deployment payload")
    unsafe_secret = any(
        "[REDACTED]" not in match.group(0)
        for match in SECRET_ASSIGNMENT_RE.finditer(serialized)
    )
    if unsafe_secret or BEARER_RE.search(serialized):
        raise ExportError("API key or token pattern remained in deployment payload")


def build_payload(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "unified-opportunity-manifest.json"
    jsonl_path = run_dir / "unified-opportunities.jsonl"
    manifest = _load_manifest(manifest_path)
    rows = _read_jsonl(jsonl_path)

    manifest_count = manifest.get("unified_row_count")
    if not isinstance(manifest_count, int) or manifest_count <= 0:
        raise ExportError(f"manifest unified_row_count must be positive: {manifest_count!r}")
    if manifest_count != len(rows):
        raise ExportError(
            f"manifest/JSONL count mismatch: manifest={manifest_count}, "
            f"jsonl={len(rows)}"
        )

    top_ids = manifest.get("top_unified_opportunity_ids")
    if not isinstance(top_ids, list) or not top_ids:
        raise ExportError("manifest Top 30 IDs are empty")
    if len(top_ids) > 30:
        raise ExportError(f"manifest Top 30 IDs exceed 30: {len(top_ids)}")
    if len(set(top_ids)) != len(top_ids):
        raise ExportError("manifest Top 30 IDs contain duplicates")

    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("unified_opportunity_id")
        if not isinstance(row_id, str) or not row_id:
            raise ExportError("unified row has an empty ID")
        if row_id in by_id:
            raise ExportError(f"duplicate unified ID in JSONL: {row_id}")
        by_id[row_id] = row
    missing_ids = [row_id for row_id in top_ids if row_id not in by_id]
    if missing_ids:
        raise ExportError(f"Top 30 IDs missing from JSONL: {missing_ids}")

    actionable_count = sum(
        1 for row in rows if row.get("priority_band") != "NO_ACTION"
    )
    manifest_actionable = manifest.get("action_candidate_count")
    if manifest_actionable != actionable_count:
        raise ExportError(
            f"manifest actionable count mismatch: manifest={manifest_actionable}, "
            f"jsonl={actionable_count}"
        )
    if manifest.get("top_row_count") != len(top_ids):
        raise ExportError(
            f"manifest Top 30 count mismatch: top_row_count="
            f"{manifest.get('top_row_count')}, ids={len(top_ids)}"
        )

    opportunities = [
        _safe_opportunity(by_id[row_id], rank)
        for rank, row_id in enumerate(top_ids, start=1)
    ]
    payload = {
        "run_date": str(manifest.get("run_day") or run_dir.name),
        "run_status": "OK",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(rows),
        "actionable_count": actionable_count,
        "top30_count": len(opportunities),
        "domain_counts": dict(
            sorted(Counter(str(row.get("domain_type") or "UNKNOWN") for row in rows).items())
        ),
        "priority_counts": dict(
            sorted(
                Counter(str(row.get("priority_band") or "UNKNOWN") for row in rows).items()
            )
        ),
        "warnings": _sanitize_value(manifest.get("warnings") or []),
        "opportunities": opportunities,
    }
    _assert_safe_payload(payload)
    return payload


def export_web_data(
    *,
    run_day: str | None = None,
    normalized_root: Path = DEFAULT_NORMALIZED_ROOT,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    run_dir = _select_run_dir(normalized_root, run_day)
    payload = build_payload(run_dir)
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".latest-",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        persisted = json.loads(temp_path.read_text(encoding="utf-8"))
        _assert_safe_payload(persisted)
        if persisted["top30_count"] != len(persisted["opportunities"]):
            raise ExportError("persisted Top 30 count mismatch")
        os.replace(temp_path, output_path)
        temp_path = None
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"web data publication failed: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-day")
    parser.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        payload = export_web_data(
            run_day=args.run_day,
            normalized_root=args.normalized_root,
            output_path=args.output,
        )
    except ExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"exported run_date={payload['run_date']} "
        f"total={payload['total_count']} "
        f"actionable={payload['actionable_count']} "
        f"top30={payload['top30_count']} "
        f"output={args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
