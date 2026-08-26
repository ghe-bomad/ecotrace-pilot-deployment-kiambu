#!/usr/bin/env bash
# Clone or update the companion dataset at the revision pinned in DATA_VERSION,
# then build its derived data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${ECOTRACE_DATA:-$(dirname "$ROOT")/ecotrace-pilot-data-kiambu}"
REF="$(tr -d '[:space:]' < "$ROOT/DATA_VERSION")"

if [ ! -d "$DATA/.git" ]; then
  echo "Cloning the dataset into $DATA (207 MB of Parquet; this takes a while)..."
  git clone https://github.com/ghe-bomad/ecotrace-pilot-data-kiambu "$DATA"
fi
git -C "$DATA" fetch --tags origin
git -C "$DATA" checkout "$REF"

echo "Building derived data (~40 s)..."
python3 "$DATA/src/derive.py"
