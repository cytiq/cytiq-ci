# cytiq-ci

Reusable GitHub Actions workflows for CI/CD across the `cytiq` repositories.

## Reusable workflows

| Workflow | Purpose |
|---|---|
| `python.yml` | Python CI: lint, type check and unit tests through the repository's `just` recipes |
| `release.yml` | Release flow: an RC tag opens a changelog PR; merging it creates a signed tag and a GitHub Release |
| `docker-publish.yml` | Build and push an image to GHCR with SBOM and provenance attestations; outputs the digest |

Pin a tag, never a branch:

```yaml
jobs:
  qa:
    uses: cytiq/cytiq-ci/.github/workflows/python.yml@0.0.1
    with:
      workdir: "."
    secrets: inherit
```

### `python.yml`

Runs `just install-uv`, `just create-env`, `just sync`, `just sync-dev`, `just lint`, `just type` and
`just tests-unit` in `workdir`. `GH_TOKEN` (optional) is used to fetch private git dependencies.

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
    uses: cytiq/cytiq-ci/.github/workflows/release.yml@0.0.1
    with:
      tag: ${{ github.ref_name }}
      update_changelog: true
    secrets: inherit

  release:
    if: >-
      github.event_name == 'pull_request' &&
      github.event.pull_request.merged == true &&
      startsWith(github.event.pull_request.head.ref, 'chore/update-changelog-')
    uses: cytiq/cytiq-ci/.github/workflows/release.yml@0.0.1
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
    uses: cytiq/cytiq-ci/.github/workflows/docker-publish.yml@0.0.1
    with:
      image: cytiq-cli
      dockerfile: docker/Dockerfile
      version: 1.2.3
      latest: true
      ref: ${{ github.sha }}
      build_args: |
        CYTIQ_BUILD_COMMIT=${{ github.sha }}
    permissions:
      contents: read
      packages: write
```

Pushes `ghcr.io/<org>/<image>:<version>` (and `:latest`), with an SBOM and `mode=max` provenance attached.
`platforms` defaults to `linux/amd64`. The `digest` output is what deployments should pin.

## Development

```bash
just install-actionlint
just lint            # actionlint over .github/workflows
```

See [CONTRIBUTING.md](./CONTRIBUTING.md).
