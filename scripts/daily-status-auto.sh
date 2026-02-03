#!/bin/bash
# Complete automation: publish to GitHub + post to Slack

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Daily Status Automation Starting..."
echo ""

# Step 1: Publish to GitHub Pages
echo "📝 Step 1: Publishing status to GitHub Pages..."
"$SCRIPT_DIR/publish-daily-status.sh"

echo ""

# Step 2: Post link to Slack
echo "💬 Step 2: Posting link to Slack thread..."
"$SCRIPT_DIR/post-status-link-to-slack.sh"

echo ""
echo "🎉 Done! Your daily status has been published and posted to Slack."
