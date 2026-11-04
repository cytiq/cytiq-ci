# CI 0.2.0 rollout

## Order

Grant Dependabot access to the private `cytiq-ci` repository before expecting automatic reusable-workflow
updates. This is separate from Actions workflow access; keep the organization's default access unchanged.

1. Run actionlint, zizmor and the usage-report tests. Collect a baseline with authenticated `gh`; keep the snapshot
   private. Do not publish the report in a public issue or repository.
2. Validate the shared workflow from a feature branch or immutable commit in a caller. Publish `0.2.0` through the
   existing RC/changelog/signed-release process; never move `0.0.1` or `0.1.0`.
3. Connect `cytiq-argo`, `cytiq-tree` and `cytiq-ml` with explicit Python/uv versions and a `just ci` recipe. Preserve
   all current checks. In ML this includes synthetic AML/FlowCyt preparation, all extras, lint, type checking and
   every unit/integration test. Tree includes example validation. Argo keeps its independent offline Argo lint.
4. Enable Docker registry cache in the CLI caller. Leave its parallel `quality` and `test` checks and their
   default-branch-only cache writes in place. Do not skip release PR packaging or merge-queue correctness tests.

## Required checks

CLI requires `quality` and `test`; do not rename them. ML currently requires `qa`; tree requires `Python QA`.
Their new reusable check is `Python QA / ci`. Keep the old jobs in the migration PR until the new check is green.
Then add the new required context, remove the old context only while the new one remains required, and remove
the duplicate legacy job. Preserve the GitHub Actions integration ID, all unrelated protection rules and Mergify
conditions. If administration access is unavailable, leave the migration PR with both checks and document the
remaining setting change; never merge a configuration that leaves its required check pending.

Argo's existing `Python QA / ci` context is retained. No check is required for the optional metrics report,
fuzzing or the manual Rust benchmark.

## Runners and experiments

`CI_LIGHT_RUNNER` is a repository/organization Actions variable, defaulting to `ubuntu-24.04` when absent.
Use `ubuntu-slim` only for the shared-workflow validation job, ML contract checks/drift, and CLI release-version
resolution after testing the complete steps there. Shared CI also accepts a manual `runner` choice to compare
the two labels. Do not use slim for Docker, Rust compilation or ML QA.

Keep ten-minute timeouts for lightweight jobs. Slim has minimal software, no privileged Docker and a 15-minute
maximum. An unavailable command is a failed compatibility trial, not a reason to silently skip validation.

The CLI manual Rust benchmark uses separate ephemeral target directories for sequential, quality and test jobs.
Each measures cold and warm Cargo invocations at the same SHA/toolchain. It never uploads build caches: extra
target caches previously evicted main's cache at the repository limit. Compare summed job durations and setup
overhead as well as phase timings. These warm results measure local incremental compilation, not remote cache
transfer. Clippy and test artifacts need not share all compiled output. Required-check names stay unchanged.

For Docker compare empty/warm registry cache and a real source change, on both native architectures. Verify
the manifest digest, SBOM/provenance, `--help` and CatBoost/LightGBM inference. Export failure must not prevent
publishing a correctly built image.

## Acceptance and rollback

Compare two 30-day periods, normalizing by PR count, workflow/event mix and runner type. Split merge-queue
drafts, normal PRs, main pushes and release work. Inspect the actual required-check critical path for the P95
gate; the report's whole-workflow PR latency is a conservative proxy. Retain a performance optimization only
when estimated cost falls and required-check P95 increases by at most 10%. If samples are insufficient, keep
the candidate as an experiment; do not claim savings.

Roll back a lightweight runner trial by removing/resetting `CI_LIGHT_RUNNER`. Disable Docker cache with
`enable_cache: false`. Roll back a reusable Python caller only together with its matching required-check
contexts and legacy recipe contract. The old released tags stay available. Never restore global token rewrites; private git dependencies use
`python.yml`'s `DEPS_TOKEN`, which only the `uv sync` step's git sees.

Set the read-only `CI_METRICS_TOKEN` before enabling regular weekly collection. Review missing data explicitly.
Account for artifact/cache storage separately from list-price runner estimates. Keep only the two active
platform cache tags; do not automatically delete untagged image versions, which can belong to release manifests.

No new CI is added to API, web, Prefect or Obsidian in this rollout. Bun dependency caching, cargo-chef, sccache,
self-hosted runners and ARC require a later measured decision.
