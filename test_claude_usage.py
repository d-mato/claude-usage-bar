"""Tests for claude-usage.5m.py — run with: python3 -m unittest test_claude_usage.py"""
import contextlib
import hashlib
import importlib.util
import io
import locale
import os
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location(
    "claude_usage", Path(__file__).parent / "claude-usage.5m.py"
)
claude_usage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(claude_usage)


class RoundIntTests(unittest.TestCase):
    def test_zero(self): self.assertEqual(claude_usage.round_int(0), 0)
    def test_half_rounds_up(self): self.assertEqual(claude_usage.round_int(0.5), 1)
    def test_below_half_truncates(self): self.assertEqual(claude_usage.round_int(0.49), 0)
    def test_just_under_one(self): self.assertEqual(claude_usage.round_int(0.999), 1)
    def test_string_numeric(self): self.assertEqual(claude_usage.round_int("23.5"), 24)


class FmtRemainTests(unittest.TestCase):
    def test_zero(self): self.assertEqual(claude_usage.fmt_remain(0), "0m")
    def test_negative_clamps(self): self.assertEqual(claude_usage.fmt_remain(-30), "0m")
    def test_under_one_minute(self): self.assertEqual(claude_usage.fmt_remain(45), "0m")
    def test_minutes_only(self): self.assertEqual(claude_usage.fmt_remain(125), "2m")
    def test_exact_hour_pads(self): self.assertEqual(claude_usage.fmt_remain(3600), "1h00m")
    def test_hours_and_minutes(self):
        self.assertEqual(claude_usage.fmt_remain(3 * 3600 + 44 * 60), "3h44m")


class ParseIsoUtcTests(unittest.TestCase):
    def test_empty(self): self.assertIsNone(claude_usage.parse_iso_utc(""))
    def test_none(self): self.assertIsNone(claude_usage.parse_iso_utc(None))
    def test_invalid(self): self.assertIsNone(claude_usage.parse_iso_utc("not a date"))
    def test_z_suffix(self):
        self.assertEqual(
            claude_usage.parse_iso_utc("2026-05-20T01:50:00Z"),
            datetime(2026, 5, 20, 1, 50, tzinfo=timezone.utc),
        )
    def test_fractional_seconds(self):
        dt = claude_usage.parse_iso_utc("2026-05-20T01:50:00.123Z")
        self.assertEqual(dt.microsecond, 123000)


class _TzFixed:
    """Pin TZ to Asia/Tokyo so iso_to_local output is deterministic."""
    def setUp(self):
        self._orig_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Tokyo"
        time.tzset()
    def tearDown(self):
        if self._orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._orig_tz
        time.tzset()


class IsoToLocalTests(_TzFixed, unittest.TestCase):
    def test_empty_returns_dash(self):
        self.assertEqual(claude_usage.iso_to_local("", "%H:%M"), "—")
    def test_invalid_returns_input(self):
        self.assertEqual(claude_usage.iso_to_local("garbage", "%H:%M"), "garbage")
    def test_utc_to_jst(self):
        # 01:50 UTC → 10:50 JST (UTC+9).
        self.assertEqual(claude_usage.iso_to_local("2026-05-20T01:50:00Z", "%H:%M"), "10:50")
    def test_strftime_japanese(self):
        # 00:00 UTC on 5/23 → 09:00 JST same day.
        self.assertEqual(
            claude_usage.iso_to_local("2026-05-23T00:00:00Z", "%-m月%-d日 %H:%M"),
            "5月23日 09:00",
        )


class ColorForPctTests(unittest.TestCase):
    def test_below_70_is_empty(self): self.assertEqual(claude_usage.color_for_pct(69), "")
    def test_70_is_orange(self): self.assertEqual(claude_usage.color_for_pct(70), "orange")
    def test_89_is_orange(self): self.assertEqual(claude_usage.color_for_pct(89), "orange")
    def test_90_is_red(self): self.assertEqual(claude_usage.color_for_pct(90), "red")


class PctRgbTests(unittest.TestCase):
    def test_low_is_blue(self): self.assertEqual(claude_usage.pct_rgb(0), (65, 125, 240))
    def test_69_is_blue(self): self.assertEqual(claude_usage.pct_rgb(69), (65, 125, 240))
    def test_70_is_orange(self): self.assertEqual(claude_usage.pct_rgb(70), (220, 130, 0))
    def test_90_is_red(self): self.assertEqual(claude_usage.pct_rgb(90), (220, 50, 50))


class AsciiBarTests(unittest.TestCase):
    def test_zero(self): self.assertEqual(claude_usage.ascii_bar(0), "[" + "░" * 20 + "]")
    def test_full(self): self.assertEqual(claude_usage.ascii_bar(100), "[" + "█" * 20 + "]")
    def test_half(self):
        self.assertEqual(claude_usage.ascii_bar(50), "[" + "█" * 10 + "░" * 10 + "]")
    def test_negative_clamps(self):
        self.assertEqual(claude_usage.ascii_bar(-10), "[" + "░" * 20 + "]")
    def test_over_clamps(self):
        self.assertEqual(claude_usage.ascii_bar(150), "[" + "█" * 20 + "]")


class GetTests(unittest.TestCase):
    def test_top_level(self): self.assertEqual(claude_usage.get({"a": 1}, "a"), 1)
    def test_nested(self): self.assertEqual(claude_usage.get({"a": {"b": 2}}, "a.b"), 2)
    def test_missing_returns_default(self):
        self.assertEqual(claude_usage.get({}, "a", 0), 0)
    def test_missing_default_is_none(self):
        self.assertIsNone(claude_usage.get({}, "a"))
    def test_null_treated_as_missing(self):
        # Mirrors jq's `.x // default` semantics — explicit null falls through.
        self.assertEqual(claude_usage.get({"a": None}, "a", "fallback"), "fallback")
    def test_non_dict_intermediate(self):
        self.assertIsNone(claude_usage.get({"a": "x"}, "a.b"))


class DonutB64Tests(unittest.TestCase):
    def test_output_stable(self):
        # Snapshot the donut PNG hash so subtle rendering regressions are caught.
        b64 = claude_usage.donut_b64(50, 65, 125, 240)
        self.assertEqual(
            hashlib.sha256(b64.encode()).hexdigest(),
            "770fa5844123ef0a2415ce36dc4d4c16e204cec3439f16d4ac93ede24e6ad790",
        )


class MainOutputTests(_TzFixed, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # main() calls setlocale(LC_TIME, ""); mirror it here so expected
        # values computed with strftime match what main() will produce.
        self._orig_locale = locale.setlocale(locale.LC_TIME)
        locale.setlocale(locale.LC_TIME, "")

    def tearDown(self):
        locale.setlocale(locale.LC_TIME, self._orig_locale)
        super().tearDown()

    def _run_main(self, resp, *, expires_at_ms=2 ** 63 - 1, now=None):
        if now is None:
            now = datetime(2026, 5, 19, 22, 6, tzinfo=timezone.utc)
        real_dt = claude_usage.datetime
        cred = {"claudeAiOauth": {"accessToken": "x", "expiresAt": expires_at_ms}}
        with mock.patch.object(claude_usage, "keychain_credentials", return_value=cred), \
             mock.patch.object(claude_usage, "fetch_usage", return_value=resp), \
             mock.patch.object(claude_usage, "datetime", wraps=real_dt) as mock_dt:
            mock_dt.now = mock.Mock(return_value=now)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    claude_usage.main()
                except SystemExit:
                    pass  # emit_error calls sys.exit(0)
        return buf.getvalue()

    def test_typical_output(self):
        resp = {
            "five_hour": {"utilization": 7.2, "resets_at": "2026-05-20T01:50:00Z"},
            "seven_day": {"utilization": 43.1, "resets_at": "2026-05-23T00:00:00Z"},
            "seven_day_sonnet": {"utilization": 0},
            "seven_day_omelette": {"utilization": 37.4, "resets_at": "2026-05-23T00:00:00Z"},
        }
        out = self._run_main(resp)
        # Reset date is rendered via the user's LC_TIME, so build the
        # expectation through strftime instead of hard-coding a format.
        week_reset = datetime(2026, 5, 23, 9, 0).strftime("%x %H:%M")
        self.assertIn("7% · 3h44m | image=", out)
        self.assertIn("5-hour session — resets 10:50 (3h44m left)", out)
        self.assertIn(f"Week (all models) — resets {week_reset}", out)
        self.assertIn("Week (Sonnet only)", out)
        self.assertNotIn("Week (Opus only)", out)
        self.assertIn(f"Claude Design — resets {week_reset}", out)
        self.assertIn("Open claude.ai usage | href=https://claude.ai/settings/usage", out)
        self.assertIn("Refresh | refresh=true", out)

    def test_opus_only_section(self):
        resp = {
            "five_hour": {"utilization": 0},
            "seven_day": {"utilization": 0},
            "seven_day_opus": {"utilization": 12},
        }
        out = self._run_main(resp)
        self.assertIn("Week (Opus only)", out)
        self.assertNotIn("Week (Sonnet only)", out)
        self.assertNotIn("Claude Design", out)

    def test_high_utilization_colors(self):
        # 5h=95 → red title; week=72 → orange somewhere.
        resp = {
            "five_hour": {"utilization": 95, "resets_at": "2026-05-20T01:50:00Z"},
            "seven_day": {"utilization": 72, "resets_at": "2026-05-23T00:00:00Z"},
        }
        out = self._run_main(resp)
        self.assertIn("color=red", out)
        self.assertIn("color=orange", out)

    def test_api_error_short_circuits(self):
        out = self._run_main({"error": {"type": "rate_limited"}})
        self.assertIn("Claude ⚠️", out)
        self.assertIn("API error: rate_limited", out)

    def test_expired_token_short_circuits(self):
        out = self._run_main({}, expires_at_ms=1)
        self.assertIn("OAuth token expired", out)


if __name__ == "__main__":
    unittest.main()
