#!/usr/bin/env python3
"""Read and format today's daily status for Slack.

Reads YYYY-MM-DD.md from the daily-status directory, strips Jekyll
frontmatter, converts markdown to Slack mrkdwn format, and outputs
the formatted message to stdout.
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

STATUS_DIR = Path.home() / "work" / "src" / "github" / "daily-status"

SECTION_MAP = {
    "## Accomplishments": ":rocket: *Accomplishments*",
    "## Risks & Challenges": ":rotating_light: *Risks & Challenges*",
    "## Key Effort": ":person_climbing: *Key Effort*",
}


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


def strip_frontmatter(content):
    """Remove Jekyll frontmatter (--- blocks) from content."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip("\n")
    return content


def strip_title(content):
    """Remove the '# Daily Status - YYYY-MM-DD' heading."""
    lines = content.split("\n")
    result = []
    for line in lines:
        if re.match(r"^# Daily Status", line):
            continue
        result.append(line)
    return "\n".join(result).lstrip("\n")


def markdown_to_slack(content):
    """Convert markdown formatting to Slack mrkdwn."""
    lines = content.split("\n")
    result = []

    for line in lines:
        # Convert section headers
        for md_header, slack_header in SECTION_MAP.items():
            if line.strip() == md_header:
                line = slack_header
                break

        # Convert markdown links [text](url) to Slack <url|text>
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", line)

        # Convert bold **text** to Slack *text*
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)

        result.append(line)

    return "\n".join(result)


def format_status(target_date=None):
    """Read and format the daily status file for the given date."""
    if target_date is None:
        target_date = datetime.now()

    date_str = target_date.strftime("%Y-%m-%d")
    status_file = STATUS_DIR / f"{date_str}.md"

    if not status_file.exists():
        notify(
            "Slack Status: No Status File",
            f"No daily status file found for {date_str}\n"
            f"Expected: {status_file}",
        )
        print(f"Error: No status file found: {status_file}", file=sys.stderr)
        sys.exit(1)

    content = status_file.read_text()
    content = strip_frontmatter(content)
    content = strip_title(content)
    content = markdown_to_slack(content)

    # Clean up excessive blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = content.strip()

    return f"*Automated Daily Status Report*\n\n{content}"


def main():
    message = format_status()
    print(message)


if __name__ == "__main__":
    main()
