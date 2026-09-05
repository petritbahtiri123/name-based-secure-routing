"""Conservative classification of one fixed-shape physical-core depth ladder."""
import math
import statistics


def classify_ladder(records):
    if not records:
        raise ValueError("repeat records required")
    for key in ("path", "payload_bytes", "streams_per_group", "endpoint_groups"):
        if len({r.get(key) for r in records}) != 1:
            raise ValueError("different workload shapes must be classified separately")
    grouped = {}
    for r in records:
        depth = r["outstanding_per_stream"]
        if type(depth) is not int or depth < 1 or not r["valid"]:
            raise ValueError("invalid workload record")
        for key in ("aggregate_application_gbps", "p99_latency_ns"):
            if not math.isfinite(r[key]) or r[key] <= 0:
                raise ValueError("invalid measured value")
        if not 0 <= r["max_observed_total_outstanding"] <= r["configured_total_outstanding"]:
            raise ValueError("outstanding bound violated")
        grouped.setdefault(depth, []).append(r)
    baseline = statistics.median(r["p99_latency_ns"] for r in grouped[min(grouped)])
    cells, best_stable = [], None
    for depth, rows in sorted(grouped.items()):
        identities = [r["repeat"] for r in rows]
        if len(set(identities)) != len(rows) or len(rows) < 3:
            raise ValueError("at least three distinct valid repeats required")
        rates = [r["aggregate_application_gbps"] for r in rows]
        cv = statistics.stdev(rates) / statistics.mean(rates)
        if cv > .05 and len(rows) < 5:
            raise ValueError("five valid repeats required for dispersed cell")
        latency = [r["p99_latency_ns"] / baseline for r in rows]
        failed = any(r["errors"] or r["timeouts"] or not r["cleanup_pass"] for r in rows)
        if failed or max(latency) > 2 or (best_stable is not None and min(rates) < .75 * best_stable):
            status = "SATURATED"
        elif (sum(value > 1.25 for value in latency) >= 2
              or (best_stable is not None and sum(rate < .90 * best_stable for rate in rates) >= 2)):
            status = "DEGRADED"
        elif (max(latency) <= 1.25 and cv <= .05
              and (not cells or cells[0]["classification"] == "STABLE")
              and (best_stable is None or min(rates) >= .90 * best_stable)):
            status = "STABLE"
            best_stable = max(best_stable or 0, statistics.median(rates))
        else:
            status = "UNRESOLVED"
        cells.append({"outstanding_per_stream": depth, "repeat_count": len(rows),
                      "classification": status, "median_gbps": statistics.median(rates),
                      "gbps_range": [min(rates), max(rates)], "repeat_cv": cv,
                      "median_p99_ns": statistics.median(r["p99_latency_ns"] for r in rows),
                      "p99_ratio_range": [min(latency), max(latency)],
                      "errors_timeouts_or_cleanup_failure": failed})
    return {"schema": "nbsr-physical-core-ladder-classification-v1", "cells": cells,
            "reference_p99_ns": baseline, "strict_stable_gbps": best_stable,
            "observed_peak_diagnostic_gbps": max(r["aggregate_application_gbps"] for r in records),
            "scope": "One fixed-shape closed-loop depth ladder. Bounded in-flight work and clean drain are required; no external offered-rate claim.",
            "hardware_ceiling": "NOT_CLASSIFIED; CPU/topology and other resource evidence must be assessed separately."}
