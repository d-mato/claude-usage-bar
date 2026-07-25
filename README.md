# claude-usage-bar

A SwiftBar plugin that shows your Claude Code usage (5-hour session, weekly, per-model weekly, and usage credits) in the macOS menu bar as a percentage.

![Menu bar](docs/menubar.png)

- Left: a donut chart of the current 5-hour session utilization
- Middle: utilization as a percentage
- Right: time remaining until that session resets

Clicking the menu bar item reveals a dropdown with the 5-hour, weekly, and per-model weekly utilization and reset times, plus usage-credit spend when the account has any. The text turns orange at 70% and red at 90%.

![Dropdown](docs/dropdown.png)

## How it works

The plugin asks the local Claude Code CLI for usage via its stream-json control interface: it spawns `claude -p --input-format stream-json --output-format stream-json`, sends a `get_usage` control request, and reads the response. That returns the same account-wide, server-side numbers that back Claude Code's `/usage` command — including per-model weekly windows (e.g. Fable) and usage-credit spend.

- **Auth**: handled entirely by the Claude Code CLI — the plugin never touches your OAuth token or the Keychain.
- **Aggregation**: done server-side by Anthropic — account-wide across all your machines, no local log parsing.
- **Cost**: zero — `get_usage` is a control request, no inference involved.
- **Dependencies**: `python3` (from Xcode Command Line Tools) and the `claude` CLI.

> [!NOTE]
> The `get_usage` control request is undocumented and could change between Claude Code releases (verified on 2.1.220). See [issue #2](https://github.com/d-mato/claude-usage-bar/issues/2) for the investigation that led here, and the version history below for the previous approaches.

## Requirements

- macOS with `python3` (from Xcode Command Line Tools)
- Homebrew
- Claude Code installed and logged in (`claude` on PATH, or in `~/.local/bin`, `/opt/homebrew/bin`, or `/usr/local/bin`; override with the `CLAUDE_BIN` environment variable)

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

> Upgrading from v0.4 or earlier: the Keychain access granted to SwiftBar is no longer used and can be revoked (Keychain Access.app → `Claude Code-credentials` → Access Control).

## Display

| Location | Content |
|---|---|
| Menu bar | `37% · 2h24m` (5-hour session utilization + time remaining) |
| Dropdown | 5-hour session, weekly, and per-model weekly (e.g. Fable) utilization with reset times; usage-credit spend when present |

## Troubleshooting

- **`Claude ⚠️` in the menu bar**: open the dropdown to see the error.
- **`claude CLI not found`**: install Claude Code, or point the plugin at the binary with `CLAUDE_BIN=/path/to/claude` in SwiftBar's environment.
- **`no get_usage response from claude`**: run `claude` in a terminal — you may be logged out, or the installed version may predate the `get_usage` control request (verified on 2.1.220).
- **`get_usage timed out`**: usually a transient network problem; pick Refresh from the menu.
- **Stale numbers**: pick Refresh from the menu, or wait 5 minutes. To change the refresh interval, rename the `5m` part of the filename (e.g. to `1m`).

## Version history

- **v0.1**: aggregated local logs via `ccusage`. Retired because its numbers drifted tens of percent from the official `/usage`.
- **v0.2**: switched to calling the official `/api/oauth/usage` endpoint directly.
- **v0.3**: rewrote the plugin in Python to drop the `jq` dependency.
- **v0.4**: switched to reading `anthropic-ratelimit-unified-*` headers from a 1-token Messages API call, after `/api/oauth/usage` became too aggressively rate limited to poll ([anthropics/claude-code#31637](https://github.com/anthropics/claude-code/issues/31637)).
- **v0.5**: switched to the Claude Code `get_usage` control request — zero token cost, no Keychain access, and per-model weekly windows (e.g. Fable) plus usage credits are back ([#2](https://github.com/d-mato/claude-usage-bar/issues/2)).

## License

MIT — see [LICENSE](LICENSE).
