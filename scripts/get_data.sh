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

# Never move someone else'"'"'s working checkout out from under them: the sensor
# repository shares this directory, and it also writes pressure_volumes.csv into
# data/derived_data/ (gitignored there). Refuse rather than discard.
if [ -n "$(git -C "$DATA" status --porcelain --untracked-files=no)" ]; then
  echo "ERROR: $DATA has uncommitted changes to tracked files." >&2
  echo "Commit or stash them, then re-run. Refusing to check out $REF over them." >&2
  exit 1
fi

git -C "$DATA" fetch --tags origin
if [ "$(git -C "$DATA" rev-parse HEAD)" != "$(git -C "$DATA" rev-parse "$REF")" ]; then
  echo "Checking out the pinned dataset revision $REF (leaves a detached HEAD)..."
  git -C "$DATA" checkout --detach "$REF"
fi

echo "Building derived data (~15 s)..."
python3 "$DATA/src/derive.py" --quiet
