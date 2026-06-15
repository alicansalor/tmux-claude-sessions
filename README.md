# tmux-claude-sessions

Browse and resume [Claude Code](https://claude.com/claude-code) sessions from a
tmux popup — a fuzzy picker with rich, scrollable previews and Claude's own
"Goal / Done / Next" recaps, all read straight off disk so opening the picker
costs **zero model tokens**.

```
 claude sessions >
▌ Explore tmux plugins for Claude session searching        13:57
▌   scag-748 · 26p
▌   Goal: build a tmux popup to browse and resume Claude sessions.
▌   The picker, zero-token keybindings, real recaps, and newest-first
▌   ordering are all done. Next: test it live.
▌ ────────────────────────────────────────────────────────────────
▌ Create tickets for trial supplier coverage analysis      13:35
▌   scag-748 · 8p
▌   Goal: raise Linear tickets for the Trial Supplier Coverage …
```

## Features

- **Two-line cards** — AI-generated title, branch, prompt count, and the full
  session recap (or "where you left off" when no recap exists yet).
- **Live preview** — metadata header (branch, timespan, model, tokens) plus a
  readable transcript with tool calls collapsed to one line.
- **Two resume modes:**
  - `prefix + Ctrl-j` — resume in a pane sitting at a shell prompt (`send-keys`).
  - `prefix + Ctrl-r` — *in-place* resume that replaces whatever is running in
    the pane, including an open Claude session (`respawn-pane`).
- **Newest-first**, cursor on the latest session.
- **Tab** toggles between the current project and all projects.
- **Zero tokens** — everything is parsed from `~/.claude/projects/*.jsonl`; no
  model is ever invoked, even when you cancel.

## Requirements

- [tmux](https://github.com/tmux/tmux) 3.2+ (for `display-popup`)
- [fzf](https://github.com/junegunn/fzf) 0.50+ (multi-line items, `--wrap`,
  `--accept-nth`)
- Python 3.9+
- [Claude Code](https://claude.com/claude-code) (the thing whose sessions this
  browses)

## Install

### With [TPM](https://github.com/tmux-plugins/tpm)

Add to `~/.tmux.conf`:

```tmux
set -g @plugin 'alicansalor/tmux-claude-sessions'
```

Then press `prefix + I` to install.

### Manual

```sh
git clone https://github.com/alicansalor/tmux-claude-sessions ~/.tmux/plugins/tmux-claude-sessions
```

Add to `~/.tmux.conf`:

```tmux
run-shell ~/.tmux/plugins/tmux-claude-sessions/claude-sessions.tmux
```

Reload tmux (`tmux source-file ~/.tmux.conf`).

## Configuration

Set these before the plugin is loaded:

```tmux
set -g @claude_sessions_key         'C-j'   # browse + resume
set -g @claude_sessions_inplace_key 'C-r'   # in-place resume
set -g @claude_sessions_width       '85%'
set -g @claude_sessions_height      '85%'
```

## How it works

Claude Code stores each session as a JSONL file under
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. This plugin:

1. `scripts/claude-sessions-helper.py` parses those files into picker rows and
   preview text (titles from `ai-title`, recaps from `away_summary` system
   lines, branch/model/token metadata from message events).
2. `scripts/claude-sessions` drives `fzf` inside the popup and, on selection,
   resumes the chosen session in the launching pane.

Nothing calls the model, so browsing and previewing are free.

## License

MIT
