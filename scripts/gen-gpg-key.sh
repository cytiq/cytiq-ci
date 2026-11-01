#!/usr/bin/env bash
set -euo pipefail

# Generates a new GPG keypair and writes:
#   - private.asc
#   - public.asc
#   - passphrase.txt
#   - fingerprint.txt
# into a dedicated output directory.
#
# Usage:
#   ./gen-gpg-key.sh "Your Name" "you@example.com" [output_dir]
#
# Requirements:
#   - gpg (GnuPG) installed (v2.1+ recommended)
#   - No interactive pinentry needed (we use --pinentry-mode loopback)

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 \"Full Name\" \"email@example.com\" [output_dir]" >&2
  exit 1
fi

NAME="$1"
EMAIL="$2"
OUTDIR="${3:-gpg-key-$(date +%Y%m%d-%H%M%S)}"
START_TS="$(date +%s)"

# Lock down permissions for any files we create
umask 077
mkdir -p "$OUTDIR"

# Generate a reasonably strong random passphrase
# (works on Linux/macOS; if openssl is missing, we fall back to /dev/urandom)
if command -v openssl >/dev/null 2>&1; then
  PASSPHRASE="$(openssl rand -base64 48 | tr -d '\n')"
else
  PASSPHRASE="$(LC_ALL=C tr -dc 'A-Za-z0-9!@#%^_-+=' </dev/urandom | head -c 64)"
fi

echo -n "$PASSPHRASE" > "$OUTDIR/passphrase.txt"

USER_ID="${NAME} <${EMAIL}>"

# Create a primary key for signing/certifying (ed25519), valid for 1 year
gpg --batch --yes \
  --pinentry-mode loopback \
  --passphrase "$PASSPHRASE" \
  --quick-generate-key "$USER_ID" ed25519 sign,cert 1y

# Extract fingerprint for the newest primary secret key created by this run
FPR="$(
  gpg --batch --with-colons --list-secret-keys --fingerprint "$USER_ID" | awk -F: -v start="$START_TS" '
    $1=="sec" {sec_created=$6; next}
    $1=="fpr" && sec_created >= start {
      if (sec_created > max) {max=sec_created; fpr=$10}
    }
    END {print fpr}
  '
)"

if [[ -z "${FPR:-}" ]]; then
  echo "ERROR: Could not determine fingerprint for: $USER_ID" >&2
  exit 2
fi

# Add an encryption subkey (cv25519), valid for 1 year
gpg --batch --yes \
  --pinentry-mode loopback \
  --passphrase "$PASSPHRASE" \
  --quick-add-key "$FPR" cv25519 encr 1y

echo -n "$FPR" > "$OUTDIR/fingerprint.txt"

# Export public and private keys (ASCII-armored)
gpg --armor --export "$FPR" > "$OUTDIR/public.asc"
gpg --armor --export-secret-keys "$FPR" > "$OUTDIR/private.asc"

# Helpful output
cat <<EOF

Done.
Output directory: $OUTDIR

Files created:
  - $OUTDIR/public.asc        (add to GitHub: Settings -> SSH and GPG keys -> New GPG key)
  - $OUTDIR/private.asc       (store securely; use in CI secrets)
  - $OUTDIR/passphrase.txt    (store securely; use in CI secrets if needed)
  - $OUTDIR/fingerprint.txt   (use for git config user.signingkey)

Fingerprint:
  $FPR

IMPORTANT:
  Never commit private.asc or passphrase.txt to a repo.
EOF
