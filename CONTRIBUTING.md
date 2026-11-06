# Contributing to cytiq-ci

## Purpose

Reusable GitHub Actions workflows (`on: workflow_call`) for the `cytiq` repositories. They are ported from
`vibyy-app/vibyy-ci`; keep the two in step where it makes sense, but cytiq's versions may diverge (see below).

## Layout

- `.github/workflows/python.yml`, `release.yml`, `docker-publish.yml`: the reusable workflows.
- `.github/workflows/ci.yml`: this repository's own CI (actionlint, zizmor, reporting tests).
- `.github/workflows/ci-usage-report.yml`: weekly read-only organization usage report.
- `.github/actions/mise/action.yml`: installs a caller's pinned just, runs its `just mise` and exports the job's tools.
- `release.yml` also triggers on this repository's own RC tags and changelog PRs, so `cytiq-ci` releases itself.
- `scripts/gen-gpg-key.sh`: generates the release-signing key the `GPG_*` secrets hold.

## Differences from vibyy-ci

- `release.yml` decides what to do from its `tag` input when called. Inside a called workflow, `github.event_name`
  is the **caller's** event (`push` or `pull_request`), never `workflow_call`, so branching on the event name alone
  ignored `artifacts`, `update_changelog` and `cleanup_rc_tags`.
- `release.yml` also bumps `Cargo.toml`, and updates lockfiles with `uv lock`, `cargo update --workspace` and
  `bun install --lockfile-only` rather than the caller's `just lock`, which may upgrade every dependency.
  Path dependencies in tracked `Cargo.toml` files that require the previous version move with it; otherwise a
  minor or major bump leaves their range and `cargo update --workspace` fails before the PR opens.
- `docker-publish.yml` takes `ref`, `build_args` and `platforms`, builds each platform on a native runner
  (`ubuntu-24.04-arm` for arm64) and merges them into one manifest list, pushes SBOM and provenance attestations,
  and returns the manifest list's `digest`.

## Conventions

- Each workflow uses `workflow_call` with typed inputs and optional secrets, and declares minimal `permissions`.
- Pass expressions to shell steps through `env`, not inline in `run:`.
- Inputs use `snake_case`; YAML uses 2-space indentation and the `.yml` extension.
- Callers pin a tag (`@0.2.0`). A change to an input or secret is a breaking change for callers; release it as a new
  version and note it in the PR.

## Testing

`just lint`, `just security` and `just test` run workflow lint, offline security checks and the Python 3.11+
reporting tests. `just mise` installs mise and the tools `mise.toml` pins, with the checksums in `mise.lock`
(until it has run, recipes fail with “could not find the shell `mise-cytiq`”);
after changing a version there, run `"$(just --evaluate MISE)" lock` (the pinned mise) and commit both files. CI installs them through
`.github/actions/mise` at the same revision, so `ci.yml` also exercises that action.
Reusable workflows need a caller to test: push a branch and
point a caller at it temporarily (`uses: cytiq/cytiq-ci/.github/workflows/<name>.yml@<branch>`), then switch the
caller back to the released tag.

## Access

`cytiq-ci` is private. Callers in the organisation can use it only while
**Settings → Actions → General → Access** is set to "Accessible from repositories in the 'cytiq' organization".

## Commits and pull requests

Conventional Commits with a scope, e.g. `fix(release): strip the changelog branch prefix`. git-cliff builds the
changelog from them. PRs describe the workflows touched and any new or changed inputs and secrets, with a usage
example.
