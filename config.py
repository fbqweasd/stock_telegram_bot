import os

def load_dotenv(filepath=".env"):
    """
    Custom .env file parser to load environment variables without external packages.
    """
    if not os.path.exists(filepath):
        return
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            
            # Split by first '=' only
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                
                # Remove quotes if wrapped
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                
                os.environ[key] = val

# Load variables from .env if present
load_dotenv()

# System Configs
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# Check interval in seconds (default: 3600 seconds = 1 hour)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 3600))
# DB path inside data directory
DB_PATH = os.environ.get("DB_PATH", "data/stock_bot.db")
# 매수/매도 권장 알림: 한 종목당 하루 최대 알림 횟수 (기본 3회)
MAX_DAILY_RECOMMENDATION_ALERTS = int(os.environ.get("MAX_DAILY_RECOMMENDATION_ALERTS", 3))

# Ensure the data directory exists
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)
