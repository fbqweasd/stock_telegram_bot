import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import stock_api
import telegram_bot
from telegram_bot import TelegramBot


def _fake_full_data(ticker, price=100.0, prev_close=90.0):
    """fetch_stock_data 반환값 형태의 최소 데이터를 만듭니다."""
    return {
        "ticker": ticker,
        "name": f"Name {ticker}",
        "currency": "USD",
        "current_price": price,
        "previous_close": prev_close,
        "market_state": "REGULAR",
        "timestamps": [], "closes": [], "highs": [], "lows": [], "opens": [], "volumes": [],
    }


class HandleListParallelTests(unittest.TestCase):
    def _make_bot(self):
        return TelegramBot()

    def test_handle_list_runs_in_parallel(self):
        """종목별 조회가 병렬로 실행되어 종목 수와 무관하게 빨라야 한다"""
        tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "NVDA"]
        sent = []
        calls = {"n": 0}

        def slow_fetch(ticker, price_cache=None):
            calls["n"] += 1
            time.sleep(0.3)
            return _fake_full_data(ticker)

        bot = self._make_bot()
        with patch("telegram_bot.database.get_user_subscriptions", return_value=tickers), \
             patch.object(stock_api, "is_toss_enabled", return_value=False), \
             patch.object(stock_api, "fetch_stock_data", side_effect=slow_fetch), \
             patch.object(bot, "send_message", side_effect=lambda *a, **k: sent.append(a[1]) or 1234), \
             patch.object(bot, "delete_message", return_value=None):
            start = time.time()
            bot._handle_list(1)
            elapsed = time.time() - start

        self.assertEqual(calls["n"], len(tickers))
        # 순차 실행이면 6 x 0.3s = 1.8초 이상, 병렬이면 1초 내외
        self.assertLess(elapsed, 1.5)
        self.assertEqual(len(sent), 2)  # 로딩 메시지 + 결과 메시지
        result = sent[-1]
        self.assertIn("나의 관심 주식 리스트", result)
        for ticker in tickers:
            self.assertIn(ticker, result)

    def test_handle_list_order_preserved(self):
        """병렬 조회 후에도 출력 순서는 구독 순서를 유지해야 한다"""
        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE"]

        bot = self._make_bot()
        with patch("telegram_bot.database.get_user_subscriptions", return_value=tickers), \
             patch.object(stock_api, "is_toss_enabled", return_value=False), \
             patch.object(stock_api, "fetch_stock_data",
                          side_effect=lambda t, pc=None: _fake_full_data(t)), \
             patch.object(telegram_bot.predictor, "predict_buy_sell_prices",
                          return_value={"recommendation": "BUY", "confidence": 70}), \
             patch.object(bot, "send_message", side_effect=lambda *a, **k: a[1] or 1234), \
             patch.object(bot, "delete_message", return_value=None):
            bot._handle_list(1)

    def test_handle_list_order_preserved_check(self):
        """병렬 조회 후에도 출력 줄 순서가 구독 순서와 일치해야 한다"""
        tickers = ["AAA", "BBB", "CCC", "DDD"]
        sent = []

        bot = TelegramBot()
        with patch("telegram_bot.database.get_user_subscriptions", return_value=tickers), \
             patch.object(stock_api, "is_toss_enabled", return_value=False), \
             patch.object(stock_api, "fetch_stock_data",
                          side_effect=lambda t, pc=None: _fake_full_data(t)), \
             patch.object(bot, "send_message", side_effect=lambda *a, **k: sent.append(a[1]) or 1234), \
             patch.object(bot, "delete_message", return_value=None):
            bot._handle_list(1)

        result = sent[-1]
        positions = [result.index(f"{i + 1}. <b>Name {t}</b>") for i, t in enumerate(tickers)]
        self.assertEqual(positions, sorted(positions))


class FetchCurrentPricesBatchTests(unittest.TestCase):
    def test_missing_tickers_fetched_in_parallel(self):
        """토스 배치 누락 종목의 개별 보완 조회도 병렬로 실행되어야 한다"""
        tickers = ["AAA", "BBB", "CCC", "DDD"]

        def slow_price(ticker, price_cache=None, allow_toss=True):
            time.sleep(0.4)
            return {"price": 10.0, "previous_close": 9.0, "currency": "USD"}

        with patch.object(stock_api.toss_api, "is_configured", return_value=False), \
             patch.object(stock_api, "fetch_current_price_only", side_effect=slow_price):
            start = time.time()
            result = stock_api.fetch_current_prices_batch(tickers)
            elapsed = time.time() - start

        self.assertEqual(set(result.keys()), set(tickers))
        # 순차 실행이면 4 x 0.4s = 1.6초 이상, 병렬이면 1초 미만
        self.assertLess(elapsed, 1.2)

    def test_batch_handles_individual_failures(self):
        """개별 조회 중 예외가 발생해도 전체 결과는 정상 반환되어야 한다"""
        def boom(ticker, price_cache=None, allow_toss=True):
            raise RuntimeError("fail")

        with patch.object(stock_api.toss_api, "is_configured", return_value=False), \
             patch.object(stock_api, "fetch_current_price_only", side_effect=boom):
            result = stock_api.fetch_current_prices_batch(["XXX", "YYY"])

        self.assertEqual(result, {})


class BuildListRowTests(unittest.TestCase):
    def setUp(self):
        self.bot = TelegramBot()

    def test_full_data_row_format(self):
        with patch.object(stock_api, "fetch_stock_data",
                          return_value=_fake_full_data("AAPL", 105.0, 100.0)), \
             patch.object(telegram_bot.predictor, "predict_buy_sell_prices",
                          return_value={"recommendation": "STRONG BUY", "confidence": 88}):
            row = self.bot._build_list_row(3, "AAPL")

        self.assertTrue(row.startswith("3. "))
        self.assertIn("Name AAPL", row)
        self.assertIn("105.00 USD", row)
        self.assertIn("+5.00%", row)
        self.assertIn("🟢🔥", row)

    def test_price_cache_preferred_and_passed(self):
        """토스 배치 캐시 가격을 우선 사용하고 fetch_stock_data에 캐시를 전달해야 한다"""
        cache = {"AAPL": {"price": 111.0, "previous_close": 100.0, "currency": "USD"}}
        with patch.object(stock_api, "fetch_stock_data",
                          return_value=_fake_full_data("AAPL", 105.0, 100.0)) as mock_fetch:
            row = self.bot._build_list_row(1, "AAPL", cache)

        mock_fetch.assert_called_once_with("AAPL", cache)
        self.assertIn("111.00 USD", row)
        self.assertIn("+11.00%", row)

    def test_fallback_to_light_price(self):
        """전체 데이터 조회 실패 시 가벼운 현재가 조회로 폴백해야 한다"""
        with patch.object(stock_api, "fetch_stock_data", return_value=None), \
             patch.object(stock_api, "fetch_current_price_only",
                          return_value={"price": 50.0, "previous_close": 55.0, "currency": "USD"}):
            row = self.bot._build_list_row(2, "TSLA")

        self.assertIn("TSLA", row)
        self.assertIn("50.00 USD", row)
        self.assertIn("-9.09%", row)

    def test_total_failure_row(self):
        """모든 조회가 실패하면 실패 안내 줄을 반환해야 한다"""
        with patch.object(stock_api, "fetch_stock_data", return_value=None), \
             patch.object(stock_api, "fetch_current_price_only", return_value=None):
            row = self.bot._build_list_row(1, "XXX")

        self.assertIn("데이터 로드 실패", row)

    def test_row_never_raises(self):
        """행 생성 중 예외가 발생해도 실패 안내 줄을 반환해야 한다 (병렬 실행 안전성)"""
        def raiser(*args, **kwargs):
            raise RuntimeError("boom")

        with patch.object(stock_api, "fetch_stock_data", side_effect=raiser), \
             patch.object(stock_api, "fetch_current_price_only", side_effect=raiser):
            row = self.bot._build_list_row(1, "YYY")

        self.assertIn("데이터 로드 실패", row)

    def test_change_str_variants(self):
        self.assertEqual(TelegramBot._build_change_str(100.0, 100.0), " (보합)")
        self.assertIn("+10.00%", TelegramBot._build_change_str(110.0, 100.0))
        self.assertIn("-10.00%", TelegramBot._build_change_str(90.0, 100.0))
        self.assertEqual(TelegramBot._build_change_str(110.0, None), "")
        self.assertEqual(TelegramBot._build_change_str(110.0, 0), "")

    def test_recommendation_str_variants(self):
        cases = [
            ({"recommendation": "STRONG BUY", "confidence": 88}, "🟢🔥"),
            ({"recommendation": "BUY", "confidence": 60}, "🟢"),
            ({"recommendation": "STRONG SELL", "confidence": 90}, "🔴🔥"),
            ({"recommendation": "SELL", "confidence": 55}, "🔴"),
            ({"recommendation": "HOLD", "confidence": 50}, "🟡"),
        ]
        for analysis, emoji in cases:
            with patch.object(telegram_bot.predictor, "predict_buy_sell_prices", return_value=analysis):
                self.assertIn(emoji, TelegramBot._build_recommendation_str({}))

        with patch.object(telegram_bot.predictor, "predict_buy_sell_prices",
                          return_value={"error": "not enough data"}):
            self.assertEqual(TelegramBot._build_recommendation_str({}), "")

        def raiser(_):
            raise RuntimeError("x")

        with patch.object(telegram_bot.predictor, "predict_buy_sell_prices", side_effect=raiser):
            self.assertEqual(TelegramBot._build_recommendation_str({}), "")


if __name__ == "__main__":
    unittest.main()