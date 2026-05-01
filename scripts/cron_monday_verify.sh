#!/bin/bash
# Funded & Found Out — Monday-afternoon verification.
# Fires at 12pm ET Monday, ~3 hours after the 9am pipeline.
# Reads the morning log, decides outcome, emails Josh a one-line status.

set -euo pipefail

PROJECT_DIR="/Users/joshmait/Desktop/Claude/pavilion/funded-and-found-out"
cd "$PROJECT_DIR"

DATE=$(date +%Y-%m-%d)
LOG="$PROJECT_DIR/logs/cron-monday-$DATE.log"

if [ ! -f "$LOG" ]; then
  STATUS="❌ silent failure — no log file written. Pipeline did not run."
elif grep -q "✅ Done" "$LOG" 2>/dev/null; then
  STATUS="✅ PDF generated. Wednesday cron will email it at 5pm."
elif grep -q "below the .* floor" "$LOG" 2>/dev/null; then
  COUNT=$(grep -oE "Only [0-9]+ qualified" "$LOG" | head -1 | grep -oE "[0-9]+")
  STATUS="📝 curation prompt sent — only ${COUNT:-?} qualified candidate(s). Edit data/episodes/$DATE.json to ship."
elif grep -q "ANTHROPIC_API_KEY not set" "$LOG" 2>/dev/null; then
  STATUS="❌ ANTHROPIC_API_KEY missing in .env"
elif grep -q "Gmail auth failed" "$LOG" 2>/dev/null; then
  STATUS="❌ Gmail auth failed — re-run scripts/auth_gmail.py for affected account"
else
  STATUS="⚠️ unclear outcome — check $LOG manually"
fi

"$PROJECT_DIR/.venv/bin/python" - <<PYEOF
import os, sys, base64
from email.mime.text import MIMEText
from pathlib import Path
sys.path.insert(0, "$PROJECT_DIR")
from src.delivery.emailer import get_gmail_service

svc = get_gmail_service(Path("$PROJECT_DIR") / "auth")
msg = MIMEText(
    "FFO Monday verification — $DATE\n\n$STATUS\n\nLog: $LOG\n",
    "plain",
)
msg["From"] = "josh.mait@gmail.com"
msg["To"] = "josh.mait@gmail.com"
msg["Subject"] = "FFO Mon $DATE: $STATUS"
raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
svc.users().messages().send(userId="me", body={"raw": raw}).execute()
print("Verification email sent")
PYEOF
