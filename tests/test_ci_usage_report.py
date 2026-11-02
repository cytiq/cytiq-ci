import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "usage", ROOT / "scripts/ci_usage_report.py"
)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)
RATES = json.loads((ROOT / "config/runner-rates.json").read_text())


def job(identifier, name="test", seconds=61, conclusion="success", labels=None):
    return {
        "id": identifier,
        "name": name,
        "conclusion": conclusion,
        "labels": ["ubuntu-24.04"] if labels is None else labels,
        "created_at": "2026-11-01T01:00:05Z",
        "started_at": "2026-11-01T01:00:10Z",
        "completed_at": usage.iso(
            datetime(2026, 11, 1, 1, 0, 10, tzinfo=UTC)
            + usage.timedelta(seconds=seconds)
        ),
    }


def snapshot(jobs, attempts=1):
    return {
        "schema_version": 1,
        "start": "2026-10-04T00:00:00Z",
        "end_exclusive": "2026-11-03T00:00:00Z",
        "repositories": ["cytiq/cytiq-cli", "cytiq/cytiq-web"],
        "errors": [],
        "cache_warnings": [],
        "runs": [
            {
                "repository": "cytiq/cytiq-cli",
                "run": {
                    "id": 42,
                    "name": "CI",
                    "event": "pull_request",
                    "head_branch": "feature",
                    "run_attempt": attempts,
                    "created_at": "2026-11-01T01:00:00Z",
                },
                "attempts": [{"number": 1, "jobs": jobs}],
                "cache_records": [],
            }
        ],
    }


class UsageTests(unittest.TestCase):
    def test_rounds_each_job_instead_of_workflow_wall_time(self):
        data = usage.report(snapshot([job(1), job(2)]), RATES)
        self.assertEqual(data["summary"]["rounded_minutes_known"], 4)
        self.assertEqual(data["summary"]["estimated_cost_usd_known"], 0.024)
        self.assertEqual(data["summary"]["runner_minutes_known"], 2.033)
        self.assertEqual(
            data["pr_workflow_latency"]["cytiq/cytiq-cli"]["p95_seconds"], 71
        )
        self.assertEqual(data["groups"]["repository"]["cytiq/cytiq-web"]["jobs"], 0)

    def test_all_attempts_are_counted_without_duplicate_job_ids(self):
        data = snapshot([job(1)], attempts=2)
        data["runs"][0]["attempts"].append({"number": 2, "jobs": [job(1), job(2)]})
        report = usage.report(data, RATES)
        self.assertEqual(report["summary"]["jobs"], 2)
        self.assertEqual(report["retried_runs"], 1)
        self.assertEqual(report["retry_rate"], 1)

    def test_skipped_and_never_started_jobs_do_not_invent_usage(self):
        skipped = job(1, conclusion="skipped", labels=[])
        waiting = job(2, conclusion="cancelled", labels=[])
        waiting["started_at"] = waiting["completed_at"] = None
        report = usage.report(snapshot([skipped, waiting]), RATES)
        self.assertEqual(report["summary"]["estimated_cost_usd_known"], 0)
        self.assertEqual(report["summary"]["unknown_cost_jobs"], 1)
        self.assertEqual(report["jobs"][0]["rounded_minutes"], 0)
        self.assertIsNone(report["jobs"][1]["duration_seconds"])
        self.assertIsNone(report["summary"]["job_duration_p50_seconds"])

    def test_unknown_runner_and_missing_cache_are_not_assumed_free_or_misses(self):
        data = usage.report(snapshot([job(1, labels=["ubuntu-custom-64"])]), RATES)
        self.assertIsNone(data["jobs"][0]["estimated_cost_usd"])
        self.assertEqual(data["summary"]["unknown_cost_jobs"], 1)
        self.assertIsNone(data["summary"]["cache_hit_rate"])
        self.assertIsNone(usage.runner_kind(["self-hosted", "ubuntu-24.04"]))

    def test_arm_and_slim_use_distinct_rates(self):
        data = usage.report(
            snapshot(
                [job(1, labels=["ubuntu-24.04-arm"]), job(2, labels=["ubuntu-slim"])]
            ),
            RATES,
        )
        self.assertEqual(data["summary"]["estimated_cost_usd_known"], 0.014)

    def test_retry_started_after_exclusive_end_is_excluded(self):
        data = snapshot([job(1)], attempts=2)
        later = job(2)
        later["started_at"] = "2026-11-03T01:00:10Z"
        later["completed_at"] = "2026-11-03T01:01:11Z"
        data["runs"][0]["attempts"].append({"number": 2, "jobs": [later]})
        self.assertEqual(len(usage.job_records(data, RATES)), 1)

    def test_incomplete_api_collection_is_visible(self):
        class Forbidden:
            def json(self, *args, **kwargs):
                raise usage.ApiError("permission denied")

        start, end = (
            datetime(2026, 10, 4, tzinfo=UTC),
            datetime(2026, 11, 3, tzinfo=UTC),
        )
        data = usage.collect(Forbidden(), ["cytiq/cytiq-cli"], start, end)
        report = usage.report(data, RATES)
        self.assertFalse(report["complete"])
        self.assertIn("INCOMPLETE", usage.markdown(report))

    def test_jobs_pagination_includes_the_second_page(self):
        class TwoPages:
            def json(self, path, **params):
                return {
                    "jobs": [job(index) for index in range(100)]
                    if params["page"] == 1
                    else [job(100)]
                }

        self.assertEqual(len(usage.pages(TwoPages(), "jobs", "jobs")), 101)

    def test_filtered_run_search_splits_at_the_api_limit(self):
        class ManyRuns:
            def __init__(self):
                self.queries = []

            def json(self, path, **params):
                self.queries.append(params["created"])
                if len(self.queries) == 1:
                    return {"total_count": 1001, "workflow_runs": []}
                return {"total_count": 1, "workflow_runs": [{"id": len(self.queries)}]}

        api = ManyRuns()
        result = usage.runs_in_window(
            api,
            "cytiq/cytiq-cli",
            datetime(2026, 11, 1, tzinfo=UTC),
            datetime(2026, 11, 2, tzinfo=UTC),
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(api.queries[1].endswith("2026-11-01T11:59:59Z"))
        self.assertTrue(api.queries[2].startswith("2026-11-01T12:00:00Z"))

    def test_cache_match_uses_attempt_and_unique_reusable_job_name(self):
        data = snapshot([job(1, name="Python QA / ci")])
        data["runs"][0]["cache_records"] = [
            {"run_attempt": 1, "job": "ci", "caches": [{"name": "uv", "hit": True}]},
            {"run_attempt": 2, "job": "ci", "caches": [{"name": "uv", "hit": False}]},
        ]
        self.assertEqual(usage.report(data, RATES)["summary"]["cache_hit_rate"], 1)
        data["runs"][0]["attempts"][0]["jobs"].append(job(2, name="Another QA / ci"))
        self.assertIsNone(usage.report(data, RATES)["summary"]["cache_hit_rate"])

    def test_cache_artifact_validation_never_extracts_paths(self):
        def archive(name, record):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as bundle:
                bundle.writestr(name, json.dumps(record))
            return stream.getvalue()

        record = {
            "schema_version": 1,
            "run_id": 42,
            "run_attempt": 1,
            "job": "test",
            "caches": [{"name": "cargo", "hit": True}],
        }
        self.assertEqual(
            usage.cache_artifact(archive("cache.json", record), 42), record
        )
        for name, payload in [
            ("../cache.json", record),
            ("cache.json", {**record, "run_id": 99}),
            ("cache.json", {**record, "caches": [{"name": "cargo", "hit": "true"}]}),
        ]:
            with (
                self.subTest(name=name, payload=payload),
                self.assertRaises(ValueError),
            ):
                usage.cache_artifact(archive(name, payload), 42)

    def test_api_does_not_retry_permission_errors_or_expose_response(self):
        response = usage.subprocess.CompletedProcess(
            [], 1, b"", b"secret-value: HTTP 403"
        )
        with patch.object(usage.subprocess, "run", return_value=response) as request:
            with self.assertRaises(usage.ApiError) as failure:
                usage.GitHub().read("repos/cytiq/cytiq-cli/actions/runs")
        self.assertEqual(request.call_count, 1)
        self.assertNotIn("secret-value", str(failure.exception))

    def test_reports_are_reproducible_from_snapshot_and_csv_is_safe(self):
        data = snapshot([job(1, name='=HYPERLINK("evil")')])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            usage.write_reports(usage.report(data, RATES), data, output)
            self.assertEqual(json.loads((output / "snapshot.json").read_text()), data)
            self.assertIn("'=HYPERLINK", (output / "jobs.csv").read_text())
            self.assertIn("not invoices", (output / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
