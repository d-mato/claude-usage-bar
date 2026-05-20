#!/usr/bin/env bash
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>v0.2.0</bitbar.version>
# <bitbar.author>daiki</bitbar.author>
# <bitbar.desc>Shows Claude Code usage (5-hour block and weekly) in the menu bar by calling /api/oauth/usage.</bitbar.desc>
# <bitbar.dependencies>jq,security,curl</bitbar.dependencies>

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Keychain entry written by Claude Code at login.
KEYCHAIN_SERVICE="Claude Code-credentials"
KEYCHAIN_ACCOUNT="${KEYCHAIN_ACCOUNT:-$(whoami)}"
USAGE_URL="https://api.anthropic.com/api/oauth/usage"

CONFIG_FILE="${CLAUDE_USAGE_BAR_CONFIG:-$HOME/.config/claude-usage-bar/config.sh}"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

emit_error() {
    echo "Claude ⚠️"
    echo "---"
    echo "$1 | color=red"
    echo "Refresh | refresh=true"
    exit 0
}

command -v jq       >/dev/null 2>&1 || emit_error "jq not found"
command -v security >/dev/null 2>&1 || emit_error "security CLI not found"
command -v curl     >/dev/null 2>&1 || emit_error "curl not found"

CRED_JSON="$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w 2>/dev/null)" \
    || emit_error "Keychain access denied or no entry for $KEYCHAIN_SERVICE/$KEYCHAIN_ACCOUNT"

TOKEN="$(echo "$CRED_JSON" | jq -r '.claudeAiOauth.accessToken // empty')"
[ -z "$TOKEN" ] && emit_error "no accessToken in Keychain entry"

EXPIRES_AT_MS="$(echo "$CRED_JSON" | jq -r '.claudeAiOauth.expiresAt // 0')"
NOW_MS=$(($(date +%s) * 1000))
if [ "$EXPIRES_AT_MS" -gt 0 ] && [ "$EXPIRES_AT_MS" -lt "$NOW_MS" ]; then
    emit_error "OAuth token expired — run 'claude' to re-login"
fi

RESP="$(curl -sS --max-time 8 \
    -H "Authorization: Bearer $TOKEN" \
    -H "anthropic-beta: oauth-2025-04-20" \
    "$USAGE_URL" 2>/dev/null)"
[ -z "$RESP" ] && emit_error "no response from $USAGE_URL"

# Surface API errors plainly.
ERR_TYPE="$(echo "$RESP" | jq -r '.error.type // empty' 2>/dev/null)"
[ -n "$ERR_TYPE" ] && emit_error "API error: $ERR_TYPE"

FIVE_PCT="$(echo "$RESP" | jq -r '.five_hour.utilization // 0')"
FIVE_RESET="$(echo "$RESP" | jq -r '.five_hour.resets_at // empty')"
WEEK_PCT="$(echo "$RESP" | jq -r '.seven_day.utilization // 0')"
WEEK_RESET="$(echo "$RESP" | jq -r '.seven_day.resets_at // empty')"
WEEK_SONNET_PCT="$(echo "$RESP" | jq -r '.seven_day_sonnet.utilization // 0')"
WEEK_OPUS_PCT="$(echo "$RESP" | jq -r '.seven_day_opus.utilization // 0')"

# Utilizations are already 0-100 percentages. Coerce to ints for display.
round_int() {
    awk -v n="$1" 'BEGIN { printf "%d", (n + 0.5) }'
}
FIVE_INT=$(round_int "$FIVE_PCT")
WEEK_INT=$(round_int "$WEEK_PCT")
WEEK_SONNET_INT=$(round_int "$WEEK_SONNET_PCT")
WEEK_OPUS_INT=$(round_int "$WEEK_OPUS_PCT")

# Seconds until ISO timestamp.
secs_until_iso() {
    [ -z "$1" ] && { echo 0; return; }
    local target now
    target=$(date -j -u -f "%Y-%m-%dT%H:%M:%S" "${1%%.*}" +%s 2>/dev/null) || { echo 0; return; }
    now=$(date +%s)
    echo $((target - now))
}
fmt_remain_from_secs() {
    awk -v s="$1" 'BEGIN {
        if (s < 0) s = 0;
        m = int(s/60);
        h = int(m/60); mm = m%60;
        if (h > 0) printf "%dh%02dm", h, mm;
        else       printf "%dm", mm;
    }'
}
# Convert ISO UTC timestamp to a local-time formatted string.
# BSD `date -j -u -f ... +%s` parses input as UTC; `date -j -r EPOCH` re-renders
# in the local TZ.
iso_to_local() {
    local iso="$1" fmt="$2"
    [ -z "$iso" ] && { echo "—"; return; }
    local clean="${iso%%.*}"
    local epoch
    epoch=$(date -j -u -f "%Y-%m-%dT%H:%M:%S" "$clean" +%s 2>/dev/null) || { echo "$iso"; return; }
    date -j -r "$epoch" "+$fmt" 2>/dev/null || echo "$iso"
}

FIVE_REMAIN_SECS=$(secs_until_iso "$FIVE_RESET")
FIVE_REMAIN_TXT=$(fmt_remain_from_secs "$FIVE_REMAIN_SECS")
FIVE_RESET_TIME=$(iso_to_local "$FIVE_RESET" "%H:%M")
WEEK_RESET_TXT=$(iso_to_local "$WEEK_RESET" "%-m月%-d日 %H:%M")

color_for_pct() {
    awk -v p="$1" 'BEGIN {
        if (p >= 90) print "red";
        else if (p >= 70) print "orange";
        else print "";
    }'
}
FIVE_COLOR=$(color_for_pct "$FIVE_INT")
WEEK_COLOR=$(color_for_pct "$WEEK_INT")

# --- Menu bar title ---
TITLE="${FIVE_INT}% · ${FIVE_REMAIN_TXT}"
if [ -n "$FIVE_COLOR" ]; then
    echo "$TITLE | color=$FIVE_COLOR"
else
    echo "$TITLE"
fi

echo "---"
echo "Claude Code Usage | size=11"
echo "---"

# 5-hour block
echo "5-hour session — resets ${FIVE_RESET_TIME} (${FIVE_REMAIN_TXT} left)"
FC_OPT=""
[ -n "$FIVE_COLOR" ] && FC_OPT=" color=$FIVE_COLOR"
echo "  ${FIVE_INT}% used |${FC_OPT} font=Menlo"

echo "---"

# Weekly
echo "Week (all models) — resets ${WEEK_RESET_TXT}"
WC_OPT=""
[ -n "$WEEK_COLOR" ] && WC_OPT=" color=$WEEK_COLOR"
echo "  ${WEEK_INT}% used |${WC_OPT} font=Menlo"

if [ "$WEEK_OPUS_INT" -gt 0 ]; then
    echo "Week (Opus only)"
    echo "  ${WEEK_OPUS_INT}% used | font=Menlo color=gray"
fi
if [ "$WEEK_SONNET_INT" -gt 0 ]; then
    echo "Week (Sonnet only)"
    echo "  ${WEEK_SONNET_INT}% used | font=Menlo color=gray"
fi

echo "---"
EDITOR_CMD="${VISUAL:-${EDITOR:-/usr/bin/open}}"
echo "Edit config | bash=\"$EDITOR_CMD\" param1=\"$CONFIG_FILE\" terminal=false"
echo "Open claude.ai usage | href=https://claude.ai/settings/usage"
echo "Refresh | refresh=true"
