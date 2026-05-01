#!/bin/bash
# Funded & Found Out — Wednesday 5pm email send.
# Sends the latest `funded-and-found-out-YYYY-MM-DD.pdf` from output/ to Josh.

set -euo pipefail

PROJECT_DIR="/Users/joshmait/Desktop/Claude/pavilion/funded-and-found-out"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cron-wednesday-$(date +%Y-%m-%d).log"

{
  echo "=== Wednesday delivery start: $(date) ==="
  "$PROJECT_DIR/.venv/bin/python" scripts/run_delivery.py
  echo "=== Wednesday delivery end: $(date) ==="
} >> "$LOG_FILE" 2>&1
