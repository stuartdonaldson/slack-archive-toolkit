#!/usr/bin/env bash
# Downloads and checksum-verifies a pinned slackdump release, installs to $INSTALL_DIR.
set -euo pipefail

VERSION="v4.4.0"
INSTALL_DIR="${INSTALL_DIR:-$HOME/bin}"

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)  ASSET="slackdump_Linux_x86_64.tar.gz" ;;
    Linux-aarch64) ASSET="slackdump_Linux_arm64.tar.gz" ;;
    *) echo "install-slackdump: unsupported platform $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

BASE_URL="https://github.com/rusq/slackdump/releases/download/${VERSION}"
curl -fsSL -o "$WORKDIR/$ASSET" "$BASE_URL/$ASSET"
curl -fsSL -o "$WORKDIR/checksums.txt" "$BASE_URL/checksums.txt"

EXPECTED="$(grep "$ASSET\$" "$WORKDIR/checksums.txt" | awk '{print $1}')"
ACTUAL="$(sha256sum "$WORKDIR/$ASSET" | awk '{print $1}')"
if [[ -z "$EXPECTED" || "$EXPECTED" != "$ACTUAL" ]]; then
    echo "install-slackdump: checksum mismatch for $ASSET (expected $EXPECTED, got $ACTUAL)" >&2
    exit 1
fi

tar -xzf "$WORKDIR/$ASSET" -C "$WORKDIR" slackdump
mkdir -p "$INSTALL_DIR"
install -m 755 "$WORKDIR/slackdump" "$INSTALL_DIR/slackdump"

echo "installed slackdump $VERSION to $INSTALL_DIR/slackdump"
