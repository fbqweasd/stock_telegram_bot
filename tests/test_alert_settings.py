import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database


class AlertSettingsTests(unittest.TestCase):
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

    def test_alert_settings_toggle_and_query(self):
        self.assertTrue(database.set_chat_alerts_enabled(1, False))
        self.assertFalse(database.get_chat_alerts_enabled(1))

        self.assertTrue(database.set_chat_alerts_enabled(1, True))
        self.assertTrue(database.get_chat_alerts_enabled(1))

        self.assertTrue(database.get_chat_alerts_enabled(999))

    def test_default_alert_level_is_all(self):
        """설정이 없는 채팅은 기본값 'ALL'"""
        self.assertEqual(database.get_chat_alert_level(12345), "ALL")

    def test_set_and_get_alert_level(self):
        for level in ("OFF", "MARKET", "IMPORTANT", "ALL"):
            self.assertTrue(database.set_chat_alert_level(1, level))
            self.assertEqual(database.get_chat_alert_level(1), level)

    def test_invalid_alert_level_raises(self):
        with self.assertRaises(ValueError):
            database.set_chat_alert_level(1, "INVALID")

    def test_should_send_alert_by_level(self):
        chat_id = 42

        # ALL: 모든 종류의 알림 수신
        database.set_chat_alert_level(chat_id, "ALL")
        self.assertTrue(database.should_send_alert(chat_id))
        self.assertTrue(database.should_send_alert(chat_id, is_market_wide=True))
        self.assertTrue(database.should_send_alert(chat_id, is_important=True))

        # IMPORTANT: 시장 알림 + 중요 알림만 (일반 기술적 신호는 차단)
        database.set_chat_alert_level(chat_id, "IMPORTANT")
        self.assertFalse(database.should_send_alert(chat_id))
        self.assertTrue(database.should_send_alert(chat_id, is_market_wide=True))
        self.assertTrue(database.should_send_alert(chat_id, is_important=True))

        # MARKET: 시장 알림만
        database.set_chat_alert_level(chat_id, "MARKET")
        self.assertFalse(database.should_send_alert(chat_id))
        self.assertTrue(database.should_send_alert(chat_id, is_market_wide=True))
        self.assertFalse(database.should_send_alert(chat_id, is_important=True))

        # OFF: 아무것도 수신하지 않음
        database.set_chat_alert_level(chat_id, "OFF")
        self.assertFalse(database.should_send_alert(chat_id))
        self.assertFalse(database.should_send_alert(chat_id, is_market_wide=True))
        self.assertFalse(database.should_send_alert(chat_id, is_important=True))

    def test_enabled_toggle_compat_with_levels(self):
        """레거시 on/off 함수와 레벨 간 하위 호환 확인"""
        # off → OFF 레벨
        database.set_chat_alerts_enabled(7, False)
        self.assertEqual(database.get_chat_alert_level(7), "OFF")
        self.assertFalse(database.get_chat_alerts_enabled(7))

        # on → ALL 레벨 복구
        database.set_chat_alerts_enabled(7, True)
        self.assertEqual(database.get_chat_alert_level(7), "ALL")

        # IMPORTANT 레벨에서 on 호출 시 레벨 유지
        database.set_chat_alert_level(7, "IMPORTANT")
        self.assertTrue(database.set_chat_alerts_enabled(7, True))
        self.assertEqual(database.get_chat_alert_level(7), "IMPORTANT")
        self.assertTrue(database.get_chat_alerts_enabled(7))


class DailySignalAlertTests(unittest.TestCase):
    """기술적 신호 하루 1회 제한 DB 함수 테스트"""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        database.DB_PATH = self.temp_db.name
        database.init_db()

    def tearDown(self):
        try:
            os.remove(self.temp_db.name)
        except OSError:
            pass

    def test_signal_alert_not_sent_initially(self):
        self.assertFalse(database.has_sent_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22"))

    def test_record_signal_alert_once_per_day(self):
        self.assertTrue(database.record_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22", 150.0))
        self.assertTrue(database.has_sent_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22"))

        # 같은 날짜 재기록은 무시됨
        self.assertFalse(database.record_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22", 151.0))

    def test_different_signal_types_are_independent(self):
        database.record_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22", 150.0)
        # 다른 유형은 오늘 처음이므로 전송 가능
        self.assertFalse(database.has_sent_signal_alert(1, "AAPL", "BB_LOWER", "2026-08-22"))

    def test_different_tickers_are_independent(self):
        database.record_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22", 150.0)
        self.assertFalse(database.has_sent_signal_alert(1, "TSLA", "SMA_20_OVER", "2026-08-22"))

    def test_next_day_allows_again(self):
        database.record_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-22", 150.0)
        # 날짜가 바뀌면 다시 전송 가능
        self.assertFalse(database.has_sent_signal_alert(1, "AAPL", "SMA_20_OVER", "2026-08-23"))


if __name__ == "__main__":
    unittest.main()
