#!/usr/bin/env python3
"""Summarize all active Claude Code sessions and update the daily status file.

Finds all running Claude instances, reads their session logs, uses
claude --print to summarize recent activity, and appends a timestamped
update to ~/.claude/plans/daily-status-YYYY-MM-DD.md.

Then commits and pushes to git.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PLANS_DIR = Path.home() / ".claude" / "plans"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
# Number of recent messages to feed to claude for summarization
RECENT_MESSAGES = 40


def get_active_claude_pids():
    """Find all running interactive claude processes (exclude --print)."""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True, text=True, check=False,
    )
    pids = []
    for line in result.stdout.splitlines():
        if "claude" not in line or "grep" in line:
            continue
        parts = line.split()
        pid = parts[1]
        # Reconstruct the command
        cmd = " ".join(parts[10:])
        # Skip non-claude processes, --print invocations, podman containers,
        # tail processes, and this script itself
        if not cmd.startswith("claude"):
            continue
        if "--print" in cmd:
            continue
        pids.append(pid)
    return pids


def get_pid_cwd(pid):
    """Get the working directory of a process."""
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except (OSError, FileNotFoundError):
        return None


def get_pid_terminal(pid):
    """Get the terminal of a process."""
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", pid],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_pid_start_time(pid):
    """Get the start time of a process."""
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", pid],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def cwd_to_project_dir(cwd):
    """Convert a CWD path to the Claude projects directory name."""
    # Claude uses the CWD path with / replaced by - and leading -
    project_name = cwd.replace("/", "-")
    return PROJECTS_DIR / project_name


def find_active_session(project_dir):
    """Find the most recently modified .jsonl session file."""
    if not project_dir.exists():
        return None
    jsonl_files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return jsonl_files[0] if jsonl_files else None


def extract_recent_messages(session_file, count=RECENT_MESSAGES):
    """Extract the last N user/assistant messages from a session log."""
    messages = []
    with open(session_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_type = entry.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", "")
            role = msg.get("role", msg_type)

            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            parts.append(
                                f"[tool: {block.get('name', '?')}]"
                            )
                        elif block.get("type") == "tool_result":
                            result_content = block.get("content", "")
                            if isinstance(result_content, str):
                                parts.append(f"[result: {result_content[:200]}]")
                text = "\n".join(parts)

            # Skip system reminders and empty messages
            if not text.strip() or text.strip().startswith("<system-reminder>"):
                continue

            # Truncate very long messages
            if len(text) > 500:
                text = text[:500] + "..."

            messages.append({"role": role, "text": text})

    return messages[-count:]


def summarize_session(messages, cwd, terminal, start_time):
    """Use claude --print to summarize a session's recent activity."""
    if not messages:
        return None

    conversation = []
    for msg in messages:
        role = msg["role"].upper()
        conversation.append(f"{role}: {msg['text']}")

    conversation_text = "\n\n".join(conversation)

    prompt = f"""Analyze this Claude Code session conversation and produce a concise summary.

Session info:
- Working directory: {cwd}
- Terminal: {terminal}
- Running since: {start_time}

Recent conversation (last {len(messages)} messages):

{conversation_text}

Produce a summary with:
1. **Project**: What project/repo is being worked on (infer from the working directory and conversation)
2. **Current task**: What is the user currently working on (1-2 sentences)
3. **Recent progress**: What was accomplished in the recent messages (2-4 bullet points)
4. **Status**: Is the task in progress, blocked, or completed

Output ONLY the summary in markdown format. No preamble."""

    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True, text=True, check=False,
        timeout=120,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def get_daily_status_path():
    """Get the path to today's daily status file."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return PLANS_DIR / f"daily-status-{date_str}.md"


def create_or_get_status_file(path):
    """Create the daily status file if it doesn't exist, return its content."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    if path.exists():
        return path.read_text()
    content = f"# Daily Status - {date_str}\n"
    path.write_text(content)
    return content


def append_update(path, summaries):
    """Append a timestamped update section to the status file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    content = path.read_text() if path.exists() else ""

    update = f"\n---\n\n### Auto-update at {timestamp}\n\n"
    for summary in summaries:
        update += f"#### Session: {summary['terminal']} ({summary['cwd']})\n\n"
        update += summary["summary"] + "\n\n"

    content += update
    path.write_text(content)


def git_commit_and_push(path):
    """Commit and push the status file."""
    repo_dir = PLANS_DIR
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = path.name

    subprocess.run(
        ["git", "add", filename],
        cwd=repo_dir, check=False, capture_output=True,
    )

    # Check if there are changes to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir, check=False, capture_output=True,
    )
    if result.returncode == 0:
        print("No changes to commit")
        return

    subprocess.run(
        ["git", "commit", "-m", f"Auto-update daily status {date_str}"],
        cwd=repo_dir, check=False, capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=repo_dir, check=False, capture_output=True,
    )
    print(f"Committed and pushed {filename}")


def main():
    print(f"Scanning for active Claude sessions at {datetime.now():%H:%M:%S}...")

    pids = get_active_claude_pids()
    if not pids:
        print("No active Claude sessions found")
        return

    print(f"Found {len(pids)} active session(s)")

    summaries = []
    for pid in pids:
        cwd = get_pid_cwd(pid)
        if not cwd:
            continue

        terminal = get_pid_terminal(pid)
        start_time = get_pid_start_time(pid)
        project_dir = cwd_to_project_dir(cwd)
        session_file = find_active_session(project_dir)

        if not session_file:
            print(f"  PID {pid} ({terminal}): no session file found")
            continue

        print(f"  PID {pid} ({terminal}): {cwd}")
        print(f"    Session: {session_file.name}")

        messages = extract_recent_messages(session_file)
        if not messages:
            print(f"    No recent messages")
            continue

        print(f"    Summarizing {len(messages)} recent messages...")
        summary = summarize_session(messages, cwd, terminal, start_time)
        if summary:
            summaries.append({
                "pid": pid,
                "terminal": terminal,
                "cwd": cwd,
                "summary": summary,
            })
            print(f"    Done")
        else:
            print(f"    Summarization failed")

    if not summaries:
        print("No sessions to summarize")
        return

    status_path = get_daily_status_path()
    create_or_get_status_file(status_path)
    append_update(status_path, summaries)
    print(f"\nUpdated {status_path}")

    git_commit_and_push(status_path)


if __name__ == "__main__":
    main()
