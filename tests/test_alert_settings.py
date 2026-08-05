import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database


class AlertSettingsTests(unittest.TestCase):
    def setUp(self):
        db_path = database.DB_PATH
        if os.path.exists(db_path):
            os.remove(db_path)
        database.init_db()

    def test_alert_settings_toggle_and_query(self):
        self.assertTrue(database.set_chat_alerts_enabled(1, False))
        self.assertFalse(database.get_chat_alerts_enabled(1))

        self.assertTrue(database.set_chat_alerts_enabled(1, True))
        self.assertTrue(database.get_chat_alerts_enabled(1))

        self.assertTrue(database.get_chat_alerts_enabled(999))


if __name__ == "__main__":
    unittest.main()
