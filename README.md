# claude-usage-bar

A SwiftBar plugin that shows your Claude Code usage (5-hour session and weekly) in the macOS menu bar as a percentage.

![Menu bar](docs/menubar.png)

- Left: a donut chart of the current 5-hour session utilization
- Middle: utilization as a percentage
- Right: time remaining until that session resets

Clicking the menu bar item reveals a dropdown with the 5-hour and weekly utilization and reset times. The text turns orange at 70% and red at 90%.

![Dropdown](docs/dropdown.png)

## How it works

The plugin sends a minimal request to the Messages API (`POST /v1/messages`, Haiku, `max_tokens: 1`) and reads the current utilization from the `anthropic-ratelimit-unified-*` response headers — the same server-side numbers that back Claude Code's `/usage` command.

- **Auth**: reads the Claude Code OAuth access token from the macOS Keychain entry `Claude Code-credentials` via the `security` command.
- **Aggregation**: done server-side by Anthropic — no local log parsing.
- **Cost**: each refresh consumes ~9 Haiku tokens (8 input + 1 output) of your subscription quota — negligible, but not zero.
- **Dependencies**: `python3`, `security` (both standard on macOS once Xcode Command Line Tools are installed).

> [!NOTE]
> Earlier versions called Claude Code's internal `/api/oauth/usage` endpoint, but around March 2026 it began returning persistent 429s (roughly one request per hour is allowed), which defeats the point of a live menu bar gauge ([anthropics/claude-code#31637](https://github.com/anthropics/claude-code/issues/31637)). Reading rate-limit headers off a 1-token inference call is the workaround. Two side effects: per-model weekly breakdowns (Opus/Sonnet) are no longer available, and polling itself keeps a 5-hour usage window open, so a reset time is always shown even when you're otherwise idle.

## Requirements

- macOS (requires the `security` CLI and `python3` from Xcode Command Line Tools)
- Homebrew
- Logged into Claude Code (so the OAuth token is stored in the Keychain)

## Setup

```sh
brew install --cask swiftbar

# Clone this repo anywhere
git clone https://github.com/d-mato/claude-usage-bar ~/Projects/claude-usage-bar
chmod +x ~/Projects/claude-usage-bar/claude-usage.5m.py

# Launch SwiftBar and pick a Plugin Folder when prompted
# (existing users: skip this — your Plugin Folder is already set)
open -a SwiftBar

# Symlink the script into your SwiftBar Plugin Folder
ln -s ~/Projects/claude-usage-bar/claude-usage.5m.py \
      "$(defaults read com.ameba.SwiftBar PluginDirectory)/"
```

The symlink approach lets `git pull` update the plugin in place and keeps the script next to other SwiftBar plugins you may already have.

### First-run Keychain prompt

The first time SwiftBar runs the plugin, macOS will show a dialog like:

> "SwiftBar" wants to access the keychain item "Claude Code-credentials".

Click **Always Allow**. Choosing **Allow** alone will re-prompt every refresh.

## Display

| Location | Content |
|---|---|
| Menu bar | `37% · 2h24m` (5-hour session utilization + time remaining) |
| Dropdown | 5-hour session and weekly utilization, reset times |

## Troubleshooting

- **`Claude ⚠️` in the menu bar**: open the dropdown to see the error. Usually it's a Keychain denial or an expired token.
- **`OAuth token expired`**: run `claude` in a terminal to re-login.
- **`Keychain access denied`**: open Keychain Access.app, find `Claude Code-credentials`, and add SwiftBar to the Access Control list.
- **Stale numbers**: pick Refresh from the menu, or wait 5 minutes. To change the refresh interval, rename the `5m` part of the filename (e.g. to `1m`).

## Version history

- **v0.1**: aggregated local logs via `ccusage`. Retired because its numbers drifted tens of percent from the official `/usage`.
- **v0.2**: switched to calling the official `/api/oauth/usage` endpoint directly.
- **v0.3**: rewrote the plugin in Python to drop the `jq` dependency.
- **v0.4**: switched to reading `anthropic-ratelimit-unified-*` headers from a 1-token Messages API call, after `/api/oauth/usage` became too aggressively rate limited to poll.

## License

MIT — see [LICENSE](LICENSE).
