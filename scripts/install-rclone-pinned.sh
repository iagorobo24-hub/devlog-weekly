#!/usr/bin/env bash
# Install the rclone build exercised by the local backend tests.
# No root, curl|bash, mutable 'latest' or unauthenticated installation script.
set -euo pipefail

version="1.75.0"
sha256="aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa"
case "$(uname -m)" in
    x86_64) arch="amd64" ;;
    *) echo "Unsupported runner architecture for pinned rclone: $(uname -m)" >&2; exit 2 ;;
esac

name="rclone-v${version}-linux-${arch}"
temp_dir="$(mktemp -d)"
trap 'rm -rf -- "$temp_dir"' EXIT
archive="$temp_dir/$name.zip"
curl --fail --location --silent --show-error --retry 3 \
    "https://downloads.rclone.org/v${version}/${name}.zip" --output "$archive"
(
    cd "$temp_dir"
    printf '%s  %s\n' "$sha256" "$name.zip" | sha256sum --check --status
)
unzip -q "$archive" "$name/rclone" -d "$temp_dir"
destination="${RCLONE_INSTALL_DIR:-$HOME/.local/bin}"
mkdir -p "$destination"
install -m 0755 "$temp_dir/$name/rclone" "$destination/rclone"
"$destination/rclone" version | head -n 1
if [[ -n "${GITHUB_PATH:-}" ]]; then
    printf '%s\n' "$destination" >> "$GITHUB_PATH"
fi
