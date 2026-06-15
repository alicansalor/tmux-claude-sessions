#!/usr/bin/env python3
"""Helper for the claude-sessions tmux popup.

Subcommands:
  list            Print one tab-separated row per session for the current
                  project (or all projects, toggled via the CS_STATE file).
  list --toggle   Flip the current/all mode, then print the list.
  preview <id>    Print a readable transcript preview for a session id.

Each Claude session is a JSONL file under
  ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
where each line is a JSON event (mode, snapshot, user/assistant message,
ai-title, etc.). We only need a handful of those line types.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# ----- session directory resolution -----------------------------------------


def encode_cwd(path: str) -> str:
    """Reproduce Claude's project-dir encoding: non-alphanumerics -> '-'."""
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def current_project_dir() -> Path:
    return PROJECTS_DIR / encode_cwd(os.getcwd())


def session_files(all_projects: bool):
    """Yield .jsonl session files, newest first by mtime."""
    if all_projects:
        files = PROJECTS_DIR.glob("*/*.jsonl")
    else:
        files = current_project_dir().glob("*.jsonl")
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


# ----- mode state (current vs all) -------------------------------------------


def read_mode() -> str:
    state = os.environ.get("CS_STATE")
    if state and Path(state).exists():
        return Path(state).read_text().strip() or "current"
    return "current"


def toggle_mode() -> str:
    state = os.environ.get("CS_STATE")
    mode = "all" if read_mode() == "current" else "current"
    if state:
        Path(state).write_text(mode)
    return mode


# ----- JSONL parsing ----------------------------------------------------------


def iter_events(path: Path):
    try:
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def collect_meta(path: Path) -> dict:
    """Single-pass extraction of everything the list/preview header needs."""
    ai_title = None
    first_user = None
    last_user = None
    recap = None
    prompts = 0
    cwd = None
    branch = None
    model = None
    tokens = 0
    first_ts = None
    last_ts = None
    for ev in iter_events(path):
        if cwd is None and isinstance(ev.get("cwd"), str):
            cwd = ev["cwd"]
        if isinstance(ev.get("gitBranch"), str) and ev["gitBranch"]:
            branch = ev["gitBranch"]
        ts = parse_ts(ev.get("timestamp"))
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
        etype = ev.get("type")
        if etype == "ai-title" and ev.get("aiTitle"):
            ai_title = ev["aiTitle"]
        elif etype == "system" and ev.get("subtype") == "away_summary":
            # Claude's own "Goal/Done/Next" recap, written when a session goes
            # idle. The latest one wins. Free to reuse — no model call needed.
            if ev.get("content"):
                recap = strip_recap_note(ev["content"])
        elif etype == "assistant":
            msg = ev.get("message", {})
            if msg.get("model"):
                model = msg["model"]
            usage = msg.get("usage") or {}
            tokens += usage.get("output_tokens", 0) or 0
        elif etype == "user":
            content = ev.get("message", {}).get("content")
            if isinstance(content, str):  # a real typed prompt, not a tool_result
                prompts += 1
                # Prefer the first natural prompt; skip command/caveat wrappers
                # like <local-command-caveat> or <command-name> that the CLI
                # injects for slash commands.
                if not content.lstrip().startswith("<"):
                    if first_user is None:
                        first_user = content
                    last_user = content
    title = " ".join((ai_title or first_user or "(no title)").split())
    return {
        "title": title,
        "first_user": first_user or "",
        "last_user": last_user or "",
        "recap": recap,
        "prompts": prompts,
        "cwd": cwd,
        "branch": branch,
        "model": model,
        "tokens": tokens,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def parse_ts(value):
    """Parse an ISO-8601 timestamp (…Z) into epoch seconds, or None."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return None


def short_model(model: str | None) -> str:
    if not model:
        return "?"
    m = re.match(r"claude-([a-z]+)-(\d+)-(\d+)", model)
    if m:
        return f"{m.group(1)} {m.group(2)}.{m.group(3)}"
    return model.replace("claude-", "")


def short_branch(branch: str | None) -> str:
    """Prefer an embedded ticket id (scag-748); else the last path segment."""
    if not branch:
        return ""
    m = re.search(r"[A-Za-z]+-\d+", branch)
    if m:
        return m.group(0).lower()
    return truncate(branch.split("/")[-1], 22)


def fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def fmt_elapsed(secs: float) -> str:
    total_min = int(secs // 60)
    h, m = divmod(total_min, 60)
    if h:
        return f"{h}h{m}m"
    if m:
        return f"{m}m"
    return f"{int(secs)}s"


def rel_time(ts: float) -> str:
    now = datetime.now()
    dt = datetime.fromtimestamp(ts)
    delta = now - dt
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if delta.days < 7:
        return dt.strftime("%a")  # Mon, Tue, ...
    if dt.year == now.year:
        return dt.strftime("%d %b")
    return dt.strftime("%d %b %y")


# ----- commands ---------------------------------------------------------------


# ANSI styling for the two-line cards.
BOLD = "\033[1m"
DIM = "\033[90m"
RST = "\033[0m"


def cmd_list(toggle: bool):
    if toggle:
        toggle_mode()
    all_projects = read_mode() == "all"
    for path in session_files(all_projects):
        sid = path.stem
        m = collect_meta(path)
        when = rel_time(path.stat().st_mtime)

        meta_bits = []
        if m["branch"]:
            meta_bits.append(short_branch(m["branch"]))
        meta_bits.append(f"{m['prompts']}p")
        recap = m["recap"]
        # No recap? fall back to "where you left off" on the meta line.
        if not recap:
            snippet = clean_user_text(m["last_user"] or m["first_user"])
            if snippet:
                meta_bits.append(f'↪ "{truncate(snippet, 50)}"')
        meta = " · ".join(meta_bits)
        if all_projects:
            proj = Path(m["cwd"]).name if m["cwd"] else "?"
            meta += f"  [{proj}]"

        # Card: bold title + time, dim meta, then (if present) the full recap on
        # its own line in normal weight — as prominent as the title and left
        # untruncated so fzf's --wrap shows all of it.
        lines = [
            f"{sid}\t{BOLD}{truncate(m['title'], 64)}{RST}  {DIM}{when}{RST}",
            f"  {DIM}{meta}{RST}",
        ]
        if recap:
            lines.append(f"  {recap}")
        # field 1 = id (hidden + used by preview/accept); field 2.. = the card.
        # NUL-terminated so the multi-line record survives --read0.
        sys.stdout.write("\n".join(lines) + "\0")


def truncate(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def strip_recap_note(content: str) -> str:
    """Drop the trailing '(disable recaps in /config)' UI hint Claude appends."""
    txt = " ".join(content.split())
    return re.sub(r"\s*\(disable recaps in /config\)\s*$", "", txt).strip()


def clean_user_text(content: str) -> str:
    """Collapse whitespace and strip CLI command/caveat wrappers for display.

    Slash commands arrive wrapped as <command-name>/foo</command-name>... and
    local commands are prefixed with a <local-command-caveat> block; reduce
    them to something readable (or drop pure caveats entirely).
    """
    txt = " ".join(content.split())
    if txt.startswith("<local-command-caveat>"):
        return ""  # pure noise injected by the CLI
    m = re.search(r"<command-name>(.*?)</command-name>", txt)
    if m:
        return m.group(1).strip()
    return txt


def find_session(sid: str) -> Path | None:
    for path in PROJECTS_DIR.glob(f"*/{sid}.jsonl"):
        return path
    return None


def block_summary(block: dict) -> str | None:
    """One-line summary for an assistant content block."""
    btype = block.get("type")
    if btype == "text":
        txt = " ".join(block.get("text", "").split())
        return f"● claude: {truncate(txt, 280)}" if txt else None
    if btype == "tool_use":
        name = block.get("name", "tool")
        inp = block.get("input", {}) or {}
        hint = (
            inp.get("command")
            or inp.get("file_path")
            or inp.get("path")
            or inp.get("pattern")
            or inp.get("description")
            or inp.get("prompt")
            or ""
        )
        hint = " ".join(str(hint).split())
        return f"  ⚙ {name}: {truncate(hint, 200)}" if hint else f"  ⚙ {name}"
    # skip thinking, etc.
    return None


def cmd_preview(sid: str):
    path = find_session(sid)
    if path is None:
        print(f"session {sid} not found")
        return
    m = collect_meta(path)
    bar = "─" * 62

    print(f"{BOLD}{m['title']}{RST}")
    print(bar)
    if m["branch"]:
        print(f"  {DIM}branch {RST} {m['branch']}")
    if m["first_ts"] and m["last_ts"]:
        start = datetime.fromtimestamp(m["first_ts"]).strftime("%Y-%m-%d %H:%M")
        end = datetime.fromtimestamp(m["last_ts"]).strftime("%H:%M")
        span = fmt_elapsed(m["last_ts"] - m["first_ts"])
        print(f"  {DIM}when   {RST} {start} → {end}  ({span})")
    print(
        f"  {DIM}model  {RST} {short_model(m['model'])}"
        f"   {DIM}prompts{RST} {m['prompts']}"
        f"   {DIM}tokens {RST} {fmt_tokens(m['tokens'])}"
    )
    if m["cwd"]:
        print(f"  {DIM}path   {RST} {m['cwd']}")
    print(bar)
    print()
    if m["recap"]:
        print(f"{BOLD}recap{RST}")
        # Single line; the preview window's own 'wrap' handles overflow. Wrapping
        # it here too would double-wrap into ragged short lines.
        print(m["recap"])
        print(bar)
        print()
    for ev in iter_events(path):
        etype = ev.get("type")
        if etype == "user":
            content = ev.get("message", {}).get("content")
            if isinstance(content, str):
                txt = clean_user_text(content)
                if txt:
                    print(f"▸ you: {truncate(txt, 400)}")
                    print()
        elif etype == "assistant":
            content = ev.get("message", {}).get("content")
            if isinstance(content, list):
                for block in content:
                    line = block_summary(block)
                    if line:
                        print(line)


def main():
    args = sys.argv[1:]
    if not args:
        cmd_list(toggle=False)
        return
    if args[0] == "list":
        cmd_list(toggle="--toggle" in args[1:])
    elif args[0] == "preview" and len(args) >= 2:
        cmd_preview(args[1])
    else:
        print(f"usage: {sys.argv[0]} list [--toggle] | preview <id>", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
