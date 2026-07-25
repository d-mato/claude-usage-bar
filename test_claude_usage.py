"""Tests for claude-usage.5m.py — run with: python3 -m unittest test_claude_usage.py"""
import contextlib
import hashlib
import importlib.util
import io
import json
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


def usage_data(**rl_overrides):
    """A realistic get_usage control-response payload (2026-07-25 shape).

    Everything usage-related — including model_scoped and spend — nests
    inside rate_limits; keyword overrides apply at that level.
    """
    rl = {
        "five_hour": {"utilization": 7.2, "resets_at": "2026-05-20T01:50:00+00:00"},
        "seven_day": {"utilization": 43.1, "resets_at": "2026-05-23T00:00:00+00:00"},
        "model_scoped": [],
        "spend": {
            "used": {"amount_minor": 0, "currency": "USD", "exponent": 2},
            "limit": {"amount_minor": 20000, "currency": "USD", "exponent": 2},
            "percent": 0,
            "enabled": False,
            "disabled_reason": "out_of_credits",
        },
    }
    rl.update(rl_overrides)
    return {"rate_limits_available": True, "rate_limits": rl}


def control_response_line(inner, request_id=None, subtype="success"):
    return json.dumps({
        "type": "control_response",
        "response": {
            "subtype": subtype,
            "request_id": request_id or claude_usage.REQUEST_ID,
            "response": inner,
        },
    })


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


class ParseUsageResponseTests(unittest.TestCase):
    def test_picks_matching_control_response(self):
        stdout = "\n".join([
            json.dumps({"type": "system", "subtype": "init"}),
            control_response_line({"rate_limits": {}}),
        ])
        resp = claude_usage.parse_usage_response(stdout)
        self.assertEqual(resp["subtype"], "success")
        self.assertEqual(resp["response"], {"rate_limits": {}})

    def test_ignores_other_request_ids(self):
        stdout = control_response_line({}, request_id="someone-else")
        self.assertIsNone(claude_usage.parse_usage_response(stdout))

    def test_ignores_non_json_lines(self):
        stdout = "warning: something\n" + control_response_line({"x": 1})
        self.assertEqual(claude_usage.parse_usage_response(stdout)["response"], {"x": 1})

    def test_empty_stdout(self):
        self.assertIsNone(claude_usage.parse_usage_response(""))

    def test_error_subtype_passed_through(self):
        stdout = control_response_line(None, subtype="error")
        self.assertEqual(claude_usage.parse_usage_response(stdout)["subtype"], "error")


class ScopedLimitsTests(unittest.TestCase):
    def test_empty_when_absent(self):
        self.assertEqual(claude_usage.scoped_limits({}), [])
        self.assertEqual(claude_usage.scoped_limits({"model_scoped": None}), [])

    def test_typical_entry(self):
        data = {"model_scoped": [
            {"display_name": "Fable", "utilization": 4, "resets_at": "2026-07-31T23:59:59+00:00"},
        ]}
        self.assertEqual(claude_usage.scoped_limits(data), [
            {"name": "Fable", "percent": 4, "resets_at": "2026-07-31T23:59:59+00:00"},
        ])

    def test_missing_fields_get_defaults(self):
        self.assertEqual(claude_usage.scoped_limits({"model_scoped": [{}]}), [
            {"name": "Model", "percent": 0, "resets_at": ""},
        ])

    def test_non_dict_entries_skipped(self):
        self.assertEqual(claude_usage.scoped_limits({"model_scoped": ["junk"]}), [])


class FmtMoneyTests(unittest.TestCase):
    def test_dollars(self): self.assertEqual(claude_usage.fmt_money(20000), "$200.00")
    def test_zero(self): self.assertEqual(claude_usage.fmt_money(0), "$0.00")
    def test_cents(self): self.assertEqual(claude_usage.fmt_money(137), "$1.37")
    def test_exponent_zero(self): self.assertEqual(claude_usage.fmt_money(5, 0), "$5")


class SpendInfoTests(unittest.TestCase):
    def test_hidden_while_disabled_and_unused(self):
        self.assertIsNone(claude_usage.spend_info(usage_data()["rate_limits"]))

    def test_missing_spend(self):
        self.assertIsNone(claude_usage.spend_info({}))

    def test_shown_when_enabled(self):
        rl = usage_data()["rate_limits"]
        rl["spend"]["enabled"] = True
        info = claude_usage.spend_info(rl)
        self.assertEqual(info, {"used": "$0.00", "limit": "$200.00", "percent": 0})

    def test_shown_when_used_despite_disabled(self):
        rl = usage_data()["rate_limits"]
        rl["spend"]["used"]["amount_minor"] = 1337
        rl["spend"]["percent"] = 7
        info = claude_usage.spend_info(rl)
        self.assertEqual(info["used"], "$13.37")
        self.assertEqual(info["percent"], 7)

    def test_no_limit(self):
        rl = usage_data()["rate_limits"]
        rl["spend"]["enabled"] = True
        rl["spend"]["limit"] = None
        self.assertIsNone(claude_usage.spend_info(rl)["limit"])


class DonutB64Tests(unittest.TestCase):
    def test_output_stable(self):
        # Snapshot the donut PNG hash so subtle rendering regressions are caught.
        b64 = claude_usage.donut_b64(50, 65, 125, 240)
        self.assertEqual(
            hashlib.sha256(b64.encode()).hexdigest(),
            "770fa5844123ef0a2415ce36dc4d4c16e204cec3439f16d4ac93ede24e6ad790",
        )


class FetchUsageTests(unittest.TestCase):
    def _run(self, stdout, returncode=0):
        proc = mock.Mock(stdout=stdout, returncode=returncode)
        with mock.patch.object(claude_usage.subprocess, "run", return_value=proc):
            return claude_usage.fetch_usage("/fake/claude")

    def test_success(self):
        data = usage_data()
        self.assertEqual(self._run(control_response_line(data)), data)

    def test_no_response_emits_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            self._run("", returncode=1)
        self.assertIn("no get_usage response from claude (exit 1)", buf.getvalue())

    def test_error_subtype_emits_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            self._run(control_response_line(None, subtype="error"))
        self.assertIn("get_usage failed", buf.getvalue())


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

    def _run_main(self, data, *, now=None):
        if now is None:
            now = datetime(2026, 5, 19, 22, 6, tzinfo=timezone.utc)
        real_dt = claude_usage.datetime
        with mock.patch.object(claude_usage, "find_claude", return_value="/fake/claude"), \
             mock.patch.object(claude_usage, "fetch_usage", return_value=data), \
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
        out = self._run_main(usage_data())
        # Reset date is rendered via the user's LC_TIME, so build the
        # expectation through strftime instead of hard-coding a format.
        week_reset = datetime(2026, 5, 23, 9, 0).strftime("%x %H:%M")
        self.assertIn("7% · 3h44m | image=", out)
        self.assertIn("5-hour session — resets 10:50 (3h44m left)", out)
        self.assertIn(f"Week (all models) — resets {week_reset}", out)
        self.assertIn("Open claude.ai usage | href=https://claude.ai/settings/usage", out)
        self.assertIn("Refresh | refresh=true", out)
        # Credits disabled + unused, no scoped models → neither section renders.
        self.assertNotIn("Usage credits", out)
        self.assertNotIn("Fable", out)

    def test_high_utilization_colors(self):
        # 5h=95 → red title; week=72 → orange somewhere.
        data = usage_data(
            five_hour={"utilization": 95, "resets_at": "2026-05-20T01:50:00+00:00"},
            seven_day={"utilization": 72, "resets_at": "2026-05-23T00:00:00+00:00"},
        )
        out = self._run_main(data)
        self.assertIn("color=red", out)
        self.assertIn("color=orange", out)

    def test_scoped_limit_renders(self):
        data = usage_data(model_scoped=[
            {"display_name": "Fable", "utilization": 4, "resets_at": "2026-05-23T00:00:00+00:00"},
        ])
        out = self._run_main(data)
        reset = datetime(2026, 5, 23, 9, 0).strftime("%x %H:%M")
        self.assertIn(f"Fable — resets {reset}", out)
        self.assertIn("4%", out)

    def test_spend_renders_when_used(self):
        data = usage_data()
        data["rate_limits"]["spend"]["used"]["amount_minor"] = 1337
        data["rate_limits"]["spend"]["percent"] = 7
        out = self._run_main(data)
        self.assertIn("Usage credits — $13.37 / $200.00", out)

    def test_missing_rate_limits_short_circuits(self):
        out = self._run_main({"rate_limits_available": False})
        self.assertIn("Claude ⚠️", out)
        self.assertIn("no rate_limits in get_usage response", out)


if __name__ == "__main__":
    unittest.main()
