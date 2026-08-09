"""
백테스트 모듈(backtest.py) 테스트

테스트 항목:
1. fetch_long_history - 데이터 수집 (mock API)
2. run_backtest - 백테스트 실행 (mock 데이터)
3. print_report - 결과 출력
4. Look-ahead bias 방지 검증
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import (
    fetch_long_history,
    run_backtest,
    print_report,
    _make_request,
)


def generate_mock_data(n=300, start_price=100.0, trend=0.05, volatility=2.0):
    """
    테스트용 mock 주가 데이터 생성.
    - n: 데이터 포인트 수
    - start_price: 시작 가격
    - trend: 일별 추세 (양수 = 상승, 음수 = 하락)
    - volatility: 변동성 (%)
    """
    import random
    random.seed(42)

    closes = []
    highs = []
    lows = []
    opens = []
    volumes = []
    timestamps = []

    price = start_price
    base_ts = int(datetime(2020, 1, 1).timestamp())

    for i in range(n):
        # 일별 변동 (추세 + 랜덤 노이즈)
        daily_change = trend + random.uniform(-volatility, volatility)
        open_price = price
        close_price = max(1.0, price + daily_change)
        high_price = max(open_price, close_price) + random.uniform(0, volatility * 0.5)
        low_price = min(open_price, close_price) - random.uniform(0, volatility * 0.5)

        closes.append(round(close_price, 2))
        highs.append(round(high_price, 2))
        lows.append(round(low_price, 2))
        opens.append(round(open_price, 2))
        volumes.append(random.randint(100000, 1000000))
        timestamps.append(base_ts + i * 86400)  # 하루 간격

        price = close_price

    return {
        "ticker": "TEST",
        "currency": "USD",
        "timestamps": timestamps,
        "dates": [datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") for ts in timestamps],
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "opens": opens,
        "volumes": volumes,
    }


class TestFetchLongHistory(unittest.TestCase):
    """fetch_long_history 함수 테스트"""

    def test_successful_fetch(self):
        """정상적인 데이터 수집 테스트"""
        # 현재 시간 기준으로 mock 데이터 생성 (years 필터링 통과, 100개 이상 필요)
        now = int(datetime.now().timestamp())
        n = 120
        mock_data = {
            "chart": {
                "result": [{
                    "meta": {"currency": "USD"},
                    "timestamp": [now - (n - 1 - i) * 86400 for i in range(n)],
                    "indicators": {
                        "quote": [{
                            "close": [100.0 + i * 0.5 for i in range(n)],
                            "high": [101.0 + i * 0.5 for i in range(n)],
                            "low": [99.0 + i * 0.5 for i in range(n)],
                            "open": [99.5 + i * 0.5 for i in range(n)],
                            "volume": [1000000 + i * 1000 for i in range(n)],
                        }]
                    }
                }]
            }
        }

        with patch("backtest._make_request", return_value=mock_data):
            result = fetch_long_history("AAPL", years=5)

        self.assertIsNotNone(result)
        self.assertEqual(result["ticker"], "AAPL")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(len(result["closes"]), n)
        self.assertEqual(result["closes"][0], 100.0)
        # 날짜 형식 검증 (YYYY-MM-DD)
        self.assertRegex(result["dates"][0], r"^\d{4}-\d{2}-\d{2}$")
    def test_none_values_cleaned(self):
        """None 값이 포함된 데이터 정제 테스트"""
        now = int(datetime.now().timestamp())
        n = 120
        closes = [100.0 + i * 0.5 for i in range(n)]
        closes[1] = None  # 중간에 None 값 삽입
        mock_data = {
            "chart": {
                "result": [{
                    "meta": {"currency": "USD"},
                    "timestamp": [now - (n - 1 - i) * 86400 for i in range(n)],
                    "indicators": {
                        "quote": [{
                            "close": closes,
                            "high": [101.0 + i * 0.5 for i in range(n)],
                            "low": [99.0 + i * 0.5 for i in range(n)],
                            "open": [99.5 + i * 0.5 for i in range(n)],
                            "volume": [1000000 + i * 1000 for i in range(n)],
                        }]
                    }
                }]
            }
        }

        with patch("backtest._make_request", return_value=mock_data):
            result = fetch_long_history("AAPL")

        self.assertIsNotNone(result)
        # None 값이 있는 행은 제거되어야 함
        self.assertEqual(len(result["closes"]), n - 1)
        self.assertEqual(result["closes"][0], 100.0)
        self.assertEqual(result["closes"][1], 101.0)  # None이 제거된 후 다음 값

    def test_failed_fetch(self):
        """API 실패 시 None 반환 테스트"""
        with patch("backtest._make_request", return_value=None):
            result = fetch_long_history("INVALID")
        self.assertIsNone(result)

    def test_insufficient_data(self):
        """데이터가 부족하면 None 반환 테스트"""
        mock_data = {
            "chart": {
                "result": [{
                    "meta": {"currency": "USD"},
                    "timestamp": [1600000000],
                    "indicators": {
                        "quote": [{
                            "close": [100.0],
                            "high": [101.0],
                            "low": [99.0],
                            "open": [99.5],
                            "volume": [1000000],
                        }]
                    }
                }]
            }
        }

        with patch("backtest._make_request", return_value=mock_data):
            result = fetch_long_history("AAPL")
        self.assertIsNone(result)

class TestRunBacktest(unittest.TestCase):
    """run_backtest 함수 테스트"""

    def setUp(self):
        self.data = generate_mock_data(n=300, start_price=100.0, trend=0.1, volatility=1.0)

    def test_basic_run(self):
        """기본 백테스트 실행 테스트"""
        result = run_backtest(self.data, horizon=5, step=1)

        self.assertNotIn("error", result)
        self.assertEqual(result["ticker"], "TEST")
        self.assertEqual(result["currency"], "USD")

        # 예측 정확도
        self.assertIn("prediction_accuracy", result)
        self.assertGreater(result["prediction_accuracy"]["total_predictions"], 0)
        self.assertIn("accuracy_pct", result["prediction_accuracy"])

        # 매매 성과
        self.assertIn("trading_performance", result)
        self.assertIn("total_return_pct", result["trading_performance"])
        self.assertIn("win_rate_pct", result["trading_performance"])
        self.assertIn("num_trades", result["trading_performance"])

        # 기간 정보
        self.assertIn("period", result)
        self.assertIn("start_date", result["period"])
        self.assertIn("end_date", result["period"])

    def test_insufficient_data(self):
        """데이터 부족 시 오류 반환 테스트"""
        small_data = generate_mock_data(n=50, start_price=100.0)
        result = run_backtest(small_data, horizon=5)
        self.assertIn("error", result)

    def test_horizon_parameter(self):
        """horizon 파라미터가 결과에 반영되는지 테스트"""
        result = run_backtest(self.data, horizon=10, step=1)
        self.assertEqual(result["settings"]["horizon_days"], 10)

    def test_step_parameter(self):
        """step 파라미터가 예측 수에 영향을 주는지 테스트"""
        result_step1 = run_backtest(self.data, horizon=5, step=1)
        result_step5 = run_backtest(self.data, horizon=5, step=5)

        # step이 크면 예측 횟수가 적어야 함
        self.assertGreater(
            result_step1["prediction_accuracy"]["total_predictions"],
            result_step5["prediction_accuracy"]["total_predictions"]
        )

    def test_initial_capital(self):
        """초기 자본 설정 테스트"""
        result = run_backtest(self.data, horizon=5, step=1, initial_capital=50000)
        self.assertEqual(result["trading_performance"]["initial_capital"], 50000)

    def test_lookahead_bias_prevention(self):
        """
        Look-ahead bias 방지 검증:
        각 예측 시점에서 미래 데이터가 사용되지 않아야 함.
        predict_buy_sell_prices가 호출될 때 전달되는 데이터 길이를 검증.
        """
        from predictor import predict_buy_sell_prices

        original_predict = predict_buy_sell_prices
        call_data_lengths = []

        def mock_predict(stock_data):
            call_data_lengths.append(len(stock_data["closes"]))
            return original_predict(stock_data)

        with patch("backtest.predict_buy_sell_prices", side_effect=mock_predict):
            run_backtest(self.data, horizon=5, step=10)

        # 각 호출의 데이터 길이가 증가하는지 확인 (과거 데이터만 사용)
        self.assertGreater(len(call_data_lengths), 0)
        for i in range(1, len(call_data_lengths)):
            self.assertGreater(call_data_lengths[i], call_data_lengths[i - 1])

    def test_prediction_fields(self):
        """예측 결과에 필요한 필드가 모두 포함되는지 테스트"""
        result = run_backtest(self.data, horizon=5, step=10)

        recent_preds = result.get("recent_predictions", [])
        if recent_preds:
            p = recent_preds[0]
            required_fields = [
                "date", "future_date", "price", "future_price",
                "price_change_pct", "recommendation", "score",
                "confidence", "direction", "correct"
            ]
            for field in required_fields:
                self.assertIn(field, p, f"필드 '{field}' 누락")

    def test_trade_fields(self):
        """거래 결과에 필요한 필드가 모두 포함되는지 테스트"""
        result = run_backtest(self.data, horizon=5, step=10)

        recent_trades = result.get("recent_trades", [])
        if recent_trades:
            t = recent_trades[0]
            self.assertIn("type", t)
            self.assertIn("date", t)
            self.assertIn("price", t)


class TestPrintReport(unittest.TestCase):
    """print_report 함수 테스트"""

    def test_print_valid_result(self):
        """정상 결과 출력 테스트"""
        data = generate_mock_data(n=200, start_price=100.0, trend=0.1, volatility=1.0)
        result = run_backtest(data, horizon=5, step=5)

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_report(result)

        output = buf.getvalue()
        self.assertIn("백테스트 결과", output)
        self.assertIn("예측 정확도", output)
        self.assertIn("매매 성과", output)

    def test_print_error_result(self):
        """오류 결과 출력 테스트"""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_report({"error": "테스트 오류"})

        output = buf.getvalue()
        self.assertIn("오류", output)


class TestMakeRequest(unittest.TestCase):
    """_make_request 함수 테스트"""

    def test_successful_request(self):
        """정상 HTTP 요청 테스트"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"key": "value"}'

        mock_urlopen = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", mock_urlopen):
            result = _make_request("https://example.com/api")

        self.assertEqual(result, {"key": "value"})

    def test_failed_request(self):
        """HTTP 요청 실패 시 예외 발생 테스트"""
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            with self.assertRaises(Exception):
                _make_request("https://example.com/api", retries=1, delay=0)


if __name__ == "__main__":
    unittest.main()