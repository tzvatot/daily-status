#!/bin/bash
set -e

# Source bashrc for claude CLI and environment
source ~/.bashrc_elad

REPO_DIR="$HOME/work/src/github/daily-status"
DAILY_FILES_DIR="$HOME/.claude/plans"
LOG_FILE="/tmp/daily-status-publish.log"

# Logging function - outputs to both console and log file
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$@"
    echo "[$timestamp] $@" >> "$LOG_FILE"
}

# Error handler - send notification on failure
error_handler() {
    local exit_code=$?
    log "❌ Script failed with exit code: $exit_code"

    # Send desktop notification
    DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
        notify-send -u critical "Daily Status Publish Failed" \
        "Failed to publish daily status. Check $LOG_FILE for details." 2>/dev/null || true

    exit $exit_code
}

trap error_handler ERR

# Log session start
echo "" >> "$LOG_FILE"
log "========================================="
log "Starting daily status publish"

# Accept optional date parameter (defaults to today)
# Usage: ./publish-daily-status.sh [YYYY-MM-DD]
# Examples:
#   ./publish-daily-status.sh              # publishes today
#   ./publish-daily-status.sh 2026-02-02   # publishes Feb 2
#   ./publish-daily-status.sh yesterday    # publishes yesterday
if [[ -n "$1" ]]; then
    # Allow relative dates like "yesterday"
    REPORT_DATE=$(date -d "$1" +%Y-%m-%d 2>/dev/null)
    if [[ -z "$REPORT_DATE" ]]; then
        log "❌ Invalid date: $1"
        log "   Use format: YYYY-MM-DD or relative dates like 'yesterday'"
        exit 1
    fi
else
    REPORT_DATE=$(date +%Y-%m-%d)
fi

log "📅 Publishing status for: $REPORT_DATE"

# Find daily status file for the specified date
DAILY_FILE=$(ls -t "$DAILY_FILES_DIR"/daily-status-${REPORT_DATE}*.md 2>/dev/null | head -1)

if [[ -z "$DAILY_FILE" ]]; then
    log "❌ No daily status file found for $REPORT_DATE"
    log "   Expected: $DAILY_FILES_DIR/daily-status-${REPORT_DATE}*.md"
    exit 1
fi

log "📝 Found daily status: $(basename "$DAILY_FILE")"

# Check for Claude CLI
if ! command -v claude &> /dev/null; then
    log "❌ Claude CLI not found"
    log "   Please ensure ~/.bashrc_elad is sourced and claude is in PATH"
    exit 1
fi

log "🤖 Asking Claude to format the daily status..."

# Create prompt file in repo directory (claude CLI can access this)
PROMPT_FILE="$REPO_DIR/.claude-prompt-temp.md"
cat > "$PROMPT_FILE" <<'PROMPTEOF'
Reformat the daily status report below into this exact structure. Output ONLY the markdown sections shown below. Do NOT include any preamble, explanation, commentary, or notes about what you're doing. Start directly with "## Accomplishments":

## Accomplishments
[Bullet points of key things completed today - convert ALL Jira ticket references (MGMT-XXXXX) to clickable markdown links like [MGMT-XXXXX](https://issues.redhat.com/browse/MGMT-XXXXX)]

## Risks & Challenges
[Any blockers, issues, or concerns - or "None"]

## Key Effort
[One sentence describing main focus area]

IMPORTANT: Do NOT create a "Related Links" section. All Jira tickets should be inline clickable links in the Accomplishments section.

Daily status content:

PROMPTEOF

# Append the daily status content
cat "$DAILY_FILE" >> "$PROMPT_FILE"

# Get Claude to reformat it
FORMATTED_CONTENT=$(claude --print "$(cat "$PROMPT_FILE")" 2>/dev/null)

# Cleanup temp file
rm "$PROMPT_FILE"

if [[ -z "$FORMATTED_CONTENT" ]]; then
    log "❌ Failed to get response from Claude"
    exit 1
fi

# Strip any preamble/commentary before "## Accomplishments"
FORMATTED_CONTENT=$(echo "$FORMATTED_CONTENT" | sed -n '/^## Accomplishments/,$p')

# Create the formatted file with frontmatter
FORMATTED_FILE="$REPO_DIR/${REPORT_DATE}.md"

cat > "$FORMATTED_FILE" <<EOF
---
layout: default
title: Daily Status - $REPORT_DATE
date: $REPORT_DATE
---

# Daily Status - $REPORT_DATE

$FORMATTED_CONTENT
EOF

log "✅ Formatted by Claude"

# Commit and push to GitHub
cd "$REPO_DIR"
git add "${REPORT_DATE}.md"

if git diff --cached --quiet; then
    log "⚠️  No changes to commit (status already published)"
    exit 0
fi

git commit -m "Daily status update - $REPORT_DATE"
git push origin main

log "✅ Published to GitHub"
log "🔗 URL: https://tzvatot.github.io/daily-status/${REPORT_DATE}"
log "========================================="
