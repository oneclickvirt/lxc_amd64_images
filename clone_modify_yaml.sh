#!/usr/bin/env bash
# Refresh in an isolated stage; failed upstream updates retain valid definitions.
set -euo pipefail
repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "${CI_IMAGE_PYTHON:-python3}" "$repository_root/.github/scripts/refresh_image_sources.py" --repository lxc_amd64_images
