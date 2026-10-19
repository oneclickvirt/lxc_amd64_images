#!/usr/bin/env bash
# The stable Snap is 3.1 and cannot load the current OpenWrt definition.
set -euo pipefail

version=3.4.0
digest=c2c2845691a5f29a93ccbf1af0cacf64ebe3877234969114928736ddbbb47aad
task_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/distrobuilder.XXXXXXXX")
trap 'rm -rf -- "$task_dir"' EXIT

curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 \
  --retry 3 --retry-max-time 240 --retry-connrefused \
  "https://github.com/lxc/distrobuilder/releases/download/v${version}/distrobuilder-${version}.tar.gz" \
  -o "$task_dir/source.tar.gz"
printf '%s  %s\n' "$digest" "$task_dir/source.tar.gz" | sha256sum --check --status
tar -xzf "$task_dir/source.tar.gz" -C "$task_dir"

# Oracle's official OL8 ISO uses the same versioned filename as OL9/OL10.
# The upstream 3.4.0 iteration fallback only recognizes the latter two.
python3 - "$task_dir/distrobuilder-${version}/sources/oraclelinux-http.go" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
source = path.read_text()
before = 'if s.definition.Image.Release == "9" || s.definition.Image.Release == "10" {'
after = 'if s.definition.Image.Release == "8" || s.definition.Image.Release == "9" || s.definition.Image.Release == "10" {'
if source.count(before) != 1:
    raise SystemExit('Oracle ISO compatibility patch does not match the verified source')
path.write_text(source.replace(before, after))
path = path.with_name('centos-http.go')
source = path.read_text()
before = 'https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/'
if source.count(before) != 2:
    raise SystemExit('CentOS repository compatibility patch does not match the verified source')
path.write_text(source.replace(before, 'https://mirror.stream.centos.org/'))
PY

sudo apt-get update
sudo apt-get install -y build-essential debootstrap rsync gpg squashfs-tools xz-utils umoci btrfs-progs dosfstools qemu-utils parted
(
  cd "$task_dir/distrobuilder-${version}"
  # The verified release contains vendored modules. Building cannot select a
  # different dependency graph or depend on a live module proxy.
  export GOFLAGS=-mod=vendor
  # The upstream source fixtures contain a historical signing key which can
  # expire independently of the builder. Compile the package here; runtime
  # image builds still enforce each source's current signature/checksum.
  timeout --kill-after=30s 600s go test -run '^$' -tags=containers_image_storage_stub,containers_image_docker_daemon_stub,containers_image_openpgp ./sources
  go build -trimpath \
    -tags=containers_image_storage_stub,containers_image_docker_daemon_stub,containers_image_openpgp \
    -o "$task_dir/distrobuilder" ./distrobuilder
)
actual_version=$("$task_dir/distrobuilder" --version)
[[ "$actual_version" == *"${version}"* ]] || { echo 'Unexpected builder version' >&2; exit 1; }
sudo install -m 0755 "$task_dir/distrobuilder" /usr/local/bin/distrobuilder
/usr/local/bin/distrobuilder --version
