#!/usr/bin/env bash
# Run functional smoke + read-only load against both salons.
set -euo pipefail
cd "$(dirname "$0")/.."

export QA_HOST="${QA_HOST:-92.246.128.94}"
export QA_KASKAD_PW="${QA_KASKAD_PW:-kaskad2026}"
export QA_HAIROS_PW="${QA_HAIROS_PW:-hairos2026}"

echo "=== 1/2 Functional smoke ==="
python3 qa_auto/smoke_api.py
SMOKE=$?

echo "=== 2/2 Load read-only (kaskad :8000) ==="
python3 qa_auto/load_read.py --workers "${QA_LOAD_WORKERS:-50}" --seconds "${QA_LOAD_SECONDS:-15}"
LOAD=$?

if [[ $SMOKE -eq 0 && $LOAD -eq 0 ]]; then
  echo "ALL PASS"
  exit 0
fi
echo "FAIL smoke=$SMOKE load=$LOAD"
exit 1
