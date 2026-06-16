"""LLM usage and cost logging for the Agent Factory Platform."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[2]
DEFAULT_COST_CATALOG_FILE = PROJECT_ROOT / "config" / "llm_costs.json"
DEFAULT_USAGE_LOG_FILE = PROJECT_ROOT / "data" / "llm_usage.json"
MAX_RECENT_RUNS = 100
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageSnapshot:
    """Normalized token usage for one model."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int = 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_cost_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the maintained model pricing catalog."""
    resolved = path or DEFAULT_COST_CATALOG_FILE
    if not resolved.exists():
        return {"updated_at": None, "source": None, "models": {}}
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Cost catalog must be a JSON object: {resolved}")
    data.setdefault("models", {})
    return data


def load_usage_log(path: Path | None = None) -> dict[str, Any]:
    """Load the aggregate LLM usage summary."""
    resolved = path or DEFAULT_USAGE_LOG_FILE
    if not resolved.exists():
        return _empty_usage_log()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Usage log must be a JSON object: {resolved}")
    data.setdefault("totals", _empty_usage_totals())
    data.setdefault("by_model", {})
    data.setdefault("recent_runs", [])
    return data


def record_llm_run(
    *,
    operation: str,
    requested_model: str | None,
    effective_model: str | None,
    status: str,
    duration_seconds: float,
    usage_by_model: Mapping[str, UsageSnapshot] | None = None,
    error: str | None = None,
    thread_id: str | None = None,
    request_kind: str | None = None,
    result_preview: str | None = None,
    usage_log_path: Path | None = None,
    cost_catalog_path: Path | None = None,
) -> dict[str, Any]:
    """Write one run record and update the project-wide usage summary."""
    resolved_usage_log = usage_log_path or DEFAULT_USAGE_LOG_FILE
    resolved_usage_log.parent.mkdir(parents=True, exist_ok=True)

    resolved_catalog = load_cost_catalog(cost_catalog_path)
    model_usage = _normalise_usage_map(usage_by_model or {})
    cost_breakdown = _estimate_cost_breakdown(model_usage, resolved_catalog)
    total_tokens = sum(item.total_tokens for item in model_usage.values())
    input_tokens = sum(item.input_tokens for item in model_usage.values())
    output_tokens = sum(item.output_tokens for item in model_usage.values())

    run_record = {
        "timestamp": utc_now_iso(),
        "operation": operation,
        "request_kind": request_kind,
        "status": status,
        "thread_id": thread_id,
        "requested_model": requested_model,
        "effective_model": effective_model,
        "duration_ms": _round_ms(duration_seconds),
        "usage": [item for item in cost_breakdown["models"]],
        "totals": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "cost": cost_breakdown["cost"],
    }
    if error:
        run_record["error"] = error
    if result_preview:
        run_record["result_preview"] = result_preview

    usage_log = load_usage_log(resolved_usage_log)
    _update_usage_log(usage_log, run_record)
    resolved_usage_log.write_text(json.dumps(usage_log, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    logger.info(_format_run_summary(run_record))
    return run_record


def get_usage_summary(path: Path | None = None) -> dict[str, Any]:
    """Return the current usage summary JSON payload."""
    return load_usage_log(path)


def extract_usage_metadata(usage_source: Any) -> dict[str, UsageSnapshot]:
    """Normalize a callback handler or raw usage metadata payload."""
    if usage_source is None:
        return {}

    if hasattr(usage_source, "usage_metadata"):
        usage_source = getattr(usage_source, "usage_metadata")

    if not isinstance(usage_source, Mapping):
        return {}

    normalised: dict[str, UsageSnapshot] = {}
    for model_name, payload in usage_source.items():
        snapshot = _snapshot_from_payload(payload)
        if snapshot is not None:
            normalised[str(model_name)] = snapshot
    return normalised


def canonical_model_name(model_name: str | None) -> str | None:
    """Strip provider prefixes from a model name."""
    if not model_name:
        return None
    if ":" in model_name:
        return model_name.split(":", 1)[1].strip()
    return model_name.strip()


def _normalise_usage_map(usage_map: Mapping[str, UsageSnapshot]) -> dict[str, UsageSnapshot]:
    normalised: dict[str, UsageSnapshot] = {}
    for model_name, snapshot in usage_map.items():
        if not isinstance(snapshot, UsageSnapshot):
            continue
        normalised[str(model_name)] = snapshot
    return normalised


def _snapshot_from_payload(payload: Any) -> UsageSnapshot | None:
    if payload is None:
        return None
    if isinstance(payload, UsageSnapshot):
        return payload
    if not isinstance(payload, Mapping):
        return None

    input_tokens = int(payload.get("input_tokens", 0) or 0)
    output_tokens = int(payload.get("output_tokens", 0) or 0)
    total_tokens = int(payload.get("total_tokens", input_tokens + output_tokens) or 0)

    cached_input_tokens = 0
    input_details = payload.get("input_token_details")
    if isinstance(input_details, Mapping):
        cached_input_tokens = int(input_details.get("cache_read", 0) or 0)

    return UsageSnapshot(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
    )


def _estimate_cost_breakdown(
    usage_map: Mapping[str, UsageSnapshot],
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    models_catalog = catalog.get("models", {})
    line_items: list[dict[str, Any]] = []
    known_cost = Decimal("0")
    unknown_models: list[str] = []

    for raw_model_name, snapshot in usage_map.items():
        canonical_name = canonical_model_name(raw_model_name) or raw_model_name
        pricing = _lookup_pricing(models_catalog, raw_model_name, canonical_name)
        line_item = {
            "model": raw_model_name,
            "canonical_model": canonical_name,
            "input_tokens": snapshot.input_tokens,
            "output_tokens": snapshot.output_tokens,
            "total_tokens": snapshot.total_tokens,
            "cached_input_tokens": snapshot.cached_input_tokens,
        }

        if pricing is None or pricing.get("status") == "unknown":
            line_item["cost_usd"] = None
            line_item["cost_status"] = "unknown"
            unknown_models.append(raw_model_name)
        else:
            item_cost = _estimate_model_cost(snapshot, pricing)
            line_item["cost_usd"] = item_cost
            line_item["cost_status"] = "estimated"
            known_cost += Decimal(str(item_cost))
        line_items.append(line_item)

    if not line_items:
        return {
            "models": [],
            "cost": {
                "status": "unknown",
                "known_usd": None,
                "unknown_models": [],
            },
        }

    if unknown_models and len(unknown_models) == len(line_items):
        status = "unknown"
        known_usd: float | None = None
    elif unknown_models:
        status = "partial"
        known_usd = _decimal_to_usd(known_cost)
    else:
        status = "estimated"
        known_usd = _decimal_to_usd(known_cost)

    return {
        "models": line_items,
        "cost": {
            "status": status,
            "known_usd": known_usd,
            "unknown_models": unknown_models,
        },
    }


def _lookup_pricing(
    catalog: Any,
    raw_model_name: str,
    canonical_name: str,
) -> Mapping[str, Any] | None:
    if not isinstance(catalog, Mapping):
        return None

    candidates = [raw_model_name, canonical_name, raw_model_name.lower(), canonical_name.lower()]
    for candidate in candidates:
        if not candidate:
            continue
        entry = catalog.get(candidate)
        if isinstance(entry, Mapping):
            return entry
    return None


def _estimate_model_cost(snapshot: UsageSnapshot, pricing: Mapping[str, Any]) -> float:
    input_rate = Decimal(str(pricing["input_per_1m"]))
    output_rate = Decimal(str(pricing["output_per_1m"]))
    cached_input_rate = Decimal(str(pricing.get("cached_input_per_1m", pricing["input_per_1m"])))

    cached_input_tokens = min(snapshot.cached_input_tokens, snapshot.input_tokens)
    standard_input_tokens = max(snapshot.input_tokens - cached_input_tokens, 0)

    total = (
        (Decimal(standard_input_tokens) * input_rate)
        + (Decimal(cached_input_tokens) * cached_input_rate)
        + (Decimal(snapshot.output_tokens) * output_rate)
    ) / Decimal("1000000")
    return _decimal_to_usd(total)


def _update_usage_log(usage_log: dict[str, Any], run_record: dict[str, Any]) -> None:
    totals = usage_log.setdefault("totals", _empty_usage_totals())
    totals["calls"] += 1
    totals["runs"] += 1
    totals["duration_ms"] += run_record["duration_ms"]
    totals["input_tokens"] += run_record["totals"]["input_tokens"]
    totals["output_tokens"] += run_record["totals"]["output_tokens"]
    totals["total_tokens"] += run_record["totals"]["total_tokens"]

    if run_record["status"] == "ok":
        totals["ok_runs"] += 1
    else:
        totals["error_runs"] += 1

    cost = run_record["cost"]
    if cost["known_usd"] is not None:
        totals["known_cost_usd"] = _decimal_to_usd(
            Decimal(str(totals["known_cost_usd"])) + Decimal(str(cost["known_usd"]))
        )
    if cost["status"] != "estimated":
        totals["unknown_cost_runs"] += 1

    by_model = usage_log.setdefault("by_model", {})
    for item in run_record["usage"]:
        model_key = item["canonical_model"]
        model_totals = by_model.setdefault(model_key, _empty_model_totals())
        model_totals["calls"] += 1
        model_totals["input_tokens"] += item["input_tokens"]
        model_totals["output_tokens"] += item["output_tokens"]
        model_totals["total_tokens"] += item["total_tokens"]
        if item["cost_usd"] is not None:
            model_totals["known_cost_usd"] = _decimal_to_usd(
                Decimal(str(model_totals["known_cost_usd"])) + Decimal(str(item["cost_usd"]))
            )
        else:
            model_totals["unknown_cost_runs"] += 1

    recent_runs = usage_log.setdefault("recent_runs", [])
    recent_runs.append(run_record)
    del recent_runs[:-MAX_RECENT_RUNS]
    usage_log["updated_at"] = run_record["timestamp"]


def _empty_usage_log() -> dict[str, Any]:
    return {
        "updated_at": None,
        "totals": _empty_usage_totals(),
        "by_model": {},
        "recent_runs": [],
    }


def _empty_usage_totals() -> dict[str, Any]:
    return {
        "calls": 0,
        "runs": 0,
        "ok_runs": 0,
        "error_runs": 0,
        "duration_ms": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "known_cost_usd": 0.0,
        "unknown_cost_runs": 0,
    }


def _empty_model_totals() -> dict[str, Any]:
    return {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "known_cost_usd": 0.0,
        "unknown_cost_runs": 0,
    }


def _decimal_to_usd(value: Decimal) -> float:
    quantized = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return float(quantized)


def _round_ms(duration_seconds: float) -> float:
    return _decimal_to_usd(Decimal(str(duration_seconds)) * Decimal("1000"))


def _format_run_summary(run_record: dict[str, Any]) -> str:
    totals = run_record["totals"]
    cost = run_record["cost"]
    if cost["status"] == "estimated":
        cost_text = f"${cost['known_usd']:.6f}"
    elif cost["status"] == "partial":
        cost_text = f"${cost['known_usd']:.6f} (partial)"
    else:
        cost_text = "unknown"
    model_names = ", ".join(item["model"] for item in run_record["usage"]) or "none"
    return (
        f"LLM {run_record['operation']} finished "
        f"in {run_record['duration_ms']:.1f}ms "
        f"(input={totals['input_tokens']}, output={totals['output_tokens']}, total={totals['total_tokens']}, "
        f"cost={cost_text}, models={model_names}, status={run_record['status']})"
    )
