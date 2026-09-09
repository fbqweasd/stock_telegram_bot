import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import market_indices
import scheduler


def stamp(day, hour=9, minute=0):
    return datetime(2026, 9, day, hour, minute,
                    tzinfo=timezone(timedelta(hours=9))).timestamp()


class ConfirmedCloseTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "meta": {"regularMarketPrice": 2650.5,
                     "regularMarketTime": stamp(9, 15, 30),
                     "currentTradingPeriod": {"regular": {"end": stamp(9, 15, 30)}}},
            "timestamp": [stamp(7), stamp(8), stamp(9)],
            "indicators": {"quote": [{"close": [2500.0, 2638.2, 2650.5]}]},
        }
        market_indices._result_cache.clear()

    def fetch(self):
        with patch.object(market_indices, "_make_request", return_value=json.dumps(
                {"chart": {"result": [self.result]}})) as request:
            result = market_indices._fetch_korea_index_close("^KS11", "KOSPI", "2026-09-09")
        self.assertIn("includePrePost=false", request.call_args.args[0])
        return result

    def test_close_and_previous_trading_day(self):
        result = self.fetch()
        self.assertEqual(result["value"], 2650.5)
        self.assertEqual(result["previous_close"], 2638.2)
        self.assertEqual(result["change"], 12.3)
        self.assertEqual(result["change_pct"], 0.47)

    def test_delayed_intraday_quote_is_not_close(self):
        self.result["meta"]["regularMarketTime"] = stamp(9, 15, 29)
        self.assertIsNone(self.fetch())

    def test_previous_date_quote_is_rejected(self):
        self.result["meta"]["regularMarketTime"] = stamp(8, 18)
        self.assertIsNone(self.fetch())

    def test_stale_or_missing_daily_close_is_rejected(self):
        for value in (2600, None, float("nan"), 0):
            with self.subTest(value=value):
                self.result["indicators"]["quote"][0]["close"][-1] = value
                self.assertIsNone(self.fetch())

    def test_missing_today_does_not_use_yesterday(self):
        self.result["timestamp"].pop()
        self.assertIsNone(self.fetch())

    def test_extended_session_must_finish(self):
        self.result["meta"]["currentTradingPeriod"]["regular"]["end"] = stamp(9, 16, 30)
        self.assertIsNone(self.fetch())

    def test_invalid_previous_close_is_not_skipped(self):
        self.result["indicators"]["quote"][0]["close"][1] = None
        self.assertIsNone(self.fetch())

    def test_incomplete_result_is_not_cached(self):
        complete = {"kospi": {"value": 2650.5}, "kosdaq": {"value": 900}}
        with patch.object(market_indices, "fetch_korea_market_closing_indices",
                          side_effect=[{"kospi": complete["kospi"]}, complete]) as fetch, \
             patch.object(market_indices, "fetch_usd_krw"), \
             patch.object(market_indices, "fetch_fear_greed_index"), \
             patch.object(market_indices, "fetch_vix"), \
             patch.object(market_indices, "fetch_market_indices"):
            self.assertIsNone(market_indices.fetch_korea_market_close_data("2026-09-09"))
            self.assertEqual(market_indices.fetch_korea_market_close_data("2026-09-09")["korea_indices"], complete)
            self.assertEqual(fetch.call_count, 2)

    def test_scheduler_retries_then_sends_once_even_after_17(self):
        bot = MagicMock()
        job = scheduler.AlertScheduler(bot)
        with patch("scheduler.market_calendar.get_korea_now", return_value=datetime(2026, 9, 9, 18)), \
             patch("scheduler.market_calendar.is_korea_trading_day", return_value=True), \
             patch("scheduler.database.get_all_subscriptions", return_value=[(123, "AAPL")]), \
             patch("scheduler.database.should_send_alert", return_value=True), \
             patch("scheduler.market_indices.fetch_korea_market_close_data", side_effect=[None, {"date": "2026-09-09"}]) as fetch, \
             patch.object(job, "_send_alert_with_topic", return_value=1) as send:
            job._check_korea_market_close_alert()
            send.assert_not_called()
            self.assertIsNone(job.last_korea_market_close_alert_date)
            job._check_korea_market_close_alert()
            job._check_korea_market_close_alert()
            send.assert_called_once()
            self.assertEqual(fetch.call_count, 2)
            fetch.assert_called_with("2026-09-09")

    def test_missing_close_has_readable_manual_report(self):
        self.assertIn("아직 확인되지", market_indices.format_korea_market_close_report(None))


class KoreaCloseTimingTests(unittest.TestCase):
    def setUp(self):
        self.job = scheduler.AlertScheduler(MagicMock())

    def test_wait_targets_153000_with_subsecond_precision(self):
        with patch("scheduler.market_calendar.is_korea_trading_day", return_value=True):
            for now, expected in (
                (datetime(2026, 9, 9, 14), 60),
                (datetime(2026, 9, 9, 15, 29, 59, 750000), 0.25),
                (datetime(2026, 9, 9, 15, 30), 0),
                (datetime(2026, 9, 9, 18), 0),
            ):
                with self.subTest(now=now), patch(
                    "scheduler.market_calendar.get_korea_now", return_value=now
                ):
                    self.assertEqual(self.job._korea_close_wait_seconds(), expected)

    def test_loop_starts_at_close_and_retries_ten_seconds_later(self):
        now = datetime(2026, 9, 9, 15, 29, 59, 750000)
        checked_at = []

        def wait(seconds):
            nonlocal now
            now += timedelta(seconds=seconds)

        def check():
            checked_at.append(now)
            if len(checked_at) == 2:
                self.job.stop()

        with patch("scheduler.market_calendar.get_korea_now", side_effect=lambda: now), \
             patch("scheduler.market_calendar.is_korea_trading_day", return_value=True), \
             patch.object(self.job._stop_event, "wait", side_effect=wait), \
             patch.object(self.job, "_check_korea_market_close_alert", side_effect=check):
            self.job._run_korea_close_loop()
        self.assertEqual(checked_at, [datetime(2026, 9, 9, 15, 30),
                                      datetime(2026, 9, 9, 15, 30, 10)])

    def test_holidays_and_sent_dates_do_not_trigger_queries(self):
        with patch("scheduler.market_calendar.get_korea_now", return_value=datetime(2026, 9, 9, 16)), \
             patch("scheduler.market_calendar.is_korea_trading_day", return_value=False):
            self.assertEqual(self.job._korea_close_wait_seconds(), 60)
        self.job.last_korea_market_close_alert_date = "2026-09-09"
        with patch("scheduler.market_calendar.get_korea_now", return_value=datetime(2026, 9, 9, 16)):
            self.assertEqual(self.job._korea_close_wait_seconds(), 60)

    def test_start_uses_separate_worker_and_is_idempotent(self):
        with patch("scheduler.threading.Thread") as thread:
            self.job.start()
            self.job.start()
            self.assertEqual(thread.call_count, 2)
            targets = [call.kwargs["target"] for call in thread.call_args_list]
            self.assertIn(self.job._run_loop, targets)
            self.assertIn(self.job._run_korea_close_loop, targets)
            self.job.stop()
        self.assertTrue(self.job._stop_event.is_set())

    def test_regular_scan_does_not_send_korea_close(self):
        self.job.is_running = True
        with patch("scheduler.time.sleep"), \
             patch.object(self.job, "_check_weekly_report"), \
             patch.object(self.job, "_check_us_market_close_alert"), \
             patch.object(self.job, "_check_extreme_market_conditions"), \
             patch.object(self.job, "_check_index_high_breakouts"), \
             patch.object(self.job, "_check_all_subscribed_stocks", side_effect=self.job.stop), \
             patch.object(self.job, "_check_korea_market_close_alert") as korea:
            self.job._run_loop()
        korea.assert_not_called()


if __name__ == "__main__":
    unittest.main()
