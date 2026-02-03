#!/bin/bash
set -e

# Configuration
SLACK_TOKEN=$(cat ~/.slack_token 2>/dev/null || echo "")
CHANNEL_ID="C0A8KATCJ59"  # osac-daily-status channel
GITHUB_PAGES_URL="https://tzvatot.github.io/daily-status"

# Accept optional date parameter (defaults to today)
# Usage: ./post-status-link-to-slack.sh [YYYY-MM-DD]
if [[ -n "$1" ]]; then
    REPORT_DATE=$(date -d "$1" +%Y-%m-%d 2>/dev/null)
    if [[ -z "$REPORT_DATE" ]]; then
        echo "❌ Invalid date: $1"
        exit 1
    fi
else
    REPORT_DATE=$(date +%Y-%m-%d)
fi

echo "📅 Posting status link for: $REPORT_DATE"
STATUS_URL="${GITHUB_PAGES_URL}/${REPORT_DATE}"

if [[ -z "$SLACK_TOKEN" ]]; then
    echo "❌ Slack token not found"
    echo ""
    echo "Please create a Slack token and save it to ~/.slack_token"
    echo ""
    echo "Steps:"
    echo "1. Go to https://api.slack.com/apps"
    echo "2. Create new app or use existing"
    echo "3. Add Bot Token Scopes: chat:write, channels:history, channels:read"
    echo "4. Install app to workspace"
    echo "5. Invite bot to #osac-daily-status channel: /invite @your-bot-name"
    echo "6. Copy 'Bot User OAuth Token' (starts with xoxb-)"
    echo "7. Save to file: echo 'xoxb-YOUR-TOKEN' > ~/.slack_token"
    echo "8. Set permissions: chmod 600 ~/.slack_token"
    exit 1
fi

echo "🔍 Finding OSAC daily status thread for $REPORT_DATE..."

# Find standup thread for the specified date
REPORT_START=$(date -d "$REPORT_DATE 00:00:00" +%s)
REPORT_END=$(date -d "$REPORT_DATE 23:59:59" +%s)

RESPONSE=$(curl -s -X GET "https://slack.com/api/conversations.history" \
  -H "Authorization: Bearer ${SLACK_TOKEN}" \
  -d "channel=${CHANNEL_ID}" \
  -d "oldest=${REPORT_START}" \
  -d "latest=${REPORT_END}" \
  -d "limit=50")

# Check for API errors
if ! echo "$RESPONSE" | jq -e '.ok' > /dev/null 2>&1; then
    echo "❌ Slack API error:"
    echo "$RESPONSE" | jq -r '.error' 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

# Find message containing "Please update your daily status"
THREAD_TS=$(echo "$RESPONSE" | jq -r '.messages[] | select(.text | contains("Please update your daily status")) | .ts' | head -1)

if [[ -z "$THREAD_TS" ]]; then
    echo "❌ Could not find today's OSAC daily status thread"
    echo "   Searched in channel C0A8KATCJ59 for messages containing 'Please update your daily status'"
    echo ""
    echo "Debug: Messages found today:"
    echo "$RESPONSE" | jq -r '.messages[].text' | head -5
    exit 1
fi

echo "✅ Found thread: $THREAD_TS"

# Create message
MESSAGE="📊 *Daily Status Update*

View my full status report: ${STATUS_URL}"

echo "📤 Posting to Slack thread..."

# Post to thread
POST_RESPONSE=$(curl -s -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer ${SLACK_TOKEN}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @- <<JSONEOF
{
  "channel": "${CHANNEL_ID}",
  "thread_ts": "${THREAD_TS}",
  "text": $(jq -Rs . <<< "$MESSAGE"),
  "unfurl_links": true
}
JSONEOF
)

# Check response
if echo "$POST_RESPONSE" | jq -e '.ok' > /dev/null; then
    echo "✅ Posted successfully!"
    echo "🔗 View in Slack: https://redhat.enterprise.slack.com/archives/${CHANNEL_ID}/p${THREAD_TS//./}"
else
    echo "❌ Failed to post:"
    echo "$POST_RESPONSE" | jq -r '.error'
    exit 1
fi
