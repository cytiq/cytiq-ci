#!/usr/bin/env bash
set -euo pipefail

version=1.7.12
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) platform=linux_amd64; checksum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;;
  Linux/aarch64) platform=linux_arm64; checksum=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6 ;;
  Darwin/arm64) platform=darwin_arm64; checksum=aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f ;;
  Darwin/x86_64) platform=darwin_amd64; checksum=5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644 ;;
  *) echo 'Unsupported actionlint platform' >&2; exit 1 ;;
esac

destination=${1:-"${RUNNER_TEMP:-${TMPDIR:-/tmp}}/cytiq-ci-bin"}
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
archive="actionlint_${version}_${platform}.tar.gz"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "https://github.com/rhysd/actionlint/releases/download/v${version}/${archive}" \
  --output "$temporary/$archive"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$temporary" && printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check)
else
  (cd "$temporary" && printf '%s  %s\n' "$checksum" "$archive" | shasum -a 256 --check)
fi
mkdir -p "$destination"
tar -xzf "$temporary/$archive" -C "$destination" actionlint
if [ -n "${GITHUB_PATH:-}" ]; then
  printf '%s\n' "$destination" >> "$GITHUB_PATH"
fi
printf 'Installed actionlint %s in %s\n' "$version" "$destination"
