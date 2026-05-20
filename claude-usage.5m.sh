#!/usr/bin/env bash
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>v0.1.0</bitbar.version>
# <bitbar.author>daiki</bitbar.author>
# <bitbar.desc>Shows Claude Code usage (5-hour block and weekly) in the menu bar via ccusage.</bitbar.desc>
# <bitbar.dependencies>node,jq,ccusage</bitbar.dependencies>

set -u

export PATH="/opt/homebrew/bin:/Users/daiki/.volta/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Defaults — override in ~/.config/claude-usage-bar/config.sh
# Token-based limits for Claude Max ($100) plan.
# Anthropic does not publish exact token limits; these are community-observed
# rough ceilings. Tune to match your own experience.
BLOCK_TOKEN_LIMIT="${BLOCK_TOKEN_LIMIT:-220000000}"    # 5-hour block ~220M tokens
WEEKLY_TOKEN_LIMIT="${WEEKLY_TOKEN_LIMIT:-1000000000}" # week ~1B tokens

CONFIG_FILE="${CLAUDE_USAGE_BAR_CONFIG:-$HOME/.config/claude-usage-bar/config.sh}"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

emit_error() {
    echo "Claude ⚠️"
    echo "---"
    echo "$1 | color=red"
    echo "Refresh | refresh=true"
    exit 0
}

command -v node >/dev/null 2>&1 || emit_error "node not found on PATH"
command -v jq   >/dev/null 2>&1 || emit_error "jq not found on PATH"

BLOCKS_JSON="$(npx -y ccusage blocks --active --json 2>/dev/null)"
WEEKLY_JSON="$(npx -y ccusage weekly --json 2>/dev/null)"

[ -z "$BLOCKS_JSON" ] && emit_error "ccusage blocks failed"
[ -z "$WEEKLY_JSON" ] && emit_error "ccusage weekly failed"

# --- 5-hour block ---
BLOCK_TOKENS=$(echo "$BLOCKS_JSON" | jq -r '.blocks[0].totalTokens // 0')
BLOCK_COST=$(echo "$BLOCKS_JSON"   | jq -r '.blocks[0].costUSD // 0')
BLOCK_END=$(echo "$BLOCKS_JSON"    | jq -r '.blocks[0].endTime // ""')
BLOCK_REMAIN_MIN=$(echo "$BLOCKS_JSON" | jq -r '.blocks[0].projection.remainingMinutes // 0')
BLOCK_PROJ_TOKENS=$(echo "$BLOCKS_JSON" | jq -r '.blocks[0].projection.totalTokens // 0')
BLOCK_PROJ_COST=$(echo "$BLOCKS_JSON"   | jq -r '.blocks[0].projection.totalCost // 0')
BLOCK_IS_ACTIVE=$(echo "$BLOCKS_JSON"   | jq -r '.blocks[0].isActive // false')

# --- Weekly (current ISO week = last entry in array) ---
WEEK_TOKENS=$(echo "$WEEKLY_JSON" | jq -r '.weekly[-1].totalTokens // 0')
WEEK_COST=$(echo "$WEEKLY_JSON"   | jq -r '.weekly[-1].totalCost // 0')
WEEK_PERIOD=$(echo "$WEEKLY_JSON" | jq -r '.weekly[-1].period // ""')

pct() {
    # $1 = used, $2 = limit
    awk -v u="$1" -v l="$2" 'BEGIN { if (l<=0) print 0; else printf "%.0f", (u/l)*100 }'
}
fmt_tokens() {
    awk -v n="$1" 'BEGIN {
        if (n >= 1e9)      printf "%.2fB", n/1e9;
        else if (n >= 1e6) printf "%.1fM", n/1e6;
        else if (n >= 1e3) printf "%.1fK", n/1e3;
        else               printf "%d", n;
    }'
}

BLOCK_PCT=$(pct "$BLOCK_TOKENS" "$BLOCK_TOKEN_LIMIT")
WEEK_PCT=$(pct "$WEEK_TOKENS"  "$WEEKLY_TOKEN_LIMIT")
BLOCK_PROJ_PCT=$(pct "$BLOCK_PROJ_TOKENS" "$BLOCK_TOKEN_LIMIT")

color_for_pct() {
    awk -v p="$1" 'BEGIN {
        if (p >= 90) print "red";
        else if (p >= 70) print "orange";
        else print "";
    }'
}
BLOCK_COLOR=$(color_for_pct "$BLOCK_PCT")
WEEK_COLOR=$(color_for_pct "$WEEK_PCT")

# Menu-bar title: 5-hour block % + time until block resets.
# Weekly status lives in the dropdown.
fmt_remain() {
    awk -v m="$1" 'BEGIN {
        m = int(m);
        if (m < 0) m = 0;
        h = int(m/60); mm = m%60;
        if (h > 0) printf "%dh%02dm", h, mm;
        else       printf "%dm", mm;
    }'
}

if [ "$BLOCK_IS_ACTIVE" = "true" ]; then
    TITLE="${BLOCK_PCT}% · $(fmt_remain "$BLOCK_REMAIN_MIN")"
else
    TITLE="idle"
fi

if [ -n "$BLOCK_COLOR" ]; then
    echo "$TITLE | color=$BLOCK_COLOR"
else
    echo "$TITLE"
fi

echo "---"
echo "Claude Code Usage | size=11"
echo "---"

# 5h block section
if [ "$BLOCK_IS_ACTIVE" = "true" ]; then
    BLOCK_END_LOCAL=$(node -e "console.log(new Date('$BLOCK_END').toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}))" 2>/dev/null)
    echo "5-hour block — ends ${BLOCK_END_LOCAL} (${BLOCK_REMAIN_MIN}m left)"
    BC_OPT=""
    [ -n "$BLOCK_COLOR" ] && BC_OPT=" color=$BLOCK_COLOR"
    echo "  Used: $(fmt_tokens "$BLOCK_TOKENS") / $(fmt_tokens "$BLOCK_TOKEN_LIMIT") (${BLOCK_PCT}%) |${BC_OPT} font=Menlo"
    echo "  Cost: \$$(printf '%.2f' "$BLOCK_COST") | font=Menlo"
    echo "  Projected: $(fmt_tokens "$BLOCK_PROJ_TOKENS") (${BLOCK_PROJ_PCT}%) / \$$(printf '%.2f' "$BLOCK_PROJ_COST") | font=Menlo"
else
    echo "5-hour block: no active session"
fi

echo "---"

# Weekly section
echo "Week (${WEEK_PERIOD} ~)"
WC_OPT=""
[ -n "$WEEK_COLOR" ] && WC_OPT=" color=$WEEK_COLOR"
echo "  Used: $(fmt_tokens "$WEEK_TOKENS") / $(fmt_tokens "$WEEKLY_TOKEN_LIMIT") (${WEEK_PCT}%) |${WC_OPT} font=Menlo"
echo "  Cost: \$$(printf '%.2f' "$WEEK_COST") | font=Menlo"

echo "---"
echo "Block limit: $(fmt_tokens "$BLOCK_TOKEN_LIMIT") | size=10 color=gray"
echo "Weekly limit: $(fmt_tokens "$WEEKLY_TOKEN_LIMIT") | size=10 color=gray"
EDITOR_CMD="${VISUAL:-${EDITOR:-/usr/bin/open}}"
echo "Edit config | bash=\"$EDITOR_CMD\" param1=\"$CONFIG_FILE\" terminal=false"
echo "Open ccusage | shell=npx param1=-y param2=ccusage param3=blocks terminal=true"
echo "Refresh | refresh=true"
