#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
cd "${SCRIPT_DIR}"

NAME="kinesis-freestyle2-mac-hid-bpf"
VERSION="${VERSION:-1.0.0}"
IMAGE="${IMAGE:-${NAME}-build:${VERSION}}"
OUTPUT_DIR="${OUTPUT_DIR:-${SCRIPT_DIR}/output}"

TARBALL="${NAME}-${VERSION}.tar.gz"

# Build the source tarball from the current HEAD.
git archive --format=tar.gz \
  --prefix="${NAME}-${VERSION}/" \
  -o "${TARBALL}" \
  HEAD

trap 'rm -f "${SCRIPT_DIR}/${TARBALL}"' EXIT

# vmlinux.h is generated inside the container from /sys/kernel/btf/vmlinux,
# which podman passes through from the host.
podman build \
  --build-arg "VERSION=${VERSION}" \
  -t "${IMAGE}" \
  -f Containerfile \
  .

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

CID="$(podman create "${IMAGE}")"
trap 'podman rm -f "${CID}" >/dev/null 2>&1 || true; rm -f "${SCRIPT_DIR}/${TARBALL}"' EXIT
podman cp "${CID}:/output/." "${OUTPUT_DIR}/"

echo "RPMs written to ${OUTPUT_DIR}:"
ls -1 "${OUTPUT_DIR}"
