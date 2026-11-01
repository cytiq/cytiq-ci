# justfile
# -----------------------------------------------------------------------------
# Global settings for just

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# ---- Install actionlint (macOS: brew / Linux: curl script)
[group('setup')]
install-actionlint:
    @if command -v brew >/dev/null 2>&1; then \
        brew install actionlint; \
    else \
        bash <(curl https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash); \
    fi

# ---- Lint GitHub Actions workflows
[group('quality')]
lint:
    actionlint -color

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
