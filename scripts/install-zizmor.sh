#!/usr/bin/env bash
set -euo pipefail

version=1.31.1
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) platform=x86_64-unknown-linux-gnu; checksum=d185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99 ;;
  Linux/aarch64) platform=aarch64-unknown-linux-gnu; checksum=37eebbd5762a44f262d94875431b14a6d2402991e90a685113ea97b8b41be833 ;;
  Darwin/arm64) platform=aarch64-apple-darwin; checksum=ad5aa633cd56215b11e6c51d51f90c7e6b22904a75047d1215abbd422f61d698 ;;
  Darwin/x86_64) platform=x86_64-apple-darwin; checksum=72ae63bb85b67229c06242f04195cb43927e9fab5f43803c6434dc701a517d61 ;;
  *) echo 'Unsupported zizmor platform' >&2; exit 1 ;;
esac

destination=${1:-"${RUNNER_TEMP:-${TMPDIR:-/tmp}}/cytiq-ci-bin"}
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
archive="zizmor-${platform}.tar.gz"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "https://github.com/zizmorcore/zizmor/releases/download/v${version}/${archive}" \
  --output "$temporary/$archive"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$temporary" && printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check)
else
  (cd "$temporary" && printf '%s  %s\n' "$checksum" "$archive" | shasum -a 256 --check)
fi
mkdir -p "$destination"
tar -xzf "$temporary/$archive" -C "$destination" zizmor
if [ -n "${GITHUB_PATH:-}" ]; then
  printf '%s\n' "$destination" >> "$GITHUB_PATH"
fi
printf 'Installed zizmor %s in %s\n' "$version" "$destination"
