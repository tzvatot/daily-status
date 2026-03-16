#!/usr/bin/env python3
"""Find today's OSAC daily status thread in Slack.

Authenticates using xoxc token + d cookie from ~/.config/slack/,
searches channel C08ESMFV85Q for the daily status request message,
and prints the thread timestamp (thread_ts) to stdout.
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

CHANNEL_ID = "C08ESMFV85Q"
SEARCH_TEXT = "Please update your daily status"
CONFIG_DIR = Path.home() / ".config" / "slack"
SLACK_API_BASE = "https://slack.com/api"


def notify(title, message):
    """Send a desktop notification."""
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    uid = os.getuid()
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    try:
        subprocess.run(
            ["notify-send", "-u", "critical", title, message],
            env=env,
            check=False,
        )
    except FileNotFoundError:
        pass


def read_token_file(path):
    """Read and return the contents of a token file, stripped of whitespace."""
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        notify(
            "Slack Status: Missing Token",
            f"Token file not found: {path}\n"
            "Extract tokens from Chrome DevTools Network tab.",
        )
        print(f"Error: Token file not found: {path}", file=sys.stderr)
        sys.exit(1)


def slack_api_call(method, token, d_cookie, params):
    """Make a Slack API call with xoxc token and d cookie."""
    params["token"] = token
    data = urllib.parse.urlencode(params).encode()

    req = urllib.request.Request(
        f"{SLACK_API_BASE}/{method}",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"d={d_cookie}",
        },
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_my_user_id(token, d_cookie):
    """Get the authenticated user's Slack user ID."""
    result = slack_api_call("auth.test", token, d_cookie, {})
    if not result.get("ok"):
        return None
    return result.get("user_id")


def check_already_posted(token, d_cookie, thread_ts, user_id):
    """Check if the user has already posted a reply in the thread."""
    result = slack_api_call("conversations.replies", token, d_cookie, {
        "channel": CHANNEL_ID,
        "ts": thread_ts,
        "limit": "100",
    })

    if not result.get("ok"):
        return False

    for msg in result.get("messages", []):
        # Skip the parent message itself
        if msg.get("ts") == thread_ts:
            continue
        if msg.get("user") == user_id:
            return True

    return False


def find_thread(token, d_cookie, target_date=None):
    """Find the daily status thread for the given date (defaults to today)."""
    if target_date is None:
        target_date = datetime.now()

    day_start = datetime(
        target_date.year, target_date.month, target_date.day,
        tzinfo=timezone.utc,
    )
    day_end = datetime(
        target_date.year, target_date.month, target_date.day,
        23, 59, 59, tzinfo=timezone.utc,
    )

    result = slack_api_call("conversations.history", token, d_cookie, {
        "channel": CHANNEL_ID,
        "oldest": str(day_start.timestamp()),
        "latest": str(day_end.timestamp()),
        "limit": "50",
    })

    if not result.get("ok"):
        error = result.get("error", "unknown error")
        if error in ("invalid_auth", "not_authed", "token_expired", "token_revoked"):
            notify(
                "Slack Status: Token Expired",
                "Your Slack tokens have expired.\n"
                "Re-extract from Chrome DevTools Network tab\n"
                "and update files in ~/.config/slack/",
            )
        print(f"Error: Slack API error: {error}", file=sys.stderr)
        sys.exit(1)

    messages = result.get("messages", [])
    for msg in messages:
        text = msg.get("text", "")
        if SEARCH_TEXT in text:
            return msg["ts"]

    print(
        f"Error: No daily status thread found for "
        f"{target_date.strftime('%Y-%m-%d')}",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    token = read_token_file(CONFIG_DIR / "xoxc_token")
    d_cookie = read_token_file(CONFIG_DIR / "d_cookie")

    thread_ts = find_thread(token, d_cookie)
    print(thread_ts)


if __name__ == "__main__":
    main()
