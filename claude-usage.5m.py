#!/usr/bin/env python3
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>v0.5.0</bitbar.version>
# <bitbar.author>daiki</bitbar.author>
# <bitbar.desc>Shows Claude Code usage (5-hour block, weekly, per-model weekly, usage credits) in the menu bar via the Claude Code get_usage control request.</bitbar.desc>
# <bitbar.dependencies>python3,claude</bitbar.dependencies>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>

import base64
import json
import locale
import math
import os
import shutil
import struct
import subprocess
import sys
import zlib
from datetime import datetime, timezone

# Usage is read from the Claude Code CLI itself: a `get_usage` control request
# over its stream-json interface returns the same account-wide numbers that
# back `/usage`, including per-model weekly windows and usage credits, with
# zero inference tokens. See issue #2 for the investigation that led here.
REQUEST_ID = "claude-usage-bar"
GET_USAGE_REQUEST = json.dumps({
    "type": "control_request",
    "request_id": REQUEST_ID,
    "request": {"subtype": "get_usage"},
}) + "\n"
# SwiftBar runs plugins with a minimal PATH, so fall back to the usual
# install locations when `claude` isn't found on it.
CLAUDE_CANDIDATES = [
    os.path.expanduser("~/.local/bin/claude"),
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
]


def emit_error(msg):
    print("Claude ⚠️")
    print("---")
    print(f"{msg} | color=red")
    print("Refresh | refresh=true")
    sys.exit(0)


def find_claude():
    override = os.environ.get("CLAUDE_BIN")
    if override:
        return override
    found = shutil.which("claude")
    if found:
        return found
    for candidate in CLAUDE_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def parse_usage_response(stdout):
    # The CLI emits one JSON object per line; pick out the control_response
    # matching our request_id. Returns the inner response dict
    # ({"subtype": ..., "response": {...}}) or None if it never arrived.
    for line in stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict) or msg.get("type") != "control_response":
            continue
        resp = msg.get("response") or {}
        if resp.get("request_id") == REQUEST_ID:
            return resp
    return None


def fetch_usage(claude_bin):
    try:
        proc = subprocess.run(
            [claude_bin, "-p",
             "--input-format", "stream-json",
             "--output-format", "stream-json",
             "--verbose"],
            input=GET_USAGE_REQUEST,
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        emit_error(f"claude CLI not found at {claude_bin}")
    except subprocess.TimeoutExpired:
        emit_error("get_usage timed out after 60s")
    resp = parse_usage_response(proc.stdout)
    if resp is None:
        emit_error(f"no get_usage response from claude (exit {proc.returncode})")
    if resp.get("subtype") != "success":
        emit_error(f"get_usage failed: {resp.get('error') or resp.get('subtype')}")
    return resp.get("response") or {}


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or cur.get(k) is None:
            return default
        cur = cur[k]
    return cur


def scoped_limits(rl):
    # Per-model weekly windows (e.g. Fable), server-labeled and pre-filtered.
    rows = []
    for entry in rl.get("model_scoped") or []:
        if not isinstance(entry, dict):
            continue
        rows.append({
            "name": entry.get("display_name") or "Model",
            "percent": entry.get("utilization") or 0,
            "resets_at": entry.get("resets_at") or "",
        })
    return rows


def fmt_money(minor, exponent=2):
    return f"${minor / (10 ** exponent):.{exponent}f}"


def spend_info(rl):
    # Usage credits (pay-as-you-go beyond plan limits). Hidden while the
    # account has never spent anything and credits are disabled.
    spend = rl.get("spend")
    if not isinstance(spend, dict):
        return None
    used_minor = get(spend, "used.amount_minor")
    if not spend.get("enabled") and not used_minor:
        return None
    exponent = get(spend, "used.exponent", 2)
    limit_minor = get(spend, "limit.amount_minor")
    return {
        "used": fmt_money(used_minor or 0, exponent),
        "limit": fmt_money(limit_minor, get(spend, "limit.exponent", 2)) if limit_minor is not None else None,
        "percent": spend.get("percent") or 0,
    }


def round_int(n):
    # Match the original awk: printf "%d", (n + 0.5) — half-up truncation.
    return int(float(n) + 0.5)


def fmt_remain(secs):
    secs = max(0, secs)
    h, rem = divmod(secs // 60, 60)
    return f"{h}h{rem:02d}m" if h else f"{rem}m"


def parse_iso_utc(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def iso_to_local(iso, fmt):
    if not iso:
        return "—"
    dt = parse_iso_utc(iso)
    return dt.astimezone().strftime(fmt) if dt else iso


def color_for_pct(p):
    if p >= 90: return "red"
    if p >= 70: return "orange"
    return ""


def pct_rgb(p):
    if p >= 90: return (220, 50, 50)
    if p >= 70: return (220, 130, 0)
    return (65, 125, 240)


def ascii_bar(p, w=20):
    p = max(0, min(100, p))
    filled = round_int(p * w / 100)
    return "[" + "█" * filled + "░" * (w - filled) + "]"


# Generate a Retina-aware RGBA PNG donut chart as base64. The PNG is rendered at
# 2× pixel density and tagged with a pHYs chunk declaring 144 DPI, so NSImage
# treats it as @2x (logical size = SIZE/2 pt, sharp on Retina).
def donut_b64(pct, cr, cg, cb):
    pct = max(0.0, min(100.0, float(pct)))
    SIZE, SS = 44, 2  # 44 px → 22 pt logical size at @2x (matches menu bar height).
    cx = cy = SIZE / 2.0
    R_OUT = SIZE / 2.0 - 2.0
    R_IN = R_OUT * 0.5  # ring thickness = 50% of outer radius
    used = (cr, cg, cb, 255)
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
                    d = math.sqrt(dx * dx + dy * dy)
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
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    # pHYs: 5669 px/m ≈ 144 DPI, unit=1 (meter) → NSImage treats as @2x.
    phys = chunk(b"pHYs", struct.pack(">IIB", 5669, 5669, 1))
    idat = zlib.compress(b"".join(b"\x00" + r for r in rows))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + phys
           + chunk(b"IDAT", idat)
           + chunk(b"IEND", b""))
    return base64.b64encode(png).decode()


def bar_line(p_int, color):
    opt = f" color={color}" if color else ""
    return f"  {ascii_bar(p_int)} {p_int}% |{opt} font=Menlo"


def main():
    # Pick up the user's LC_TIME so %x renders in their locale's date format.
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass

    claude_bin = find_claude()
    if not claude_bin:
        emit_error("claude CLI not found — install Claude Code or set CLAUDE_BIN")

    data = fetch_usage(claude_bin)
    rl = data.get("rate_limits")
    if not isinstance(rl, dict):
        emit_error("no rate_limits in get_usage response (API billing account?)")

    five_pct = get(rl, "five_hour.utilization", 0)
    five_reset = get(rl, "five_hour.resets_at", "")
    week_pct = get(rl, "seven_day.utilization", 0)
    week_reset = get(rl, "seven_day.resets_at", "")

    five_int = round_int(five_pct)
    week_int = round_int(week_pct)

    five_reset_dt = parse_iso_utc(five_reset)
    now_utc = datetime.now(timezone.utc)
    five_remain_secs = int((five_reset_dt - now_utc).total_seconds()) if five_reset_dt else 0
    five_remain_txt = fmt_remain(five_remain_secs)
    five_reset_time = iso_to_local(five_reset, "%H:%M")
    week_reset_txt = iso_to_local(week_reset, "%x %H:%M")

    five_color = color_for_pct(five_int)
    week_color = color_for_pct(week_int)
    donut = donut_b64(five_int, *pct_rgb(five_int))

    # Menu bar title (donut icon + text).
    title = f"{five_int}% · {five_remain_txt}"
    print(f"{title} | image={donut}" + (f" color={five_color}" if five_color else ""))

    print("---")
    print("Claude Usage | size=11")
    print("---")

    print(f"5-hour session — resets {five_reset_time} ({five_remain_txt} left)")
    print(bar_line(five_int, five_color))

    print("---")

    print(f"Week (all models) — resets {week_reset_txt}")
    print(bar_line(week_int, week_color))

    for row in scoped_limits(rl):
        pct = round_int(row["percent"])
        print(f"{row['name']} — resets {iso_to_local(row['resets_at'], '%x %H:%M')}")
        print(bar_line(pct, color_for_pct(pct)))

    spend = spend_info(rl)
    if spend:
        pct = round_int(spend["percent"])
        limit_txt = f" / {spend['limit']}" if spend["limit"] else ""
        print("---")
        print(f"Usage credits — {spend['used']}{limit_txt}")
        print(bar_line(pct, color_for_pct(pct)))

    print("---")
    print("Open claude.ai usage | href=https://claude.ai/settings/usage")
    print("Refresh | refresh=true")


if __name__ == "__main__":
    main()
