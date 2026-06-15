#!/usr/bin/env bash
# tmux-claude-sessions — TPM entry point.
#
# tmux sources this file at startup (directly, or via TPM). It wires up the
# keybindings that open the session picker popup. All scripts are referenced by
# absolute path, so nothing needs to be on $PATH.
#
# Configurable via tmux options (set before the plugin line in tmux.conf):
#   set -g @claude_sessions_key          'C-j'   # browse + resume (send-keys)
#   set -g @claude_sessions_inplace_key  'C-r'   # in-place resume (respawn-pane)
#   set -g @claude_sessions_width        '85%'
#   set -g @claude_sessions_height       '85%'

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$CURRENT_DIR/scripts/claude-sessions"

opt() {
  local value
  value="$(tmux show-option -gqv "$1")"
  echo "${value:-$2}"
}

browse_key="$(opt '@claude_sessions_key' 'C-j')"
inplace_key="$(opt '@claude_sessions_inplace_key' 'C-r')"
width="$(opt '@claude_sessions_width' '85%')"
height="$(opt '@claude_sessions_height' '85%')"

# Browse + resume in a pane at a shell prompt (send-keys).
tmux bind-key "$browse_key" \
  display-popup -w "$width" -h "$height" -d '#{pane_current_path}' -E "$LAUNCHER"

# In-place resume: replace whatever runs in the pane (e.g. an open Claude
# session) with the chosen one. Costs zero model tokens, even on cancel.
tmux bind-key "$inplace_key" \
  display-popup -w "$width" -h "$height" -d '#{pane_current_path}' -E "$LAUNCHER --in-place"
