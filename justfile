# justfile
# -----------------------------------------------------------------------------
# Global settings for just

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# ---- Install the pinned, checksum-verified actionlint release
[group('setup')]
install-actionlint:
    bash scripts/install-actionlint.sh .tools/bin

# ---- Lint GitHub Actions workflows
[group('quality')]
lint:
    @if [ -x .tools/bin/actionlint ]; then .tools/bin/actionlint -color; else actionlint -color; fi

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
