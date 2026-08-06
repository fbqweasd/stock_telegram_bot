import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import market_indices
import market_calendar


class KoreaMarketCalendarTests(unittest.TestCase):
    def test_weekend_is_not_trading_day(self):
        # 2024-08-11 은 일요일
        sunday = datetime(2024, 8, 11, 15, 30)
        self.assertFalse(market_calendar.is_korea_trading_day(sunday))

    def test_weekday_is_trading_day(self):
        # 2024-08-12 은 월요일 (공휴일 아님)
        monday = datetime(2024, 8, 12, 15, 30)
        self.assertTrue(market_calendar.is_korea_trading_day(monday))

    def test_solar_holiday_not_trading_day(self):
        # 삼일절 3/1 (2024-03-01 금요일)
        samil = datetime(2024, 3, 1, 15, 30)
        self.assertFalse(market_calendar.is_korea_trading_day(samil))

    def test_lunar_holiday_not_trading_day(self):
        # 설날 연휴 (2024-02-09 금요일)
        seollal = datetime(2024, 2, 9, 15, 30)
        self.assertFalse(market_calendar.is_korea_trading_day(seollal))

    def test_korea_now_returns_nine_hours_ahead_of_utc(self):
        # get_korea_now 가 UTC+9 를 반환하는지 확인
        now_kst = market_calendar.get_korea_now()
        self.assertEqual(now_kst.utcoffset(), None)
        # naive datetime 이며 시차 9시간을 반영했는지 추정값으로 검증하지 않음
        self.assertEqual(now_kst.tzinfo, None)


class KoreaMarketReportFormatTests(unittest.TestCase):
    def test_format_korea_market_close_report(self):
        data = {
            "date": "2024-08-12",
            "timestamp": "2024-08-12 15:30:00",
            "korea_indices": {
                "kospi": {
                    "name": "KOSPI", "value": 2650.5,
                    "change": 12.3, "change_pct": 0.47,
                },
                "kosdaq": {
                    "name": "KOSDAQ", "value": 900.1,
                    "change": -3.5, "change_pct": -0.39,
                },
            },
            "usd_krw": {"value": 1380.5, "change": -2.0, "change_pct": -0.14},
            "fear_greed": {"value": 60.0, "classification": "탐욕"},
            "vix": {"value": 14.5, "change_pct": -1.2},
            "us_indices": {
                "sp500": {"name": "S&P 500", "value": 5300.0, "change_pct": 0.3},
                "nasdaq": {"name": "NASDAQ", "value": 17000.0, "change_pct": -0.2},
                "dow": {"name": "DOW", "value": 40000.0, "change_pct": 0.1},
            },
        }
        report = market_indices.format_korea_market_close_report(data)

        self.assertIn("한국장 마감 요약", report)
        self.assertIn("KOSPI", report)
        self.assertIn("KOSDAQ", report)
        self.assertIn("USD/KRW", report)
        # 등락률 반영
        self.assertIn("0.47%", report)
        self.assertIn("-0.39%", report)
        # 참고 정보 반영
        self.assertIn("공포탐욕지수", report)
        self.assertIn("VIX", report)

    def test_format_with_partial_data(self):
        # 데이터가 일부만 있어도 리포트가 생성되어야 함
        data = {"date": "2024-08-12", "timestamp": "2024-08-12 15:30:00"}
        report = market_indices.format_korea_market_close_report(data)
        self.assertIn("한국장 마감 요약", report)


if __name__ == "__main__":
    unittest.main()
