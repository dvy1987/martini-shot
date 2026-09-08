#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build