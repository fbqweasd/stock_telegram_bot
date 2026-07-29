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