import sqlite3
import os
from config import DB_PATH

def get_connection():
    """
    Creates and returns a connection to the SQLite database.
    Since sqlite connections are not thread-safe, we open and close a connection per request/operation.
    """
    return sqlite3.connect(DB_PATH)

def init_db():
    """
    Initializes the database tables if they do not exist.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Table to store user subscriptions for stock tickers
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id INTEGER,
                ticker TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker)
            )
        """)
        
        # Table to track the last sent signals to avoid spamming user
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_signals (
                chat_id INTEGER,
                ticker TEXT,
                signal_type TEXT,
                last_price REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker, signal_type)
            )
        """)
        
        # Table to track last known price per ticker (for price change alerts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_prices (
                chat_id INTEGER,
                ticker TEXT,
                last_price REAL,
                last_alert_price REAL,
                alert_threshold_pct REAL DEFAULT 5.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker)
            )
        """)
        
        # Table to track daily price alerts (전일 종가 기준 5%/10%/20% 변동 알림)
        # 동일한 (임계값, 방향) 조합은 하루에 1번만 알림을 보내기 위해 사용
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_alerts (
                chat_id INTEGER,
                ticker TEXT,
                alert_date TEXT,
                threshold_pct REAL,
                direction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker, alert_date, threshold_pct, direction)
            )
        """)
        
        # 기존 스키마 마이그레이션: (chat_id, ticker, alert_date) PK를 가진 구버전 테이블이 있으면
        # 새 PK 구조로 재생성합니다.
        cursor.execute("PRAGMA table_info(daily_price_alerts)")
        columns = cursor.fetchall()
        pk_columns = [col[1] for col in columns if col[5] > 0]
        if pk_columns and pk_columns != ["chat_id", "ticker", "alert_date", "threshold_pct", "direction"]:
            # 구버전 테이블 백업 후 재생성
            cursor.execute("ALTER TABLE daily_price_alerts RENAME TO daily_price_alerts_old")
            cursor.execute("""
                CREATE TABLE daily_price_alerts (
                    chat_id INTEGER,
                    ticker TEXT,
                    alert_date TEXT,
                    threshold_pct REAL,
                    direction TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, ticker, alert_date, threshold_pct, direction)
                )
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO daily_price_alerts (chat_id, ticker, alert_date, threshold_pct, direction, created_at)
                SELECT chat_id, ticker, alert_date, threshold_pct, direction, created_at FROM daily_price_alerts_old
            """)
            cursor.execute("DROP TABLE daily_price_alerts_old")
        
        # Table to store chat notification topic settings (단체방 알림 토픽 설정)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_topics (
                chat_id INTEGER PRIMARY KEY,
                message_thread_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table to store whether automatic alerts are enabled for a chat
        # alert_level: 알람 수신 수준 ('OFF' / 'MARKET' / 'IMPORTANT' / 'ALL')
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_alert_settings (
                chat_id INTEGER PRIMARY KEY,
                alerts_enabled INTEGER NOT NULL DEFAULT 1,
                alert_level TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 기존 스키마 마이그레이션: alert_level 컬럼이 없으면 추가하고
        # 기존 alerts_enabled 값을 기반으로 레벨을 채워준다.
        cursor.execute("PRAGMA table_info(chat_alert_settings)")
        alert_setting_columns = [col[1] for col in cursor.fetchall()]
        if "alert_level" not in alert_setting_columns:
            cursor.execute("ALTER TABLE chat_alert_settings ADD COLUMN alert_level TEXT")
            cursor.execute("""
                UPDATE chat_alert_settings
                SET alert_level = CASE WHEN alerts_enabled = 0 THEN 'OFF' ELSE 'ALL' END
                WHERE alert_level IS NULL
            """)

        # Table to track daily technical signal alerts (기술적 신호 하루 1회 제한)
        # 동일한 (티커, 신호 유형) 조합은 같은 날짜에 1번만 알림을 보내기 위해 사용
        # (20일선 돌파 등 상태가 반복적으로 바뀌어도 하루 1번만 알림)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_signal_alerts (
                chat_id INTEGER,
                ticker TEXT,
                signal_type TEXT,
                alert_date TEXT,
                price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker, signal_type, alert_date)
            )
        """)


        # Table to track high breakout alerts (역대/52주 최고가 돌파 알림)
        # 동일한 (티커, 유형) 조합은 하루에 1번만 알림을 보내기 위해 사용
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS high_breakout_alerts (
                chat_id INTEGER,
                ticker TEXT,
                alert_type TEXT,
                alert_date TEXT,
                price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker, alert_type, alert_date)
            )
        """)

        # Table to track weekly report sends (주간 리포트 전송 기록)
        # 동일한 주(week_start)에는 1번만 전송하도록 관리
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_report_sends (
                chat_id INTEGER,
                week_start TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, week_start)
            )
        """)

        # Table to track 매수/매도 권장 알림 (STRONG BUY/STRONG SELL)
        # 한 종목당 하루 최대 알림 횟수를 제한하기 위해 사용
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendation_alerts (
                chat_id INTEGER,
                ticker TEXT,
                alert_date TEXT,
                alert_type TEXT,
                price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, ticker, alert_date, alert_type)
            )
        """)
        conn.commit()

def add_subscription(chat_id, ticker):
    """
    Subscribes a user to a specific ticker.
    Ticker is always saved in UPPERCASE.
    Returns True if successfully added, False if already subscribed.
    """
    ticker = ticker.upper().strip()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO subscriptions (chat_id, ticker) VALUES (?, ?)",
                (chat_id, ticker)
            )
            # Initialize last_price row for price tracking
            cursor.execute("""
                INSERT OR IGNORE INTO last_prices (chat_id, ticker, last_price, last_alert_price, alert_threshold_pct)
                VALUES (?, ?, NULL, NULL, 5.0)
            """, (chat_id, ticker))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        # User is already subscribed to this ticker
        return False

def remove_subscription(chat_id, ticker):
    """
    Unsubscribes a user from a specific ticker.
    Returns True if deleted, False if subscription didn't exist.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND ticker = ?",
            (chat_id, ticker)
        )
        # Clean up related price tracking
        cursor.execute(
            "DELETE FROM last_prices WHERE chat_id = ? AND ticker = ?",
            (chat_id, ticker)
        )
        conn.commit()
        return cursor.rowcount > 0

def get_user_subscriptions(chat_id):
    """
    Retrieves all tickers a specific user is subscribed to.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ticker FROM subscriptions WHERE chat_id = ? ORDER BY ticker ASC",
            (chat_id,)
        )
        rows = cursor.fetchall()
        return [row[0] for row in rows]

def get_all_subscriptions():
    """
    Retrieves all subscription mappings: [(chat_id, ticker), ...]
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, ticker FROM subscriptions")
        return cursor.fetchall()

def get_unique_tickers():
    """
    Retrieves a list of all unique tickers subscribed by at least one user.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT ticker FROM subscriptions")
        rows = cursor.fetchall()
        return [row[0] for row in rows]

def get_subscribers_for_ticker(ticker):
    """
    Retrieves all chat IDs subscribed to a specific ticker.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM subscriptions WHERE ticker = ?", (ticker,))
        rows = cursor.fetchall()
        return [row[0] for row in rows]

# Signal tracking functions to prevent redundant alerts
def get_last_signal(chat_id, ticker, signal_type):
    """
    Checks if a specific signal was already triggered and returns its price and update time.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT last_price, updated_at FROM last_signals WHERE chat_id = ? AND ticker = ? AND signal_type = ?",
            (chat_id, ticker, signal_type)
        )
        row = cursor.fetchone()
        if row:
            return {"price": row[0], "updated_at": row[1]}
        return None

def set_last_signal(chat_id, ticker, signal_type, price):
    """
    Registers or updates a triggered signal.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO last_signals (chat_id, ticker, signal_type, last_price, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, ticker, signal_type, price))
        conn.commit()

def clear_last_signal(chat_id, ticker, signal_type):
    """
    Clears a registered signal (i.e., when price returns to normal).
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM last_signals WHERE chat_id = ? AND ticker = ? AND signal_type = ?",
            (chat_id, ticker, signal_type)
        )
        conn.commit()
        return cursor.rowcount > 0

def clear_all_signals_for_ticker(chat_id, ticker):
    """
    Clears all tracked signals for a user's ticker. Useful when unsubscribing.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM last_signals WHERE chat_id = ? AND ticker = ?",
            (chat_id, ticker)
        )
        conn.commit()

# Price tracking functions for % change alerts
def get_last_price_info(chat_id, ticker):
    """
    Returns last known price and alert threshold for a user's ticker subscription.
    Returns: {last_price, last_alert_price, alert_threshold_pct} or None
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT last_price, last_alert_price, alert_threshold_pct FROM last_prices WHERE chat_id = ? AND ticker = ?",
            (chat_id, ticker)
        )
        row = cursor.fetchone()
        if row:
            return {
                "last_price": row[0],
                "last_alert_price": row[1],
                "alert_threshold_pct": row[2]
            }
        return None

def set_last_price(chat_id, ticker, price):
    """
    Updates the last known price for a ticker.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO last_prices (chat_id, ticker, last_price, last_alert_price, alert_threshold_pct, updated_at)
            VALUES (?, ?, ?, COALESCE((SELECT last_alert_price FROM last_prices WHERE chat_id = ? AND ticker = ?), NULL),
                    COALESCE((SELECT alert_threshold_pct FROM last_prices WHERE chat_id = ? AND ticker = ?), 5.0),
                    CURRENT_TIMESTAMP)
        """, (chat_id, ticker, price, chat_id, ticker, chat_id, ticker))
        conn.commit()

def set_last_alert_price(chat_id, ticker, price):
    """
    Updates the price at which the last price change alert was sent.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE last_prices SET last_alert_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND ticker = ?
        """, (price, chat_id, ticker))
        conn.commit()

def set_alert_threshold(chat_id, ticker, threshold_pct):
    """
    Sets a custom price change alert threshold (%) for a user's ticker.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO last_prices (chat_id, ticker, last_price, last_alert_price, alert_threshold_pct, updated_at)
            VALUES (?, ?,
                    COALESCE((SELECT last_price FROM last_prices WHERE chat_id = ? AND ticker = ?), NULL),
                    COALESCE((SELECT last_alert_price FROM last_prices WHERE chat_id = ? AND ticker = ?), NULL),
                    ?,
                    CURRENT_TIMESTAMP)
        """, (chat_id, ticker, chat_id, ticker, chat_id, ticker, threshold_pct))
        conn.commit()
        return cursor.rowcount > 0

def get_alert_threshold(chat_id, ticker):
    """
    Gets the custom price change alert threshold (%) for a user's ticker.
    Returns default 5.0 if not set.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT alert_threshold_pct FROM last_prices WHERE chat_id = ? AND ticker = ?",
            (chat_id, ticker)
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
        return 5.0

# ================================================================
# Daily price alert tracking (전일 종가 기준 5%/10%/20% 변동 알림)
# 하루에 1번만 알림을 보내도록 관리
# ================================================================

def get_daily_alerts_for_date(chat_id, ticker, alert_date):
    """
    Returns all sent daily alerts for a specific user/ticker/date.
    Returns a list of dicts: [{threshold_pct, direction}, ...]
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT threshold_pct, direction FROM daily_price_alerts WHERE chat_id = ? AND ticker = ? AND alert_date = ?",
            (chat_id, ticker, alert_date)
        )
        rows = cursor.fetchall()
        return [{"threshold_pct": row[0], "direction": row[1]} for row in rows]

def get_daily_alerts_for_ticker_date(ticker, alert_date):
    """
    Returns all chat_ids that have already received a daily alert for a given ticker/date.
    Returns a dict: {chat_id: [threshold_pct, ...]}
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chat_id, threshold_pct, direction FROM daily_price_alerts WHERE ticker = ? AND alert_date = ?",
            (ticker, alert_date)
        )
        rows = cursor.fetchall()
        result = {}
        for row in rows:
            chat_id = row[0]
            if chat_id not in result:
                result[chat_id] = []
            result[chat_id].append({"threshold_pct": row[1], "direction": row[2]})
        return result

def record_daily_alert(chat_id, ticker, alert_date, threshold_pct, direction):
    """
    Records that a daily price alert was sent for a specific user/ticker/date.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO daily_price_alerts (chat_id, ticker, alert_date, threshold_pct, direction)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, ticker, alert_date, threshold_pct, direction))
        conn.commit()
        return cursor.rowcount > 0

# ================================================================
# Weekly report tracking (주간 리포트 전송 기록)
# 동일한 주(week_start)에는 1번만 전송하도록 관리
# ================================================================

def has_sent_weekly_report(chat_id, week_start):
    """
    특정 사용자가 해당 주(week_start)에 주간 리포트를 이미 받았는지 확인합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM weekly_report_sends WHERE chat_id = ? AND week_start = ?",
            (chat_id, week_start)
        )
        return cursor.fetchone() is not None


def record_weekly_report_send(chat_id, week_start):
    """
    주간 리포트를 보냈음을 기록합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO weekly_report_sends (chat_id, week_start, sent_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, week_start))
        conn.commit()
        return cursor.rowcount > 0


# ================================================================
# Chat topic settings (단체방 알림 토픽 설정)
# ================================================================
# Chat topic settings (단체방 알림 토픽 설정)
# ================================================================

def set_chat_topic(chat_id, message_thread_id):
    """
    Sets the notification topic (message_thread_id) for a chat.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO chat_topics (chat_id, message_thread_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, message_thread_id))
        conn.commit()

def clear_chat_topic(chat_id):
    """
    Clears the notification topic setting for a chat (reverts to default/General).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_topics WHERE chat_id = ?", (chat_id,))
        conn.commit()

def get_chat_topic(chat_id):
    """
    Gets the notification topic (message_thread_id) for a chat.
    Returns the message_thread_id or None if not set.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message_thread_id FROM chat_topics WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        return None


# ================================================================
# 알람 수신 수준 (Alert Level) 설정
#   OFF      : 모든 자동 알람을 받지 않음
#   MARKET   : 장 마감 요약/주간 리포트 등 종목과 무관한 시장 메시지만 수신
#   IMPORTANT: 시장 메시지 + 개별 종목의 중요 알림(STRONG BUY/SELL, 급등락,
#              최고가 돌파)만 수신
#   ALL      : 모든 자동 알람을 수신 (기본값)
# ================================================================

ALERT_LEVELS = ("OFF", "MARKET", "IMPORTANT", "ALL")

ALERT_LEVEL_LABELS = {
    "OFF": "🔕 모든 알람 받지 않음",
    "MARKET": "🌍 시장 알림만 (장마감 요약 등)",
    "IMPORTANT": "⭐ 중요 알림 + 시장 알림",
    "ALL": "🔔 모든 알람 받기",
}


def set_chat_alert_level(chat_id, level):
    """
    Sets the alert receiving level for a chat.
    level must be one of ALERT_LEVELS ('OFF', 'MARKET', 'IMPORTANT', 'ALL').
    Returns True when the setting is stored successfully.
    """
    if level not in ALERT_LEVELS:
        raise ValueError(f"Invalid alert level: {level}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO chat_alert_settings
                (chat_id, alerts_enabled, alert_level, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, 0 if level == "OFF" else 1, level))
        conn.commit()
        return True


def get_chat_alert_level(chat_id):
    """
    Returns the alert receiving level for a chat.
    Defaults to 'ALL' if no setting exists (기존 동작과 호환).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT alert_level, alerts_enabled FROM chat_alert_settings WHERE chat_id = ?
        """, (chat_id,))
        row = cursor.fetchone()
        if row is None:
            return "ALL"
        alert_level, alerts_enabled = row[0], row[1]
        if alert_level in ALERT_LEVELS:
            return alert_level
        # 레거시 행(alert_level 이 비어있는 경우): alerts_enabled 값으로 판단
        return "ALL" if alerts_enabled else "OFF"


def should_send_alert(chat_id, is_market_wide=False, is_important=False):
    """
    Determines whether a chat should receive an alert of the given kind
    based on its configured alert level.
    - is_market_wide: 장마감 요약, 주간 리포트, 극단 조건, 지수 최고치 등
                      특정 종목과 무관한 시장 전체 메시지인지 여부
    - is_important:   STRONG BUY/SELL 권장, 급등락 변동, 역대/52주 최고가
                      돌파 같은 개별 종목의 중요 알림인지 여부
    """
    level = get_chat_alert_level(chat_id)
    if level == "OFF":
        return False
    if level == "MARKET":
        return is_market_wide
    if level == "IMPORTANT":
        return is_market_wide or is_important
    return True  # 'ALL'


def set_chat_alerts_enabled(chat_id, enabled):
    """
    Enables or disables automatic alerts for a chat. (하위 호환용)
    enabled=False → 'OFF', enabled=True → 기존에 OFF 였다면 'ALL'로 복구.
    Returns True when the setting is stored successfully.
    """
    current = get_chat_alert_level(chat_id)
    if enabled and current == "OFF":
        return set_chat_alert_level(chat_id, "ALL")
    if not enabled:
        return set_chat_alert_level(chat_id, "OFF")
    # 이미 켜져 있으면 현재 레벨 유지
    return True


def get_chat_alerts_enabled(chat_id):
    """
    Returns whether automatic alerts are enabled for a chat.
    Defaults to True if no setting exists.
    """
    return get_chat_alert_level(chat_id) != "OFF"


# ================================================================
# 기술적 신호 일일 알림 추적 (하루 1회 제한)
# 20일선 돌파 등 상태가 하루에 여러 번 바뀌어도 유형당 1번만 알림
# ================================================================

def has_sent_signal_alert(chat_id, ticker, signal_type, alert_date):
    """
    특정 사용자가 특정 종목/신호 유형에 대해 해당 날짜에 이미 알림을 받았는지 확인합니다.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM daily_signal_alerts
            WHERE chat_id = ? AND ticker = ? AND signal_type = ? AND alert_date = ?
        """, (chat_id, ticker, signal_type, alert_date))
        return cursor.fetchone() is not None


def record_signal_alert(chat_id, ticker, signal_type, alert_date, price=None):
    """
    해당 날짜에 신호 유형의 알림을 보냈음을 기록합니다.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO daily_signal_alerts
                (chat_id, ticker, signal_type, alert_date, price)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, ticker, signal_type, alert_date, price))
        conn.commit()
        return cursor.rowcount > 0


# ================================================================
# 매수/매도 권장 알림 (STRONG BUY/STRONG SELL) 추적
# 한 종목당 유형(STRONG_BUY/STRONG_SELL)별 하루 최대 1회
# ================================================================

def get_recommendation_alert_count(chat_id, ticker, alert_date):
    """
    특정 사용자가 특정 종목에 대해 해당 날짜에 받은 매수/매도 권장 알림 횟수를 반환합니다.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM recommendation_alerts WHERE chat_id = ? AND ticker = ? AND alert_date = ?",
            (chat_id, ticker, alert_date)
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def has_sent_recommendation_alert(chat_id, ticker, alert_date, alert_type):
    """
    특정 사용자가 특정 종목에 대해 해당 날짜에 특정 유형(STRONG_BUY/STRONG_SELL)의
    권장 알림을 이미 받았는지 확인합니다.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM recommendation_alerts WHERE chat_id = ? AND ticker = ? AND alert_date = ? AND alert_type = ?",
            (chat_id, ticker, alert_date, alert_type)
        )
        return cursor.fetchone() is not None


def record_recommendation_alert(chat_id, ticker, alert_date, alert_type, price):
    """
    매수/매도 권장 알림을 보냈음을 기록합니다.
    """
    ticker = ticker.upper().strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO recommendation_alerts (chat_id, ticker, alert_date, alert_type, price, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, ticker, alert_date, alert_type, price))
        conn.commit()
        return cursor.rowcount > 0
