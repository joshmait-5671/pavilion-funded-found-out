#!/bin/bash
# Install Hyped & Found Out launchd jobs.
#
# Run ONCE when you're back at the MacBook:
#   bash launchd/install.sh
#
# What this does:
#   1. Removes the 3 dead cron entries (Sequoia silently breaks cron).
#   2. Copies the 2 plists to ~/Library/LaunchAgents/.
#   3. Loads them with launchctl. Schedules will be:
#        - Mon 9am ET — pipeline (discovery + grade + render)
#        - Wed 5pm ET — delivery (email the PDF)
#   4. Prints job status so you can confirm.
#
# Constraint: the MacBook must be AWAKE at Mon 9am ET and Wed 5pm ET for the
# jobs to fire. If sleep is a problem long-term, copy the plists to the iMac
# (always-on) and run this script there instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
PIPELINE_PLIST="com.pavilion.hyped-pipeline.plist"
DELIVERY_PLIST="com.pavilion.hyped-delivery.plist"

echo "── 1. Pull dead crontab entries ──────────────────────────────────"
crontab -l 2>/dev/null | grep -v "funded-and-found-out" | crontab -
echo "  done. remaining crontab:"
crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" || echo "  (empty)"

echo ""
echo "── 2. Install plists ─────────────────────────────────────────────"
mkdir -p "$AGENT_DIR"
cp "$SCRIPT_DIR/$PIPELINE_PLIST" "$AGENT_DIR/"
cp "$SCRIPT_DIR/$DELIVERY_PLIST" "$AGENT_DIR/"
echo "  copied to $AGENT_DIR/"

echo ""
echo "── 3. Load with launchctl ────────────────────────────────────────"
# Bootout first in case they were already loaded — bootout failures are fine
launchctl bootout "gui/$(id -u)/com.pavilion.hyped-pipeline" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.pavilion.hyped-delivery" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT_DIR/$PIPELINE_PLIST"
launchctl bootstrap "gui/$(id -u)" "$AGENT_DIR/$DELIVERY_PLIST"
echo "  loaded."

echo ""
echo "── 4. Verify ─────────────────────────────────────────────────────"
launchctl print "gui/$(id -u)/com.pavilion.hyped-pipeline" | grep -E "(state|next run)" || true
launchctl print "gui/$(id -u)/com.pavilion.hyped-delivery" | grep -E "(state|next run)" || true

echo ""
echo "── Done. ─────────────────────────────────────────────────────────"
echo "Next scheduled fires:"
echo "  pipeline: next Monday 9:00 ET"
echo "  delivery: next Wednesday 5:00 PM ET"
echo ""
echo "To uninstall later:"
echo "  launchctl bootout gui/\$(id -u)/com.pavilion.hyped-pipeline"
echo "  launchctl bootout gui/\$(id -u)/com.pavilion.hyped-delivery"
echo "  rm $AGENT_DIR/com.pavilion.hyped-*.plist"
