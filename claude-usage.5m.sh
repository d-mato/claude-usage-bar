#!/usr/bin/env bash
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>v0.2.0</bitbar.version>
# <bitbar.author>daiki</bitbar.author>
# <bitbar.desc>Shows Claude Code usage (5-hour block and weekly) in the menu bar by calling /api/oauth/usage.</bitbar.desc>
# <bitbar.dependencies>jq,security,curl,python3</bitbar.dependencies>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Keychain entry written by Claude Code at login.
KEYCHAIN_SERVICE="Claude Code-credentials"
KEYCHAIN_ACCOUNT="${KEYCHAIN_ACCOUNT:-$(whoami)}"
USAGE_URL="https://api.anthropic.com/api/oauth/usage"

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
command -v python3  >/dev/null 2>&1 || emit_error "python3 not found"

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
WEEK_SONNET_PRESENT="$(echo "$RESP" | jq -r 'if .seven_day_sonnet == null then "0" else "1" end')"
WEEK_OPUS_PCT="$(echo "$RESP" | jq -r '.seven_day_opus.utilization // 0')"
WEEK_OPUS_PRESENT="$(echo "$RESP" | jq -r 'if .seven_day_opus == null then "0" else "1" end')"
WEEK_DESIGN_PCT="$(echo "$RESP" | jq -r '.seven_day_omelette.utilization // 0')"
WEEK_DESIGN_RESET="$(echo "$RESP" | jq -r '.seven_day_omelette.resets_at // empty')"

# Utilizations are already 0-100 percentages. Coerce to ints for display.
round_int() {
    awk -v n="$1" 'BEGIN { printf "%d", (n + 0.5) }'
}
FIVE_INT=$(round_int "$FIVE_PCT")
WEEK_INT=$(round_int "$WEEK_PCT")
WEEK_SONNET_INT=$(round_int "$WEEK_SONNET_PCT")
WEEK_OPUS_INT=$(round_int "$WEEK_OPUS_PCT")
WEEK_DESIGN_INT=$(round_int "$WEEK_DESIGN_PCT")

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
WEEK_DESIGN_RESET_TXT=$(iso_to_local "$WEEK_DESIGN_RESET" "%-m月%-d日 %H:%M")

color_for_pct() {
    awk -v p="$1" 'BEGIN {
        if (p >= 90) print "red";
        else if (p >= 70) print "orange";
        else print "";
    }'
}
ascii_bar() {
    awk -v p="$1" -v w=20 'BEGIN {
        if (p < 0) p = 0; if (p > 100) p = 100;
        filled = int(p * w / 100 + 0.5);
        bar = "[";
        for (i = 0; i < filled; i++) bar = bar "█";
        for (i = filled; i < w; i++) bar = bar "░";
        bar = bar "]";
        print bar;
    }'
}

# Return "R G B" integers matching color_for_pct thresholds.
pct_rgb() {
    if   [ "$1" -ge 90 ]; then echo "220 50 50"
    elif [ "$1" -ge 70 ]; then echo "220 130 0"
    else                       echo "65 125 240"
    fi
}

# Generate a Retina-aware RGBA PNG donut chart as base64.
# The PNG is rendered at 2× pixel density and tagged with a pHYs chunk declaring
# 144 DPI, so NSImage treats it as @2x (logical size = SIZE/2 pt, sharp on Retina).
# Args: pct(0-100)  r g b
donut_b64() {
    python3 - "$1" "$2" "$3" "$4" <<'PYEOF'
import math, struct, zlib, base64, sys

pct = max(0.0, min(100.0, float(sys.argv[1])))
cr, cg, cb = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])

# 44 px → 22 pt logical size at @2x (matches menu bar height).
SIZE, SS = 44, 2
cx = cy = SIZE / 2.0
R_OUT = SIZE / 2.0 - 2.0
R_IN  = R_OUT * 0.5  # ring thickness = 50% of outer radius
used  = (cr, cg, cb, 255)
empty = (185, 190, 200, 200)

rows = []
for y in range(SIZE):
    row = []
    for x in range(SIZE):
        acc = [0, 0, 0, 0]
        for sy in range(SS):
            for sx in range(SS):
                dx = x - cx + (sx + 0.5) / SS
                dy = y - cy + (sy + 0.5) / SS
                d  = math.sqrt(dx * dx + dy * dy)
                if R_IN <= d <= R_OUT:
                    ang = math.atan2(dx, -dy)
                    if ang < 0:
                        ang += 2 * math.pi
                    px = used if ang <= 2 * math.pi * pct / 100.0 else empty
                else:
                    px = (0, 0, 0, 0)
                for i in range(4):
                    acc[i] += px[i]
        row.extend(v // (SS * SS) for v in acc)
    rows.append(bytes(row))

def chunk(tag, data):
    body = tag + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

ihdr = struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0)
# pHYs: 5669 px/m ≈ 144 DPI on both axes, unit=1 (meter) → NSImage treats as @2x.
phys = chunk(b'pHYs', struct.pack('>IIB', 5669, 5669, 1))
idat = zlib.compress(b''.join(b'\x00' + r for r in rows))
png  = (b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + phys
        + chunk(b'IDAT', idat)
        + chunk(b'IEND', b''))
print(base64.b64encode(png).decode())
PYEOF
}

FIVE_COLOR=$(color_for_pct "$FIVE_INT")
WEEK_COLOR=$(color_for_pct "$WEEK_INT")

# Generate the donut chart for the menu bar icon (5-hour utilization).
# shellcheck disable=SC2046
FIVE_DONUT=$(donut_b64 "$FIVE_INT" $(pct_rgb "$FIVE_INT"))

# --- Menu bar title (donut icon + text) ---
TITLE="${FIVE_INT}% · ${FIVE_REMAIN_TXT}"
if [ -n "$FIVE_COLOR" ]; then
    echo "$TITLE | image=${FIVE_DONUT} color=$FIVE_COLOR"
else
    echo "$TITLE | image=${FIVE_DONUT}"
fi

echo "---"
echo "Claude Usage | size=11"
echo "---"

# 5-hour block
echo "5-hour session — resets ${FIVE_RESET_TIME} (${FIVE_REMAIN_TXT} left)"
FC_OPT=""
[ -n "$FIVE_COLOR" ] && FC_OPT=" color=$FIVE_COLOR"
echo "  $(ascii_bar "$FIVE_INT") ${FIVE_INT}% |${FC_OPT} font=Menlo"

echo "---"

# Weekly
echo "Week (all models) — resets ${WEEK_RESET_TXT}"
WC_OPT=""
[ -n "$WEEK_COLOR" ] && WC_OPT=" color=$WEEK_COLOR"
echo "  $(ascii_bar "$WEEK_INT") ${WEEK_INT}% |${WC_OPT} font=Menlo"

if [ "$WEEK_OPUS_PRESENT" = "1" ]; then
    echo "Week (Opus only)"
    echo "  $(ascii_bar "$WEEK_OPUS_INT") ${WEEK_OPUS_INT}% | font=Menlo color=gray"
fi
if [ "$WEEK_SONNET_PRESENT" = "1" ]; then
    echo "Week (Sonnet only)"
    echo "  $(ascii_bar "$WEEK_SONNET_INT") ${WEEK_SONNET_INT}% | font=Menlo color=gray"
fi

if [ -n "$WEEK_DESIGN_RESET" ]; then
    echo "---"
    echo "Claude Design — resets ${WEEK_DESIGN_RESET_TXT}"
    DC_OPT=""
    DC=$(color_for_pct "$WEEK_DESIGN_INT")
    [ -n "$DC" ] && DC_OPT=" color=$DC"
    echo "  $(ascii_bar "$WEEK_DESIGN_INT") ${WEEK_DESIGN_INT}% |${DC_OPT} font=Menlo"
fi

echo "---"
echo "Open claude.ai usage | href=https://claude.ai/settings/usage"
echo "Refresh | refresh=true"
