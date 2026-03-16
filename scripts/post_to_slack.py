#!/usr/bin/env python3
"""Post daily status to the OSAC Slack thread.

Orchestrator that finds today's status thread, formats the daily
status file, and posts it as a thread reply.

Retries on network errors every 15 minutes, up to 4 attempts.
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from find_status_thread import (
    read_token_file, find_thread, get_my_user_id, check_already_posted,
    CONFIG_DIR, CHANNEL_ID,
)
from prepare_status_message import format_status

SLACK_API_BASE = "https://slack.com/api"
LOG_FILE = "/tmp/daily-status-slack.log"
MAX_RETRIES = 4
RETRY_INTERVAL = 900  # 15 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)
log = logging.getLogger(__name__)


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


def post_message(token, d_cookie, channel, thread_ts, text):
    """Post a message to a Slack thread."""
    data = urllib.parse.urlencode({
        "token": token,
        "channel": channel,
        "thread_ts": thread_ts,
        "text": text,
    }).encode()

    req = urllib.request.Request(
        f"{SLACK_API_BASE}/chat.postMessage",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"d={d_cookie}",
        },
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def is_network_error(exc):
    """Check if an exception is a network/DNS error worth retrying."""
    if isinstance(exc, urllib.error.URLError):
        reason = str(getattr(exc, "reason", ""))
        return any(s in reason for s in [
            "name resolution",
            "Name or service not known",
            "Temporary failure",
            "Network is unreachable",
            "Connection refused",
            "Connection timed out",
            "Connection reset",
        ])
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return False


def run():
    """Execute the posting logic. Returns True on success, False on failure."""
    token = read_token_file(CONFIG_DIR / "xoxc_token")
    d_cookie = read_token_file(CONFIG_DIR / "d_cookie")

    log.info("Finding today's status thread...")
    try:
        thread_ts = find_thread(token, d_cookie)
    except SystemExit:
        log.error("Failed to find status thread — skipping")
        notify(
            "Slack Status: Thread Not Found",
            "Could not find today's daily status thread.\n"
            "The status was not posted.",
        )
        return True  # Not a retryable error

    log.info("Found thread: %s", thread_ts)

    log.info("Checking if already posted...")
    user_id = get_my_user_id(token, d_cookie)
    if user_id and check_already_posted(token, d_cookie, thread_ts, user_id):
        log.info("Already posted to this thread — skipping")
        return True

    log.info("Formatting daily status...")
    try:
        message = format_status()
    except SystemExit:
        log.error("Failed to format status message")
        return True  # Not a retryable error

    log.info("Posting to Slack thread...")
    result = post_message(token, d_cookie, CHANNEL_ID, thread_ts, message)

    if not result.get("ok"):
        error = result.get("error", "unknown error")
        log.error("Failed to post: %s", error)
        notify(
            "Slack Status: Post Failed",
            f"Failed to post daily status: {error}",
        )
        return True  # API error, not a network error

    ts = result.get("ts", "")
    permalink = (
        f"https://redhat.enterprise.slack.com/archives/"
        f"{CHANNEL_ID}/p{ts.replace('.', '')}"
    )
    log.info("Posted successfully!")
    log.info("View in Slack: %s", permalink)
    return True


def main():
    for attempt in range(1, MAX_RETRIES + 1):
        log.info("=" * 50)
        log.info("Starting daily status post (attempt %d/%d)", attempt, MAX_RETRIES)

        try:
            success = run()
            if success:
                log.info("=" * 50)
                return
        except Exception as exc:
            if is_network_error(exc):
                log.warning("Network error: %s", exc)
                if attempt < MAX_RETRIES:
                    log.info("Retrying in %d minutes...", RETRY_INTERVAL // 60)
                    time.sleep(RETRY_INTERVAL)
                    continue
                else:
                    log.error("All %d attempts failed due to network errors", MAX_RETRIES)
                    notify(
                        "Slack Status: Network Error",
                        f"Failed to post daily status after {MAX_RETRIES} attempts.\n"
                        "Check network connectivity.",
                    )
                    sys.exit(1)
            else:
                log.error("Unexpected error: %s", exc, exc_info=True)
                notify(
                    "Slack Status: Error",
                    f"Unexpected error: {exc}",
                )
                sys.exit(1)

        log.info("=" * 50)


if __name__ == "__main__":
    main()
