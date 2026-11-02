#!/usr/bin/env python3
"""Read Actions metadata with gh; report usage, never claim to reproduce billing."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
import sys
import time
import zipfile
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

REPOSITORIES = tuple(
    f"cytiq/cytiq-{name}"
    for name in ("cli", "ml", "tree", "ci", "argo", "api", "web", "prefect", "obsidian")
)
MAX_ARTIFACT_BYTES = 1_048_576
ROOT = Path(__file__).resolve().parent.parent


class ApiError(RuntimeError):
    pass


class GitHub:
    """gh handles authentication and strips credentials from cross-host redirects."""

    def read(self, path: str) -> bytes:
        for attempt in range(3):
            try:
                response = subprocess.run(
                    ["gh", "api", "--method", "GET", path],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                if isinstance(error, OSError) or attempt == 2:
                    raise ApiError(f"Cannot read {path.split('?')[0]}") from error
            else:
                if response.returncode == 0:
                    return response.stdout
                # Do not retry permission errors or print response bodies/credentials.
                if re.search(rb"HTTP (401|403|404)\b", response.stderr) or attempt == 2:
                    raise ApiError(f"Cannot read {path.split('?')[0]}")
            time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def json(self, path: str, **parameters: Any) -> Any:
        query = f"?{urlencode(parameters)}" if parameters else ""
        try:
            return json.loads(self.read(path + query))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(f"Invalid JSON from {path}") from error


def pages(api: GitHub, path: str, key: str, **parameters: Any) -> list[dict]:
    result = []
    for page in range(1, 10001):
        response = api.json(path, per_page=100, page=page, **parameters)
        batch = response[key]
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise ApiError(f"Pagination did not finish for {path}")


def timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def runs_in_window(
    api: GitHub, repository: str, start: datetime, end: datetime
) -> list[dict]:
    """Split searches that exceed GitHub's 1,000-run filtered-search limit."""
    path = f"repos/{repository}/actions/runs"
    query = f"{iso(start)}..{iso(end - timedelta(seconds=1))}"
    first = api.json(path, created=query, per_page=100, page=1)
    if first["total_count"] > 1000:
        seconds = int((end - start).total_seconds())
        if seconds <= 1:
            raise ApiError(f"Too many runs in a one-second window for {repository}")
        middle = start + timedelta(seconds=seconds // 2)
        return runs_in_window(api, repository, start, middle) + runs_in_window(
            api, repository, middle, end
        )
    result = list(first["workflow_runs"])
    for page in range(2, math.ceil(first["total_count"] / 100) + 1):
        result.extend(
            api.json(path, created=query, per_page=100, page=page)["workflow_runs"]
        )
    unique = {run["id"]: run for run in result}
    if len(unique) < first["total_count"]:
        raise ApiError(f"Incomplete run listing for {repository}")
    return list(unique.values())


def cache_artifact(payload: bytes, run_id: int) -> dict:
    """Read a small JSON member in memory; never extract PR-controlled paths."""
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise ValueError("Cache artifact is too large")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "cache.json":
            raise ValueError("Unexpected cache artifact members")
        if members[0].file_size > 65536:
            raise ValueError("Cache record is too large")
        record = json.loads(archive.read(members[0]))
    if not isinstance(record, dict):
        raise ValueError("Cache record must be an object")
    if (
        record.get("schema_version") != 1
        or record.get("run_id") != run_id
        or type(record.get("run_attempt")) is not int
        or record["run_attempt"] < 1
        or not isinstance(record.get("job"), str)
        or not isinstance(record.get("caches"), list)
    ):
        raise ValueError("Invalid cache record identity")
    for cache in record["caches"]:
        if not isinstance(cache, dict):
            raise ValueError("Cache observation must be an object")
        if not isinstance(cache.get("name"), str) or type(cache.get("hit")) not in (
            bool,
            type(None),
        ):
            raise ValueError("Invalid cache observation")
    return record


def collect_run(api: GitHub, repository: str, run: dict) -> tuple[dict, list, list]:
    item = {"repository": repository, "run": run, "attempts": [], "cache_records": []}
    errors, warnings = [], []
    for number in range(1, run.get("run_attempt", 1) + 1):
        path = f"repos/{repository}/actions/runs/{run['id']}/attempts/{number}/jobs"
        try:
            item["attempts"].append(
                {"number": number, "jobs": pages(api, path, "jobs")}
            )
        except (ApiError, KeyError, TypeError, ValueError) as error:
            errors.append(f"{repository} run {run['id']}/{number}: {error}")
    try:
        artifacts = pages(
            api, f"repos/{repository}/actions/runs/{run['id']}/artifacts", "artifacts"
        )
        for artifact in artifacts:
            if not artifact["name"].startswith("ci-cache-") or artifact.get("expired"):
                continue
            if artifact["size_in_bytes"] > MAX_ARTIFACT_BYTES:
                raise ValueError("Cache artifact is too large")
            payload = api.read(
                f"repos/{repository}/actions/artifacts/{artifact['id']}/zip"
            )
            item["cache_records"].append(cache_artifact(payload, run["id"]))
    except (
        ApiError,
        KeyError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
        RuntimeError,
    ) as error:
        warnings.append(f"{repository} run {run['id']}: {error}")
    return item, errors, warnings


def collect(
    api: GitHub,
    repositories: list[str],
    start: datetime,
    end: datetime,
    checkpoint: Callable[[dict], None] | None = None,
) -> dict:
    snapshot = {
        "schema_version": 1,
        "start": iso(start),
        "end_exclusive": iso(end),
        "collected_at": iso(datetime.now(UTC)),
        "repositories": repositories,
        "pending_repositories": list(repositories),
        "runs": [],
        "errors": [],
        "cache_warnings": [],
    }
    for repository in repositories:
        print(f"Collecting {repository}", file=sys.stderr)
        try:
            runs = runs_in_window(api, repository, start, end)
            # Bounded parallel GETs keep weekly collection within its timeout.
            # map retains API order, so snapshots remain deterministic.
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = pool.map(lambda run: collect_run(api, repository, run), runs)
                for item, errors, warnings in results:
                    snapshot["runs"].append(item)
                    snapshot["errors"].extend(errors)
                    snapshot["cache_warnings"].extend(warnings)
        except (ApiError, KeyError, TypeError, ValueError) as error:
            snapshot["errors"].append(f"{repository}: {error}")
        snapshot["pending_repositories"].remove(repository)
        if checkpoint is not None:
            checkpoint(snapshot)
    return snapshot


def runner_kind(labels: list[str]) -> str | None:
    labels = [label.lower() for label in labels]
    if "self-hosted" in labels:
        return None
    if "ubuntu-slim" in labels:
        return "linux_slim"
    for label in labels:
        if re.fullmatch(r"ubuntu-(latest|\d{2}\.\d{2})(-arm)?", label):
            return "linux_arm" if label.endswith("-arm") else "linux"
        if re.fullmatch(r"windows-(latest|\d{4})(-arm)?", label):
            return "windows"
        if re.fullmatch(r"macos-(latest|\d+)(-intel)?", label):
            return "macos"
    return None


def elapsed(start: str | None, end: str | None) -> float | None:
    before, after = timestamp(start), timestamp(end)
    if before is None or after is None or after < before:
        return None
    return (after - before).total_seconds()


def observations(item: dict, attempt: int, name: str, jobs: list[dict]) -> list[dict]:
    # Called workflows prefix job names; match a short name only when unambiguous.
    short = name.rsplit(" / ", 1)[-1]
    unique = sum(job["name"].rsplit(" / ", 1)[-1] == short for job in jobs) == 1
    matches = [
        record
        for record in item["cache_records"]
        if record["run_attempt"] == attempt
        and (record["job"] == name or (unique and record["job"] == short))
    ]
    return matches[0]["caches"] if len(matches) == 1 else []


def job_records(snapshot: dict, rates: dict) -> list[dict]:
    records, seen = [], set()
    end = timestamp(snapshot["end_exclusive"])
    for item in snapshot["runs"]:
        run, repository = item["run"], item["repository"]
        for attempt in item["attempts"]:
            for job in attempt["jobs"]:
                identity = (repository, job["id"])
                if identity in seen:
                    continue
                seen.add(identity)
                started = timestamp(job.get("started_at"))
                queued = timestamp(job.get("created_at"))
                observed_start = started or queued
                if observed_start is not None and observed_start >= end:
                    continue
                completed = timestamp(job.get("completed_at"))
                skipped = job.get("conclusion") == "skipped"
                seconds = (
                    0
                    if skipped
                    else elapsed(job.get("started_at"), job.get("completed_at"))
                )
                if completed is not None and completed > end and not skipped:
                    seconds = None
                minutes = math.ceil(seconds / 60) if seconds is not None else None
                kind = runner_kind(job.get("labels", []))
                cost = (
                    0.0
                    if skipped
                    else round(minutes * rates["per_minute"][kind], 6)
                    if minutes is not None and kind is not None
                    else None
                )
                records.append(
                    {
                        "repository": repository,
                        "workflow": run["name"],
                        "workflow_path": run.get("path"),
                        "run_id": run["id"],
                        "attempt": attempt["number"],
                        "event": run["event"],
                        "branch": run.get("head_branch"),
                        "merge_queue": (run.get("head_branch") or "").startswith(
                            "mergify/merge-queue/"
                        ),
                        "job_id": job["id"],
                        "job": job["name"],
                        "conclusion": job.get("conclusion"),
                        "runner_kind": kind,
                        "duration_seconds": seconds,
                        "rounded_minutes": minutes,
                        "estimated_cost_usd": cost,
                        "queue_seconds": elapsed(
                            job.get("created_at"), job.get("started_at")
                        ),
                        "cache_observations": observations(
                            item, attempt["number"], job["name"], attempt["jobs"]
                        ),
                    }
                )
    return records


def percentile(values: list[float], quantile: float) -> float | None:
    return sorted(values)[math.ceil(len(values) * quantile) - 1] if values else None


def summarize(records: list[dict]) -> dict:
    durations = [
        record["duration_seconds"]
        for record in records
        if record["duration_seconds"] is not None and record["conclusion"] != "skipped"
    ]
    costs = [
        record["estimated_cost_usd"]
        for record in records
        if record["estimated_cost_usd"] is not None
    ]
    queue = [
        record["queue_seconds"]
        for record in records
        if record["queue_seconds"] is not None
    ]
    caches = [
        cache
        for record in records
        for cache in record["cache_observations"]
        if cache["hit"] is not None
    ]
    executed = [
        record for record in records if record["conclusion"] not in ("skipped", None)
    ]
    return {
        "jobs": len(records),
        "runner_minutes_known": round(sum(durations) / 60, 3),
        "unknown_duration_jobs": sum(
            record["duration_seconds"] is None for record in records
        ),
        "rounded_minutes_known": sum(
            record["rounded_minutes"] or 0 for record in records
        ),
        "estimated_cost_usd_known": round(sum(costs), 6),
        "unknown_cost_jobs": len(records) - len(costs),
        "job_duration_p50_seconds": percentile(durations, 0.50),
        "job_duration_p95_seconds": percentile(durations, 0.95),
        "queue_p95_seconds": percentile(queue, 0.95),
        "failed_jobs": sum(
            record["conclusion"] in ("failure", "timed_out", "startup_failure")
            for record in records
        ),
        "cancelled_jobs": sum(
            record["conclusion"] == "cancelled" for record in records
        ),
        "failure_rate": sum(
            record["conclusion"] in ("failure", "timed_out", "startup_failure")
            for record in executed
        )
        / len(executed)
        if executed
        else None,
        "observed_cache_restores": len(caches),
        "cache_hit_rate": sum(cache["hit"] for cache in caches) / len(caches)
        if caches
        else None,
    }


def report(snapshot: dict, rates: dict) -> dict:
    records = job_records(snapshot, rates)
    attempted_runs = defaultdict(set)
    for record in records:
        attempted_runs[(record["repository"], record["run_id"])].add(record["attempt"])
    retried_runs = sum(
        any(number > 1 for number in attempts) for attempts in attempted_runs.values()
    )
    groups = {}
    for field in ("repository", "workflow", "job", "event"):
        buckets = defaultdict(list)
        for record in records:
            key = (
                record[field]
                if field == "repository"
                else f"{record['repository']}: {record[field]}"
            )
            buckets[key].append(record)
        groups[field] = {key: summarize(rows) for key, rows in sorted(buckets.items())}
    # Keep repositories with no jobs visible in the inventory.
    for repository in snapshot["repositories"]:
        groups["repository"].setdefault(repository, summarize([]))
    pr_latencies = defaultdict(list)
    for item in snapshot["runs"]:
        run = item["run"]
        if run["event"] != "pull_request":
            continue
        first = next(
            (attempt for attempt in item["attempts"] if attempt["number"] == 1), None
        )
        if not first or not first["jobs"]:
            continue
        active = [job for job in first["jobs"] if job.get("conclusion") != "skipped"]
        if not active or any(not job.get("completed_at") for job in active):
            continue
        finished = max(job["completed_at"] for job in active)
        seconds = elapsed(run.get("created_at"), finished)
        if seconds is not None and timestamp(finished) < timestamp(
            snapshot["end_exclusive"]
        ):
            pr_latencies[item["repository"]].append(seconds)
    return {
        "schema_version": 1,
        "start": snapshot["start"],
        "end_exclusive": snapshot["end_exclusive"],
        "complete": not snapshot["errors"] and not snapshot.get("pending_repositories"),
        "errors": snapshot["errors"],
        "cache_warnings": snapshot["cache_warnings"],
        "rate_snapshot": rates,
        "summary": summarize(records),
        "runs": len(snapshot["runs"]),
        "retried_runs": retried_runs,
        "retry_rate": retried_runs / len(snapshot["runs"])
        if snapshot["runs"]
        else None,
        "cancelled_runs": sum(
            item["run"].get("conclusion") == "cancelled" for item in snapshot["runs"]
        ),
        "pr_workflow_latency": {
            repository: {
                "samples": len(values),
                "p50_seconds": percentile(values, 0.5),
                "p95_seconds": percentile(values, 0.95),
            }
            for repository, values in sorted(pr_latencies.items())
        },
        "groups": groups,
        "jobs": records,
    }


def display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(data: dict) -> str:
    lines = [
        "# Cytiq Actions usage",
        "",
        f"UTC run cohort: {data['start']} to {data['end_exclusive']} (exclusive).",
        f"Status: {'complete' if data['complete'] else 'INCOMPLETE'}. Runs: {data['runs']}; retried: {data['retried_runs']}.",
        "",
        "Costs are list-price estimates, before included usage, credits and storage; they are not invoices.",
        "Known totals exclude missing data. PR latency includes queue/dependency wait and every job in the first attempt, not just required checks.",
        "Cache hits describe instrumented restores only; Rust reports exact matches. Missing telemetry is N/A.",
        "",
        "| Repository | Runner min (known) | Rounded min | Est. USD (known) | Unknown cost jobs | Job P50 s | Job P95 s | Cache hit rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fields = (
        "runner_minutes_known",
        "rounded_minutes_known",
        "estimated_cost_usd_known",
        "unknown_cost_jobs",
        "job_duration_p50_seconds",
        "job_duration_p95_seconds",
        "cache_hit_rate",
    )
    for repository, summary in sorted(data["groups"]["repository"].items()):
        lines.append(
            "| "
            + " | ".join(
                display(value)
                for value in [repository, *(summary[field] for field in fields)]
            )
            + " |"
        )
    lines += [
        "",
        "| Repository | PR workflow samples | PR P50 s | PR P95 s |",
        "|---|---:|---:|---:|",
    ]
    for repository, values in data["pr_workflow_latency"].items():
        lines.append(
            "| "
            + " | ".join(
                display(value)
                for value in [
                    repository,
                    values["samples"],
                    values["p50_seconds"],
                    values["p95_seconds"],
                ]
            )
            + " |"
        )
    if data["errors"] or data["cache_warnings"]:
        lines += ["", "## Missing data", ""]
        lines += [
            f"- {display(message)}"
            for message in data["errors"] + data["cache_warnings"]
        ]
    return "\n".join(lines) + "\n"


def write_reports(data: dict, snapshot: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [("report.json", data), ("snapshot.json", snapshot)]:
        (output / name).write_text(json.dumps(value, indent=2) + "\n")
    (output / "report.md").write_text(markdown(data))
    columns = (
        [key for key in data["jobs"][0] if key != "cache_observations"]
        if data["jobs"]
        else ["repository", "job", "duration_seconds", "estimated_cost_usd"]
    )
    with (output / "jobs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in data["jobs"]:
            row = {key: record[key] for key in columns}
            # Keep branch/workflow names from becoming formulas when opened in Excel.
            writer.writerow(
                {
                    key: "'" + value
                    if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
                    else value
                    for key, value in row.items()
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories", nargs="+", default=list(REPOSITORIES))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="Exclusive UTC date",
    )
    parser.add_argument("--rates", type=Path, default=ROOT / "config/runner-rates.json")
    parser.add_argument("--output-dir", type=Path, default=Path("report"))
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Re-render an existing snapshot without API access",
    )
    arguments = parser.parse_args()
    if arguments.days < 1 or any(
        not re.fullmatch(r"cytiq/[A-Za-z0-9_.-]+", repo)
        for repo in arguments.repositories
    ):
        parser.error("Use a positive --days and cytiq/repository names")
    end = datetime.combine(arguments.end_date, datetime.min.time(), tzinfo=UTC)
    rates = json.loads(arguments.rates.read_text())

    def checkpoint(partial: dict) -> None:
        write_reports(report(partial, rates), partial, arguments.output_dir)

    snapshot = (
        json.loads(arguments.snapshot.read_text())
        if arguments.snapshot
        else collect(
            GitHub(),
            arguments.repositories,
            end - timedelta(days=arguments.days),
            end,
            checkpoint=checkpoint,
        )
    )
    result = report(snapshot, rates)
    write_reports(result, snapshot, arguments.output_dir)
    print(
        f"Wrote {arguments.output_dir}/report.md ({'complete' if result['complete'] else 'INCOMPLETE'})"
    )
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
