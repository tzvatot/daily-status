#!/bin/bash
set -e

# Source bashrc for claude CLI and environment
source ~/.bashrc_elad

REPO_DIR="$HOME/work/src/github/daily-status"
DAILY_FILES_DIR="$HOME/.claude/plans"

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
        echo "❌ Invalid date: $1"
        echo "   Use format: YYYY-MM-DD or relative dates like 'yesterday'"
        exit 1
    fi
else
    REPORT_DATE=$(date +%Y-%m-%d)
fi

echo "📅 Publishing status for: $REPORT_DATE"

# Find daily status file for the specified date
DAILY_FILE=$(ls -t "$DAILY_FILES_DIR"/daily-status-${REPORT_DATE}*.md 2>/dev/null | head -1)

if [[ -z "$DAILY_FILE" ]]; then
    echo "❌ No daily status file found for $REPORT_DATE"
    echo "   Expected: $DAILY_FILES_DIR/daily-status-${REPORT_DATE}*.md"
    exit 1
fi

echo "📝 Found daily status: $(basename "$DAILY_FILE")"

# Check for Claude CLI
if ! command -v claude &> /dev/null; then
    echo "❌ Claude CLI not found"
    echo "   Please ensure ~/.bashrc_elad is sourced and claude is in PATH"
    exit 1
fi

echo "🤖 Asking Claude to format the daily status..."

# Create prompt file in repo directory (claude CLI can access this)
PROMPT_FILE="$REPO_DIR/.claude-prompt-temp.md"
cat > "$PROMPT_FILE" <<'PROMPTEOF'
Reformat the daily status report below into this exact structure. Output ONLY the markdown sections shown below. Do NOT include any preamble, explanation, commentary, or notes about what you're doing. Start directly with "## Accomplishments":

## Accomplishments
[Bullet points of key things completed today]

## Risks & Challenges
[Any blockers, issues, or concerns - or "None"]

## Key Effort
[One sentence describing main focus area]

## Related Links
[GitHub PRs, Jira tickets, etc. as bullet points - convert MGMT-XXXXX to [MGMT-XXXXX](https://issues.redhat.com/browse/MGMT-XXXXX)]

Daily status content:

PROMPTEOF

# Append the daily status content
cat "$DAILY_FILE" >> "$PROMPT_FILE"

# Get Claude to reformat it
FORMATTED_CONTENT=$(claude --print "$(cat "$PROMPT_FILE")" 2>/dev/null)

# Cleanup temp file
rm "$PROMPT_FILE"

if [[ -z "$FORMATTED_CONTENT" ]]; then
    echo "❌ Failed to get response from Claude"
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

echo "✅ Formatted by Claude"

# Commit and push to GitHub
cd "$REPO_DIR"
git add "${REPORT_DATE}.md"

if git diff --cached --quiet; then
    echo "⚠️  No changes to commit (status already published)"
    exit 0
fi

git commit -m "Daily status update - $REPORT_DATE"
git push origin main

echo "✅ Published to GitHub"
echo "🔗 URL: https://tzvatot.github.io/daily-status/${REPORT_DATE}"
