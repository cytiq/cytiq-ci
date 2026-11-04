# cytiq-ci

Reusable GitHub Actions workflows for CI/CD across the `cytiq` repositories.

## Reusable workflows

| Workflow | Purpose |
|---|---|
| `python.yml` | Python CI: lint, type check and unit tests through the repository's `just` recipes |
| `release.yml` | Release flow: an RC tag opens a changelog PR; merging it creates a signed tag and a GitHub Release |
| `docker-publish.yml` | Build and push a `linux/amd64` + `linux/arm64` image to GHCR with SBOM and provenance attestations; outputs the digest |

Pin a released tag. Version 0.2.0 changes the Python caller contract:

```yaml
jobs:
  qa:
    uses: cytiq/cytiq-ci/.github/workflows/python.yml@0.2.0
    with:
      workdir: "."
      python_version: "3.13"
      uv_version: "0.9.8"
```

### `python.yml`

Installs the exact `uv_version` and selected `python_version`, restores the uv download cache keyed by
`uv.lock`, and runs one `uv sync --locked --all-extras --group dev` in `workdir`. Only the default branch saves
the cache. It then runs `just ci` with `UV_NO_SYNC=true`, so project commands reuse that environment.

Callers provide a non-mutating `ci` recipe containing their existing checks, fixtures and test selection.

Private git dependencies on github.com (e.g. `cytiq-db = { git = "https://github.com/cytiq/cytiq-db.git", tag =
"0.1.0" }`) need the optional `DEPS_TOKEN` secret, a read-only token for those repositories. Only the `uv sync`
step sees it, through a credential helper set in that step's environment: nothing is written to `~/.gitconfig`,
no URL is rewritten or carries the token, and `just ci` runs without it. There is still no global Git
configuration. Fetch private reference repositories (data, not dependencies) with an explicit checkout and a
repository-scoped read token in the caller.

```yaml
jobs:
  qa:
    uses: cytiq/cytiq-ci/.github/workflows/python.yml@0.3.0
    with:
      workdir: "."
      python_version: "3.13"
      uv_version: "0.9.8"
    secrets:
      DEPS_TOKEN: ${{ secrets.CYTIQ_DEPS_TOKEN }}
```

Optional `ci-cache-*` artifacts record uv restore hits for 35 days; missing telemetry does not change QA results.

### `release.yml`

Call it twice from a repository's `cd.yml`:

```yaml
on:
  push:
    tags: ["*.*.*-rc*"]
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  changelog:
    if: github.event_name == 'push'
    uses: cytiq/cytiq-ci/.github/workflows/release.yml@0.2.0
    with:
      tag: ${{ github.ref_name }}
      update_changelog: true
    secrets: inherit

  release:
    if: >-
      github.event_name == 'pull_request' &&
      github.event.pull_request.merged == true &&
      startsWith(github.event.pull_request.head.ref, 'chore/update-changelog-')
    uses: cytiq/cytiq-ci/.github/workflows/release.yml@0.2.0
    with:
      tag: ${{ github.event.pull_request.head.ref }}
      update_changelog: false
      cleanup_rc_tags: true
    secrets: inherit
```

1. Pushing `X.Y.Z-rcN` generates `CHANGELOG.md` and `RELEASE_NOTES.md` with git-cliff (the caller needs a
   `cliff.toml`), sets the version in `pyproject.toml`, `Cargo.toml` and/or `package.json`, updates the matching
   lockfile without upgrading anything, and opens `chore/update-changelog-X.Y.Z`.
2. Merging that PR pushes a GPG-signed `X.Y.Z` tag, creates the GitHub Release (attaching `artifacts` globs, if
   given) and, with `cleanup_rc_tags`, deletes the `X.Y.Z-rc*` tags.

Secrets: `GPG_PRIVATE_KEY`, `GPG_PASSPHRASE`, `GPG_FINGERPRINT` (see `just gen-gpg-key`) and `GH_TOKEN`, a token
that can push to `main` and whose PRs trigger workflows (the default `GITHUB_TOKEN`'s PRs don't).

### `docker-publish.yml`

```yaml
  build-and-push:
    uses: cytiq/cytiq-ci/.github/workflows/docker-publish.yml@0.2.0
    with:
      image: cytiq-cli
      dockerfile: docker/Dockerfile
      version: 1.2.3
      latest: true
      enable_cache: true
      ref: ${{ github.sha }}
      build_args: |
        CYTIQ_BUILD_COMMIT=${{ github.sha }}
    permissions:
      contents: read
      packages: write
```

Pushes `ghcr.io/<org>/<image>:<version>` (and `:latest`) as one multi-platform manifest list, with an SBOM and
`mode=max` provenance attached to each platform. `platforms` defaults to `linux/amd64,linux/arm64`. Each platform
builds natively on its own GitHub-hosted runner (`ubuntu-24.04` or `ubuntu-24.04-arm`, no QEMU) and is pushed by
digest; a final job tags the manifest list over them. Other platforms are rejected. The `digest` output is the
manifest list's digest, which is what deployments should pin.

`enable_cache` defaults to `false`. When enabled, builds import `:cache-linux-amd64` or `:cache-linux-arm64`
from the image's registry. Default-branch/tag pushes and merged PRs into the default branch export `mode=max`
cache to the matching tag; manual publications from the default branch may also export. Other PRs do not write cache.
A missing cache or failed cache export does not
prevent a successful image publication. Build failures still fail the workflow.

Registry cache contains build layers, including intermediate build stages. Treat it as private source material.
It does not export Cargo cache mounts. In particular, changing source files or `CYTIQ_BUILD_COMMIT` can still
invalidate the compiler layer. Measure repeated and changed-source builds before adding cargo-chef or sccache.

## Dependabot access to private workflows

Automatic Actions updates need a separate organization-level Dependabot grant to read `cytiq/cytiq-ci`.
In the organization's security settings, add only `cytiq-ci` to the private repositories Dependabot may access;
keep the default repository access level unchanged. The Actions setting that allows organization repositories
to call reusable workflows does not grant Dependabot this access.

Without the grant, Actions updates report `git_dependencies_not_reachable` for this repository even though CI
itself passes. Do not work around this by passing a broad token to Python QA or disabling update checks.
See [GitHub's repository-access API](https://docs.github.com/en/rest/dependabot/repository-access) for the
administrative endpoint and required permissions. This grant is independent of the read-only metrics token.

## Usage reporting

The weekly **CI usage report** workflow reads the last 30 full UTC days across the nine configured repositories.
Set `CI_METRICS_TOKEN` in this repository to an organization-approved fine-grained token with **Actions: read**
and automatic Metadata read access on those repositories only. No billing, contents-write or organization-admin
permission is needed. The token is available only to the collection step; checkout uses its own read-only token.

The workflow stores `report.md`, `report.json`, `jobs.csv` and the re-renderable `snapshot.json` as private
artifacts for 90 days. Missing token/API access fails the run; partial reports are preserved and marked incomplete.

Local usage requires Python 3.11+ and authenticated `gh`:

```bash
python3 scripts/ci_usage_report.py --output-dir report
python3 scripts/ci_usage_report.py --snapshot report/snapshot.json --output-dir report-replayed
```

Totals include failed/cancelled attempts and nested reusable jobs under the caller, without double-counting job
IDs. The UTC window selects runs by creation time; attempts beginning after its exclusive end are excluded.
Jobs still running at that boundary have unknown duration, not zero cost. Repositories with no Actions jobs
remain visible. Cost uses the dated list-price snapshot in `config/runner-rates.json`, per-job minute rounding,
and no allowances, credits or storage: compare actual charges with the billing export.
GitHub-generated Dependabot update/graph jobs on recognized standard runners have zero estimated cost,
while their resource minutes remain visible. Ordinary CI on Dependabot pull requests is priced normally.
Unknown or larger runner labels remain N/A. See [GitHub's Dependabot runner billing rules](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-on-actions).

The PR P50/P95 is first-attempt workflow latency including all jobs, queue and dependency waits. It is a useful
proxy, not an exact measurement of required-check latency. Queue time is N/A when the API has no job creation
timestamp. Cache rates cover instrumented restores only (Rust exact matches, uv restored entries), not Docker
layer reuse or historical runs without telemetry. Raw workflow/job/event aggregates are in `report.json`.

## Development

```bash
just install-actionlint
just lint            # actionlint over .github/workflows
just test            # Python 3.11+: reporting behavior tests
just security        # pinned zizmor: low-and-higher findings
```

See [CONTRIBUTING.md](./CONTRIBUTING.md).

See [the rollout guide](docs/ci-rollout.md) for required-check migration, runner experiments and rollback.

The manual **Docker cache smoke test** checks empty/warm/changed-source cache reuse, both native architectures,
SBOM/provenance, image contents and a deliberately failed cache export. It publishes a tiny private
`ci-cache-smoke-<run-id>` package, never an application release or `latest` tag.
