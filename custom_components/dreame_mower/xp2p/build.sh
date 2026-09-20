#!/usr/bin/env bash
#
# Builds the live video helper. Runs inside a throwaway Ubuntu 24.04 container
# started by install.sh; see README.md for what it downloads and why.
#
# Reads /src (this directory, read-only) and writes the finished bundle to /out.
#
# SPDX-License-Identifier: MIT
set -euo pipefail

SDK_VERSION="v2.4.72"
SDK_URL="https://github.com/tencentyun/iot-p2p-build/releases/download/${SDK_VERSION}/xp2p_linux.zip"
SDK_SHA256="cdfbb92fdd7dd1931369f5ea348b12085384247a264372619fd75e585ccf5d91"

SRC="${SRC:-/src}"
OUT="${OUT:-/out}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ "$(uname -m)" != "x86_64" ]; then
  echo "error: live video needs an x86_64 host; this is $(uname -m)." >&2
  echo "       The vendor publishes no build for other architectures." >&2
  exit 1
fi

echo "==> installing build tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends gcc g++ libc6-dev curl ca-certificates unzip >/dev/null

echo "==> downloading the transport library (${SDK_VERSION})"
curl -fsSL "$SDK_URL" -o "$WORK/sdk.zip"

echo "==> verifying checksum"
echo "${SDK_SHA256}  ${WORK}/sdk.zip" | sha256sum -c - >/dev/null

unzip -q "$WORK/sdk.zip" -d "$WORK/sdk"
SDK_DIR="$(dirname "$(find "$WORK/sdk" -type d -name Release -path '*linux*' | head -1)")/Release"
INC_DIR="$(dirname "$(find "$WORK/sdk" -name appWrapper.h | head -1)")"
[ -d "$SDK_DIR" ] && [ -d "$INC_DIR" ] || { echo "error: unexpected archive layout" >&2; exit 1; }

echo "==> compiling the helper"
# The archives carry GCC 13 LTO bytecode, which is why this runs on Ubuntu 24.04.
# They also emit a wall of warnings from their own vendored sources, so the
# build log is kept aside and only shown when something actually fails.
gcc -Wall -Wextra -O2 -I"$INC_DIR" -o "$WORK/xp2p-runner" "$SRC/runner.c" \
  -L"$SDK_DIR" \
  -lapp_interface -lenet-core -lcurl -lz \
  -levent_extra -levent_core -levent_mbedtls -levent_pthreads \
  -ltinyxml2 -lminizip -lmbedtls -lmbedcrypto -lmbedx509 \
  -lpthread -lstdc++ -lm 2>"$WORK/build.log" || { cat "$WORK/build.log" >&2; exit 1; }

echo "==> collecting the C runtime"
# Home Assistant's container uses musl, so the helper brings its own loader and
# libc and is started through them. Nothing is linked into Home Assistant.
mkdir -p "$WORK/bundle/lib"
cp "$WORK/xp2p-runner" "$WORK/bundle/"
for name in ld-linux-x86-64.so.2 libc.so.6 libm.so.6 libstdc++.so.6 \
            libgcc_s.so.1 libnss_dns.so.2 libnss_files.so.2 libresolv.so.2; do
  path="$(find /lib /usr/lib -name "$name" 2>/dev/null | head -1)"
  [ -n "$path" ] || { echo "error: missing $name" >&2; exit 1; }
  cp -L "$path" "$WORK/bundle/lib/"
done

cat > "$WORK/bundle/manifest.json" <<EOF
{
  "sdk_version": "${SDK_VERSION}",
  "sdk_sha256": "${SDK_SHA256}",
  "runner_sha256": "$(sha256sum "$WORK/xp2p-runner" | cut -d' ' -f1)",
  "arch": "x86_64",
  "loader": "lib/ld-linux-x86-64.so.2",
  "executable": "xp2p-runner",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

mkdir -p "$OUT"
rm -rf "${OUT:?}/lib" "${OUT:?}/xp2p-runner" "${OUT:?}/manifest.json"
cp -r "$WORK/bundle/." "$OUT/"
chmod -R a+rX "$OUT"

echo "==> done: $(du -sh "$OUT" | cut -f1) in $OUT"
