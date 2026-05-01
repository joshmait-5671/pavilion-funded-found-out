#!/bin/bash
# Funded & Found Out — Monday morning pipeline.
# Discovery (Gmail) → qualify → analyze → render PDF.
# Wednesday email send is handled by a separate cron entry calling run_delivery.py.

set -euo pipefail

PROJECT_DIR="/Users/joshmait/Desktop/Claude/pavilion/funded-and-found-out"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cron-monday-$(date +%Y-%m-%d).log"

{
  echo "=== Monday pipeline start: $(date) ==="
  "$PROJECT_DIR/.venv/bin/python" scripts/run_pipeline.py
  echo "=== Monday pipeline end: $(date) ==="
} >> "$LOG_FILE" 2>&1
