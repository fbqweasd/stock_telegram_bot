import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database
from scheduler import AlertScheduler


class RecommendationAlertDatabaseTests(unittest.TestCase):
    """매수/매도 권장 알림 DB 함수 테스트"""

    def setUp(self):
        # 테스트용 임시 DB 파일 사용 (기존 DB 파일 보호)
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        database.DB_PATH = self.temp_db.name
        database.init_db()

    def tearDown(self):
        try:
            os.remove(self.temp_db.name)
        except OSError:
            pass

    def test_recommendation_alert_count_starts_at_zero(self):
        count = database.get_recommendation_alert_count(1, "AAPL", "2026-08-09")
        self.assertEqual(count, 0)

    def test_record_and_count_recommendation_alert(self):
        # 첫 번째 알림 기록
        self.assertTrue(database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY", 150.0))
        count = database.get_recommendation_alert_count(1, "AAPL", "2026-08-09")
        self.assertEqual(count, 1)

        # 같은 유형 중복 기록은 무시됨 (PK 제약)
        self.assertFalse(database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY", 150.0))
        count = database.get_recommendation_alert_count(1, "AAPL", "2026-08-09")
        self.assertEqual(count, 1)

        # 다른 유형(STRONG_SELL)은 별도로 기록됨
        self.assertTrue(database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_SELL", 160.0))
        count = database.get_recommendation_alert_count(1, "AAPL", "2026-08-09")
        self.assertEqual(count, 2)

    def test_has_sent_recommendation_alert(self):
        self.assertFalse(database.has_sent_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY"))
        database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY", 150.0)
        self.assertTrue(database.has_sent_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY"))
        self.assertFalse(database.has_sent_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_SELL"))

    def test_daily_limit_enforced(self):
        """유형별 하루 1회 제한 확인 (유형당 최대 1회, 두 유형이면 2회)"""
        database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY", 150.0)
        self.assertTrue(database.has_sent_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY"))

        # 다른 유형(STRONG_SELL)은 별도로 하루 1회 허용됨
        database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_SELL", 160.0)
        count = database.get_recommendation_alert_count(1, "AAPL", "2026-08-09")
        self.assertEqual(count, 2)

    def test_different_dates_are_independent(self):
        """날짜가 다르면 알림 횟수가 독립적으로 계산됨"""
        database.record_recommendation_alert(1, "AAPL", "2026-08-09", "STRONG_BUY", 150.0)
        count_today = database.get_recommendation_alert_count(1, "AAPL", "2026-08-09")
        count_tomorrow = database.get_recommendation_alert_count(1, "AAPL", "2026-08-10")
        self.assertEqual(count_today, 1)
        self.assertEqual(count_tomorrow, 0)


class RecommendationAlertSchedulerTests(unittest.TestCase):
    """매수/매도 권장 알림 스케줄러 로직 테스트"""

    def setUp(self):
        # 테스트용 임시 DB 파일 사용 (기존 DB 파일 보호)
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        database.DB_PATH = self.temp_db.name
        database.init_db()

        # Mock bot
        self.mock_bot = MagicMock()
        self.scheduler = AlertScheduler(self.mock_bot)

    def tearDown(self):
        try:
            os.remove(self.temp_db.name)
        except OSError:
            pass

    def _create_strong_buy_stock_data(self):
        """STRONG BUY 신호를 발생시키는 mock 데이터 생성"""
        # 급락 후 반등하는 패턴 (RSI 과매도, 볼린저 하단, 지지선 근접)
        closes = []
        for i in range(130):
            if i < 100:
                closes.append(200 - i * 0.3)  # 하락
            else:
                closes.append(170 + i * 0.1)  # 반등 시도
        highs = [c + 2 for c in closes]
        lows = [c - 2 for c in closes]
        volumes = [1000000] * 130

        return {
            "ticker": "TEST",
            "currency": "USD",
            "name": "Test Stock",
            "current_price": closes[-1],
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "previous_close": closes[-2],
        }

    def test_recommendation_alert_sent_for_strong_buy(self):
        """STRONG BUY 신호 시 권장 알림이 전송되는지 확인"""
        stock_data = self._create_strong_buy_stock_data()

        # 구독자 등록
        database.add_subscription(1, "TEST")

        # predictor를 mock하여 STRONG BUY 반환
        with patch("scheduler.predictor.predict_buy_sell_prices") as mock_predict:
            mock_predict.return_value = {
                "ticker": "TEST",
                "currency": "USD",
                "current_price": 180.0,
                "buy_target": 175.0,
                "sell_target": 190.0,
                "stop_loss": 170.0,
                "recommendation": "STRONG BUY",
                "confidence": 85,
                "score": 4.5,
                "signals": ["RSI 극단적 과매도 (강한 매수 신호)", "볼린저 하단 근접"],
                "market_regime": "RANGING",
                "indicators": {}
            }

            self.scheduler._check_recommendation_alerts("TEST", stock_data, [1])

        # 메시지가 전송되었는지 확인
        self.mock_bot.send_message.assert_called_once()
        call_args = self.mock_bot.send_message.call_args
        self.assertEqual(call_args[0][0], 1)  # chat_id
        self.assertIn("무조건 매수 권장", call_args[0][1])
        self.assertIn("권장 매수 가격", call_args[0][1])
        self.assertIn("175.00", call_args[0][1])

    def test_recommendation_alert_not_sent_for_hold(self):
        """HOLD 신호 시 권장 알림이 전송되지 않는지 확인"""
        stock_data = self._create_strong_buy_stock_data()
        database.add_subscription(1, "TEST")

        with patch("scheduler.predictor.predict_buy_sell_prices") as mock_predict:
            mock_predict.return_value = {
                "ticker": "TEST",
                "currency": "USD",
                "current_price": 180.0,
                "buy_target": 175.0,
                "sell_target": 190.0,
                "stop_loss": 170.0,
                "recommendation": "HOLD",
                "confidence": 50,
                "score": 0.0,
                "signals": [],
                "market_regime": "RANGING",
                "indicators": {}
            }

            self.scheduler._check_recommendation_alerts("TEST", stock_data, [1])

        self.mock_bot.send_message.assert_not_called()

    def test_daily_limit_prevents_excess_alerts(self):
        """다른 유형 알림이 기록돼 있어도 같은 유형은 하루 1회만 전송되는지 확인"""
        stock_data = self._create_strong_buy_stock_data()
        database.add_subscription(1, "TEST")

        import time
        kst_offset = 9 * 60 * 60
        today_str = time.strftime("%Y-%m-%d", time.gmtime(time.time() + kst_offset))

        # 오늘 이미 STRONG_BUY 알림을 보냈음 (다른 유형과 무관하게 차단됨)
        database.record_recommendation_alert(1, "TEST", today_str, "STRONG_BUY", 180.0)
        # 다른 유형(STRONG_SELL)도 보냈음 - 총 2회지만 유형당 1회 정책상 무관
        database.record_recommendation_alert(1, "TEST", today_str, "STRONG_SELL", 180.0)

        with patch("scheduler.predictor.predict_buy_sell_prices") as mock_predict:
            mock_predict.return_value = {
                "ticker": "TEST",
                "currency": "USD",
                "current_price": 180.0,
                "buy_target": 175.0,
                "sell_target": 190.0,
                "stop_loss": 170.0,
                "recommendation": "STRONG BUY",
                "confidence": 85,
                "score": 4.5,
                "signals": [],
                "market_regime": "RANGING",
                "indicators": {}
            }

            self.scheduler._check_recommendation_alerts("TEST", stock_data, [1])

        # 같은 유형(STRONG_BUY)을 오늘 이미 보냈으므로 추가 알림이 전송되지 않아야 함
        self.mock_bot.send_message.assert_not_called()

    def test_same_type_alert_not_sent_twice(self):
        """같은 유형(STRONG_BUY) 알림은 하루에 1번만 전송되는지 확인"""
        stock_data = self._create_strong_buy_stock_data()
        database.add_subscription(1, "TEST")

        import time
        kst_offset = 9 * 60 * 60
        today_str = time.strftime("%Y-%m-%d", time.gmtime(time.time() + kst_offset))

        # 이미 STRONG_BUY 알림을 보냈음
        database.record_recommendation_alert(1, "TEST", today_str, "STRONG_BUY", 180.0)

        with patch("scheduler.predictor.predict_buy_sell_prices") as mock_predict:
            mock_predict.return_value = {
                "ticker": "TEST",
                "currency": "USD",
                "current_price": 180.0,
                "buy_target": 175.0,
                "sell_target": 190.0,
                "stop_loss": 170.0,
                "recommendation": "STRONG BUY",
                "confidence": 85,
                "score": 4.5,
                "signals": [],
                "market_regime": "RANGING",
                "indicators": {}
            }

            self.scheduler._check_recommendation_alerts("TEST", stock_data, [1])

        self.mock_bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()