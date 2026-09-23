import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import stock_api


KST = timezone(timedelta(hours=9))
EDT = timezone(timedelta(hours=-4))


def chart(tz, last_day, regular_start):
    dates = [datetime(2026, 8, day, 12, tzinfo=tz) for day in range(1, 20)]
    dates += [datetime(2026, 9, 23, 12, tzinfo=tz)]
    if last_day == 24:
        dates += [datetime(2026, 9, 24, 12, tzinfo=tz)]
        closes = [100.0] * (len(dates) - 2) + [105.0, 110.0]
    else:
        closes = [100.0] * (len(dates) - 1) + [105.0]
    return {"chart": {"result": [{
        "meta": {
            "currency": "KRW" if tz == KST else "USD",
            "currentTradingPeriod": {"regular": {"start": regular_start.timestamp()}},
            "previousClose": 99.0,
        },
        "timestamp": [int(day.timestamp()) for day in dates],
        "indicators": {"quote": [{
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [100] * len(closes),
        }]},
    }]}}


class PreviousCloseTests(unittest.TestCase):
    def check_daily(self, ticker, tz, now, last_day, regular_start, expected):
        with patch("stock_api._make_request", return_value=chart(tz, last_day, regular_start)), \
             patch("toss_api.time.time", return_value=now.timestamp()):
            daily = stock_api._get_daily_data(ticker)
        self.assertEqual(daily["previous_close"], expected)

    def test_us_after_close_when_trading_period_points_to_tomorrow(self):
        self.check_daily(
            "AAPL", EDT, datetime(2026, 9, 24, 17, tzinfo=EDT), 24,
            datetime(2026, 9, 25, 9, 30, tzinfo=EDT), 105.0,
        )

    def test_korea_after_close_when_trading_period_points_to_tomorrow(self):
        self.check_daily(
            "005930.KS", KST, datetime(2026, 9, 24, 16, tzinfo=KST), 24,
            datetime(2026, 9, 25, 9, tzinfo=KST), 105.0,
        )

    def test_during_market_with_today_candle(self):
        self.check_daily(
            "AAPL", EDT, datetime(2026, 9, 24, 12, 30, tzinfo=EDT), 24,
            datetime(2026, 9, 24, 9, 30, tzinfo=EDT), 105.0,
        )

    def test_before_market_without_today_candle(self):
        self.check_daily(
            "AAPL", EDT, datetime(2026, 9, 24, 8, tzinfo=EDT), 23,
            datetime(2026, 9, 24, 9, 30, tzinfo=EDT), 105.0,
        )


if __name__ == "__main__":
    unittest.main()
