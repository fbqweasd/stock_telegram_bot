import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import scheduler
import market_calendar


class SchedulerTradingDayTests(unittest.TestCase):
    """휴장일(주말/공휴일)에 실시간 조회를 하지 않는지 검증하는 테스트"""

    def setUp(self):
        self.bot = MagicMock()
        self.scheduler = scheduler.AlertScheduler(self.bot)

    def test_us_ticker_weekend_skips_scan(self):
        """미국 주식(AAPL)이 주말(일요일)이면 실시간 조회를 건너뛰어야 함"""
        # 일요일 (2026-08-09)
        sunday = datetime(2026, 8, 9, 0, 0)

        with patch.object(market_calendar, "is_us_trading_day", return_value=False) as mock_us:
            with patch.object(self.scheduler, "_is_ticker_trading_day", return_value=False) as mock_trading:
                with patch.object(self.scheduler, "_process_ticker_alerts") as mock_process:
                    with patch.object(self.scheduler, "_check_stock_high_breakouts") as mock_high:
                        with patch("scheduler.stock_api.fetch_stock_data") as mock_fetch:
                            # 구독 티커 목록
                            with patch("scheduler.database.get_unique_tickers", return_value=["AAPL"]):
                                self.scheduler._check_all_subscribed_stocks()

                            # fetch_stock_data가 호출되지 않아야 함
                            mock_fetch.assert_not_called()
                            mock_process.assert_not_called()
                            mock_high.assert_not_called()

    def test_korea_ticker_weekend_skips_scan(self):
        """한국 주식(005930.KS)이 주말(일요일)이면 실시간 조회를 건너뛰어야 함"""
        # 일요일 (2026-08-09)
        sunday = datetime(2026, 8, 9, 0, 0)

        with patch.object(market_calendar, "is_korea_trading_day", return_value=False) as mock_kr:
            with patch.object(self.scheduler, "_is_ticker_trading_day", return_value=False) as mock_trading:
                with patch.object(self.scheduler, "_process_ticker_alerts") as mock_process:
                    with patch.object(self.scheduler, "_check_stock_high_breakouts") as mock_high:
                        with patch("scheduler.stock_api.fetch_stock_data") as mock_fetch:
                            with patch("scheduler.database.get_unique_tickers", return_value=["005930.KS"]):
                                self.scheduler._check_all_subscribed_stocks()

                            mock_fetch.assert_not_called()
                            mock_process.assert_not_called()
                            mock_high.assert_not_called()

    def test_us_ticker_weekday_scans(self):
        """미국 주식(AAPL)이 평일(거래일)이면 실시간 조회를 수행해야 함"""
        with patch.object(self.scheduler, "_is_ticker_trading_day", return_value=True) as mock_trading:
            with patch.object(self.scheduler, "_process_ticker_alerts") as mock_process:
                with patch.object(self.scheduler, "_check_stock_high_breakouts") as mock_high:
                    with patch("scheduler.stock_api.fetch_stock_data") as mock_fetch:
                        mock_fetch.return_value = {
                            "ticker": "AAPL",
                            "name": "Apple Inc.",
                            "currency": "USD",
                            "current_price": 200.0,
                            "previous_close": 195.0,
                            "market_state": "REGULAR",
                            "timestamps": [],
                            "closes": [190.0, 195.0, 200.0],
                            "highs": [191.0, 196.0, 201.0],
                            "lows": [189.0, 194.0, 199.0],
                            "opens": [190.0, 195.0, 200.0],
                            "volumes": [1000, 1000, 1000]
                        }

                        with patch("scheduler.database.get_unique_tickers", return_value=["AAPL"]):
                            self.scheduler._check_all_subscribed_stocks()

                        mock_fetch.assert_called_once()
                        mock_process.assert_called_once()
                        mock_high.assert_called_once()

    def test_is_ticker_trading_day_korea(self):
        """한국 주식 티커(.KS)는 한국 시장 거래일을 확인해야 함"""
        with patch.object(market_calendar, "is_korea_trading_day", return_value=True) as mock_kr:
            with patch.object(market_calendar, "is_us_trading_day", return_value=False) as mock_us:
                result = self.scheduler._is_ticker_trading_day("005930.KS")
                self.assertTrue(result)
                mock_kr.assert_called_once()
                mock_us.assert_not_called()

    def test_is_ticker_trading_day_us(self):
        """미국 주식 티커는 미국 시장 거래일을 확인해야 함"""
        with patch.object(market_calendar, "is_korea_trading_day", return_value=False) as mock_kr:
            with patch.object(market_calendar, "is_us_trading_day", return_value=True) as mock_us:
                result = self.scheduler._is_ticker_trading_day("AAPL")
                self.assertTrue(result)
                mock_us.assert_called_once()
                mock_kr.assert_not_called()

    def test_index_high_breakouts_skipped_on_weekend(self):
        """주말에는 지수 최고치 돌파 체크를 건너뛰어야 함"""
        with patch.object(market_calendar, "is_korea_trading_day", return_value=False) as mock_kr:
            with patch.object(market_calendar, "is_us_trading_day", return_value=False) as mock_us:
                with patch("scheduler.database.get_all_subscriptions", return_value=[(123, "AAPL")]):
                    with patch("scheduler.market_indices.fetch_all_index_highs") as mock_highs:
                        self.scheduler._check_index_high_breakouts()
                        mock_highs.assert_not_called()

    def test_index_high_breakouts_runs_on_trading_day(self):
        """거래일에는 지수 최고치 돌파 체크를 수행해야 함"""
        with patch.object(market_calendar, "is_korea_trading_day", return_value=True) as mock_kr:
            with patch.object(market_calendar, "is_us_trading_day", return_value=True) as mock_us:
                with patch("scheduler.database.get_all_subscriptions", return_value=[(123, "AAPL")]):
                    with patch("scheduler.market_indices.fetch_all_index_highs") as mock_highs:
                        mock_highs.return_value = {"sp500": {"all_time_high": 5000.0}}
                        with patch("scheduler.market_indices.fetch_market_indices", return_value={}):
                            with patch("scheduler.market_indices.fetch_korea_market_indices", return_value={}):
                                with patch("scheduler.market_indices.check_index_high_breakouts", return_value=[]):
                                    self.scheduler._check_index_high_breakouts()
                                    mock_highs.assert_called_once()


if __name__ == "__main__":
    unittest.main()