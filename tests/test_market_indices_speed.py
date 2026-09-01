import json
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import market_indices


def _make_chart_response(current_price, previous_close):
    """Yahoo chart API 응답 형태의 최소 JSON을 만듭니다."""
    payload = {
        "chart": {
            "result": [{
                "meta": {"regularMarketPrice": current_price},
                "timestamp": [1700000000, 1700086400],
                "indicators": {"quote": [{"close": [previous_close, current_price]}]},
            }],
            "error": None,
        }
    }
    return json.dumps(payload)


class RunConcurrentlyTests(unittest.TestCase):
    def test_tasks_run_in_parallel(self):
        """여러 작업이 동시에 실행되어 순차 실행보다 빨라야 한다"""
        def slow_task():
            time.sleep(0.4)
            return "ok"

        tasks = {f"task_{i}": slow_task for i in range(4)}

        start = time.time()
        results = market_indices._run_concurrently(tasks)
        elapsed = time.time() - start

        self.assertEqual(results, {f"task_{i}": "ok" for i in range(4)})
        # 순차 실행이면 약 1.6초, 병렬이면 1초 미만
        self.assertLess(elapsed, 1.2)

    def test_exception_maps_to_none(self):
        def bad():
            raise ValueError("boom")

        results = market_indices._run_concurrently({"bad": bad, "good": lambda: 42})
        self.assertIsNone(results["bad"])
        self.assertEqual(results["good"], 42)

    def test_empty_tasks(self):
        self.assertEqual(market_indices._run_concurrently({}), {})


class FetchYahooQuoteTests(unittest.TestCase):
    def test_parses_value_change_pct(self):
        response = _make_chart_response(105.0, 100.0)
        with patch.object(market_indices, "_make_request", return_value=response):
            quote = market_indices._fetch_yahoo_quote("^VIX", "VIX")

        self.assertEqual(quote["value"], 105.0)
        self.assertEqual(quote["change"], 5.0)
        self.assertEqual(quote["change_pct"], 5.0)
        self.assertEqual(quote["previous_close"], 100.0)

    def test_none_response_returns_none(self):
        with patch.object(market_indices, "_make_request", return_value=None):
            self.assertIsNone(market_indices._fetch_yahoo_quote("^VIX", "VIX"))

def _make_daum_exchange_response(items):
    """Daum 금융 환율 summaries API 응답 형태의 최소 JSON을 만듭니다."""
    return json.dumps({"data": items})


def _make_daum_usd_item(base_price, change, change_price, change_rate):
    """Daum 금융 USD/KRW 항목을 만듭니다."""
    return {
        "symbolCode": "FRX.KRWUSD",
        "currencyCode": "USD",
        "name": "미국 (USD/KRW)",
        "basePrice": base_price,
        "change": change,
        "changePrice": change_price,
        "changeRate": change_rate,
    }


class FetchUsdKrwTests(unittest.TestCase):
    def test_daum_rise(self):
        """상승장: changePrice는 절대값이며 changeRate 부호로 등락폭/등락률을 계산해야 한다"""
        payload = _make_daum_exchange_response([
            _make_daum_usd_item(1374.0, "RISE", 4.5, 0.0032858708),
            {"currencyCode": "JPY", "basePrice": 858.32},
        ])
        with patch.object(market_indices, "_make_request", return_value=payload):
            result = market_indices.fetch_usd_krw()

        self.assertEqual(result["value"], 1374.0)
        self.assertEqual(result["change"], 4.5)
        self.assertAlmostEqual(result["change_pct"], 0.33, places=2)
        self.assertEqual(result["previous_close"], 1369.5)

    def test_daum_fall(self):
        """하락장: 등락폭이 음수로 변환되어야 한다"""
        payload = _make_daum_exchange_response([
            _make_daum_usd_item(1370.0, "FALL", 6.0, -0.0043731778),
        ])
        with patch.object(market_indices, "_make_request", return_value=payload):
            result = market_indices.fetch_usd_krw()

        self.assertEqual(result["value"], 1370.0)
        self.assertEqual(result["change"], -6.0)
        self.assertAlmostEqual(result["change_pct"], -0.44, places=2)
        self.assertEqual(result["previous_close"], 1376.0)

    def test_daum_even(self):
        """보합: 등락폭/등락률이 0이어야 한다"""
        payload = _make_daum_exchange_response([
            _make_daum_usd_item(1370.0, "EVEN", 0.0, 0.0),
        ])
        with patch.object(market_indices, "_make_request", return_value=payload):
            result = market_indices.fetch_usd_krw()

        self.assertEqual(result["value"], 1370.0)
        self.assertEqual(result["change"], 0.0)
        self.assertEqual(result["change_pct"], 0.0)

    def test_daum_failure_falls_back_to_yahoo(self):
        """Daum API 실패 시에만 Yahoo KRW=X로 폴백해야 한다"""
        yahoo_payload = _make_chart_response(1350.0, 1330.0)
        calls = {"n": 0}

        def fake_request(url, *args, **kwargs):
            calls["n"] += 1
            if "finance.daum.net" in url:
                return None
            return yahoo_payload

        with patch.object(market_indices, "_make_request", side_effect=fake_request):
            result = market_indices.fetch_usd_krw()

        self.assertEqual(calls["n"], 2)
        self.assertEqual(result["value"], 1350.0)

    def test_daum_success_does_not_call_yahoo(self):
        """Daum이 성공하면 Yahoo는 호출하지 않아야 한다 (부하 최소화)"""
        payload = _make_daum_exchange_response([
            _make_daum_usd_item(1374.0, "RISE", 4.5, 0.0032858708),
        ])
        calls = {"n": 0}

        def fake_request(url, *args, **kwargs):
            calls["n"] += 1
            return payload

        with patch.object(market_indices, "_make_request", side_effect=fake_request):
            result = market_indices.fetch_usd_krw()

        self.assertEqual(calls["n"], 1)
        self.assertEqual(result["value"], 1374.0)


class FetchMarketIndicesTests(unittest.TestCase):
    def _fake_request_factory(self, responses):
        def fake_request(url, *args, **kwargs):
            for symbol, response in responses.items():
                if market_indices.urllib.parse.quote(symbol) in url:
                    return response
            return None
        return fake_request

    def test_fetch_market_indices_parallel(self):
        """4개 지수를 병렬로 조회하며 각 항목에 name이 포함되어야 한다"""
        responses = {
            "^GSPC": _make_chart_response(5000.0, 4900.0),
            "^IXIC": _make_chart_response(17000.0, 17050.0),
            "^NDX": _make_chart_response(18000.0, 18000.0),
            "^DJI": _make_chart_response(40000.0, 40000.0),
        }

        with patch.object(market_indices, "_make_request",
                          side_effect=self._fake_request_factory(responses)):
            result = market_indices.fetch_market_indices()

        self.assertEqual(set(result.keys()), {"sp500", "nasdaq", "nasdaq100", "dow"})
        self.assertEqual(result["sp500"]["name"], "S&P 500")
        self.assertEqual(result["sp500"]["value"], 5000.0)
        self.assertEqual(result["sp500"]["change_pct"],
                         round((5000.0 - 4900.0) / 4900.0 * 100, 2))

    def test_partial_failure_keeps_other_indices(self):
        """일부 지수 조회 실패 시 나머지는 정상 반환되어야 한다"""
        responses = {
            "^GSPC": _make_chart_response(5000.0, 4900.0),
            "^IXIC": None,
            "^NDX": _make_chart_response(18000.0, 17900.0),
            "^DJI": _make_chart_response(40000.0, 40000.0),
        }

        with patch.object(market_indices, "_make_request",
                          side_effect=self._fake_request_factory(responses)):
            result = market_indices.fetch_market_indices()

        self.assertNotIn("nasdaq", result)
        self.assertIn("sp500", result)
        self.assertIn("nasdaq100", result)
        self.assertIn("dow", result)

    def test_fetch_korea_market_indices(self):
        """KOSPI/KOSDAQ 병렬 조회"""
        responses = {
            "^KS11": _make_chart_response(2650.5, 2638.2),
            "^KQ11": _make_chart_response(900.1, 903.6),
        }

        with patch.object(market_indices, "_make_request",
                          side_effect=self._fake_request_factory(responses)):
            result = market_indices.fetch_korea_market_indices()

        self.assertEqual(set(result.keys()), {"kospi", "kosdaq"})
        self.assertEqual(result["kospi"]["name"], "KOSPI")
        self.assertEqual(result["kospi"]["value"], 2650.5)


class AggregateFetchTests(unittest.TestCase):
    def setUp(self):
        market_indices._result_cache.clear()

    def tearDown(self):
        market_indices._result_cache.clear()

    def test_fetch_all_indices_merges_all_sources(self):
        with patch.object(market_indices, "fetch_fear_greed_index", return_value={"value": 50.0}), \
             patch.object(market_indices, "fetch_vix", return_value={"value": 14.0}), \
             patch.object(market_indices, "fetch_market_indices",
                          return_value={"sp500": {"name": "S&P 500", "value": 5000.0}}), \
             patch.object(market_indices, "fetch_usd_krw", return_value={"value": 1350.0}), \
             patch.object(market_indices, "fetch_us_treasury_10y", return_value={"value": 4.25}), \
             patch.object(market_indices, "fetch_us_dollar_index", return_value={"value": 103.5}):
            data = market_indices.fetch_all_indices()

        self.assertEqual(data["fear_greed"]["value"], 50.0)
        self.assertEqual(data["vix"]["value"], 14.0)
        self.assertIn("sp500", data["indices"])
        self.assertEqual(data["usd_krw"]["value"], 1350.0)
        self.assertEqual(data["treasury_10y"]["value"], 4.25)
        self.assertEqual(data["us_dollar_index"]["value"], 103.5)
        self.assertIn("timestamp", data)

    def test_fetch_all_indices_cached(self):
        """TTL 캐시가 동작하여 반복 호출 시 재조회하지 않아야 한다"""
        calls = {"n": 0}

        def fake_fg():
            calls["n"] += 1
            return {"value": 50.0}

        with patch.object(market_indices, "fetch_fear_greed_index", fake_fg), \
             patch.object(market_indices, "fetch_vix", return_value=None), \
             patch.object(market_indices, "fetch_market_indices", return_value={}), \
             patch.object(market_indices, "fetch_usd_krw", return_value=None), \
             patch.object(market_indices, "fetch_us_treasury_10y", return_value=None), \
             patch.object(market_indices, "fetch_us_dollar_index", return_value=None):
            first = market_indices.fetch_all_indices()
            second = market_indices.fetch_all_indices()

        self.assertEqual(calls["n"], 1)
        self.assertEqual(first, second)

    def test_fetch_korea_market_close_data(self):
        with patch.object(market_indices, "fetch_korea_market_indices",
                          return_value={"kospi": {"name": "KOSPI", "value": 2650.0}}), \
             patch.object(market_indices, "fetch_usd_krw", return_value={"value": 1350.0}), \
             patch.object(market_indices, "fetch_fear_greed_index", return_value=None), \
             patch.object(market_indices, "fetch_vix", return_value=None), \
             patch.object(market_indices, "fetch_market_indices", return_value={}):
            data = market_indices.fetch_korea_market_close_data()

        self.assertIn("kospi", data["korea_indices"])
        self.assertEqual(data["usd_krw"]["value"], 1350.0)
        self.assertEqual(data["us_indices"], {})
        self.assertIn("date", data)
        self.assertIn("timestamp", data)


class IndexHighsTests(unittest.TestCase):
    def test_fetch_index_highs_parallel(self):
        def fake_request(url, *args, **kwargs):
            if "range=max" in url:
                return json.dumps({
                    "chart": {"result": [{
                        "timestamp": [1700000000, 1700086400],
                        "indicators": {"quote": [{"high": [4800.0, 4900.0]}]},
                    }]}
                })
            if "range=1y" in url:
                return json.dumps({
                    "chart": {"result": [{
                        "timestamp": [1700000000, 1700086400],
                        "indicators": {"quote": [{"high": [4950.0, 5000.0]}]},
                    }]}
                })
            return None

        with patch.object(market_indices, "_make_request", side_effect=fake_request):
            highs = market_indices.fetch_index_highs("^GSPC")

        self.assertEqual(highs["all_time_high"], 4900.0)
        self.assertEqual(highs["week52_high"], 5000.0)
        self.assertIn("all_time_high_date", highs)
        self.assertIn("week52_high_date", highs)

    def test_fetch_all_index_highs_includes_korea(self):
        """5개 지수의 최고가를 병렬로 조회하며 한국 지수를 포함해야 한다"""
        def fake_request(url, *args, **kwargs):
            return json.dumps({
                "chart": {"result": [{
                    "timestamp": [1700000000],
                    "indicators": {"quote": [{"high": [1234.0]}]},
                }]}
            })

        with patch.object(market_indices, "_make_request", side_effect=fake_request):
            result = market_indices.fetch_all_index_highs()

        self.assertEqual(set(result.keys()), {"sp500", "nasdaq", "dow", "kospi", "kosdaq"})
        self.assertEqual(result["kospi"]["name"], "KOSPI")
        self.assertEqual(result["kospi"]["all_time_high"], 1234.0)


if __name__ == "__main__":
    unittest.main()