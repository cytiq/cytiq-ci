# justfile
# -----------------------------------------------------------------------------
# Global settings for just

# Recipes run with the tools pinned in mise.toml, through the mise release that
# `just mise` installs outside PATH. `mise-cytiq` links to it and exists nowhere
# else, so a recipe fails rather than run another mise on PATH.
set shell := ["mise-cytiq", "exec", "--", "bash", "-eu", "-o", "pipefail", "-c"]

MISE_VERSION := replace_regex(read(justfile_directory() / "mise.toml"), '(?sm)\A.*?^min_version = "([^"]+)"$.*\z', '$1')
MISE_DIR := env("XDG_DATA_HOME", home_directory() / ".local/share") / "cytiq/mise" / MISE_VERSION
MISE := MISE_DIR / "mise"
export PATH := MISE_DIR + ":" + env("PATH")

# ---- Install the pinned mise and the tools in mise.toml; rerun after either changes
[group('setup')]
[script('bash')]
mise:
    set -euo pipefail
    version={{ quote(MISE_VERSION) }}
    mise={{ quote(MISE) }}
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo 'mise.toml must set min_version to an exact mise release' >&2
        exit 1
    fi
    if [[ "$("$mise" --version 2>/dev/null)" != "$version "* ]]; then
        installer="$(mktemp)"
        trap 'rm -f -- "$installer"' EXIT
        # The release's own installer embeds the checksums of its archives.
        curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
            "https://github.com/jdx/mise/releases/download/v$version/install.sh" --output "$installer"
        MISE_VERSION="v$version" MISE_INSTALL_PATH="$mise" MISE_INSTALL_FROM_GITHUB=1 \
            MISE_INSTALL_HELP=0 sh "$installer"
    fi
    ln -sfn mise "$(dirname -- "$mise")/mise-cytiq"
    "$mise" trust --quiet
    "$mise" install --locked

# ---- Install the pinned actionlint (kept for existing instructions; `just mise` installs every tool)
[group('setup')]
install-actionlint:
    mise install --locked actionlint

# ---- Lint GitHub Actions workflows
[group('quality')]
lint:
    actionlint -color

[group('quality')]
test:
    python3 -m unittest discover -s tests -v

[group('quality')]
security:
    zizmor --offline --min-severity low .

[group('metrics')]
usage-report *args:
    python3 scripts/ci_usage_report.py {{ args }}

# ---- List existing GPG keys
[group('setup')]
list-gpg-keys:
    @gpg --list-secret-keys --keyid-format=long

# ---- Generate a release-signing GPG keypair via scripts/gen-gpg-key.sh
[group('setup')]
gen-gpg-key name email output_dir="":
    @if [[ -n "{{ output_dir }}" ]]; then \
        bash scripts/gen-gpg-key.sh "{{ name }}" "{{ email }}" "{{ output_dir }}"; \
    else \
        bash scripts/gen-gpg-key.sh "{{ name }}" "{{ email }}"; \
    fi

# ---- Show help for all recipes
help:
    @just --list
