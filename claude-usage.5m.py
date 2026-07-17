#!/usr/bin/env python3
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>v0.4.0</bitbar.version>
# <bitbar.author>daiki</bitbar.author>
# <bitbar.desc>Shows Claude Code usage (5-hour block and weekly) in the menu bar by reading anthropic-ratelimit-unified-* headers from a minimal Messages API call.</bitbar.desc>
# <bitbar.dependencies>python3,security</bitbar.dependencies>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>

import base64
import getpass
import json
import locale
import math
import os
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone

KEYCHAIN_SERVICE = "Claude Code-credentials"
KEYCHAIN_ACCOUNT = os.environ.get("KEYCHAIN_ACCOUNT") or getpass.getuser()
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
# /api/oauth/usage started returning persistent 429s (~1h windows) around
# 2026-03, so usage is read from the rate-limit headers of a minimal inference
# call instead. Cheapest available model first; dated fallback in case the
# alias is ever retired.
PROBE_MODELS = ["claude-haiku-4-5", "claude-haiku-4-5-20251001"]


def emit_error(msg):
    print("Claude ⚠️")
    print("---")
    print(f"{msg} | color=red")
    print("Refresh | refresh=true")
    sys.exit(0)


def keychain_credentials():
    try:
        out = subprocess.run(
            ["security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except FileNotFoundError:
        emit_error("security CLI not found")
    except subprocess.CalledProcessError:
        emit_error(f"Keychain access denied or no entry for {KEYCHAIN_SERVICE}/{KEYCHAIN_ACCOUNT}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        emit_error("Keychain entry is not valid JSON")


def usage_from_headers(headers):
    # Normalize anthropic-ratelimit-unified-* headers (0..1 fraction, Unix
    # seconds) into the same shape /api/oauth/usage used to return (percent,
    # ISO 8601), so the rendering code below stays unchanged.
    def block(prefix):
        util = headers.get(f"anthropic-ratelimit-unified-{prefix}-utilization")
        reset = headers.get(f"anthropic-ratelimit-unified-{prefix}-reset")
        resets_at = ""
        if reset:
            try:
                resets_at = datetime.fromtimestamp(int(reset), timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
        return {"utilization": float(util or 0) * 100.0, "resets_at": resets_at}

    return {"five_hour": block("5h"), "seven_day": block("7d")}


def fetch_usage(token):
    # Probe the Messages API with a minimal 1-token request (~9 tokens per
    # poll) and read usage from the rate-limit response headers.
    err = None
    for model in PROBE_MODELS:
        payload = json.dumps({
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}],
        }).encode()
        req = urllib.request.Request(
            MESSAGES_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if "anthropic-ratelimit-unified-5h-utilization" not in resp.headers:
                    emit_error("no ratelimit headers in response")
                return usage_from_headers(resp.headers)
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read())
            except json.JSONDecodeError:
                emit_error(f"HTTP {e.code} from {MESSAGES_URL}")
            if get(err, "error.type") == "not_found_error":
                continue  # model retired — try the next one
            return err
        except (urllib.error.URLError, TimeoutError, OSError):
            emit_error(f"no response from {MESSAGES_URL}")
    return err


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or cur.get(k) is None:
            return default
        cur = cur[k]
    return cur


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

    cred = keychain_credentials()
    oauth = cred.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        emit_error("no accessToken in Keychain entry")

    expires_at_ms = oauth.get("expiresAt") or 0
    now_ms = int(datetime.now().timestamp() * 1000)
    if expires_at_ms and expires_at_ms < now_ms:
        emit_error("OAuth token expired — run 'claude' to re-login")

    resp = fetch_usage(token)
    err_type = get(resp, "error.type")
    if err_type:
        emit_error(f"API error: {err_type}")

    five_pct = get(resp, "five_hour.utilization", 0)
    five_reset = get(resp, "five_hour.resets_at", "")
    week_pct = get(resp, "seven_day.utilization", 0)
    week_reset = get(resp, "seven_day.resets_at", "")

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

    print("---")
    print("Open claude.ai usage | href=https://claude.ai/settings/usage")
    print("Refresh | refresh=true")


if __name__ == "__main__":
    main()
