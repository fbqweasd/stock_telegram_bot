import time
import sys
import os
import database
from config import TELEGRAM_BOT_TOKEN, DB_PATH, CHECK_INTERVAL
from telegram_bot import TelegramBot
from scheduler import AlertScheduler

def check_environment():
    """
    Validates essential configuration parameters before launching.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("\n" + "="*60)
        print("❌ ERROR: TELEGRAM_BOT_TOKEN IS NOT CONFIGURED!")
        print("="*60)
        print("텔레그램 봇 토큰이 설정되지 않았습니다.")
        print("동일한 폴더에 '.env' 파일을 생성하고 아래와 같이 토큰을 입력해 주세요:")
        print("\nTELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print(f"CHECK_INTERVAL={CHECK_INTERVAL}")
        print("="*60 + "\n")
        return False
    return True

def main():
    print("🚀 Initializing Telegram Stock Alert Bot...")
    
    # Check if necessary variables exist
    if not check_environment():
        sys.exit(1)
        
    # 1. Initialize SQLite Database Tables
    print(f"📂 Initializing database at '{DB_PATH}'...")
    database.init_db()
    print("✅ Database initialized successfully.")
    
    # 2. Instantiate and start Telegram Bot polling
    print("🤖 Starting Telegram Polling Service...")
    bot = TelegramBot()
    # 봇 명령어를 등록해 사용자가 "/" 입력 시 자동완성 메뉴로 확인할 수 있게 합니다.
    bot.set_my_commands()
    bot.start_polling()
    
    # 3. Instantiate and start Background Indicator Alert Scheduler
    print("⏰ Starting Technical Indicator Background Scan Service...")
    scheduler = AlertScheduler(bot)
    scheduler.start()
    
    print("\n" + "="*50)
    print("🎉 STOCK ALERT BOT IS NOW RUNNING SUCCESSFULLY!")
    print(f"- SQLite DB: {DB_PATH}")
    print(f"- Scan Interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)")
    print("Press CTRL+C to terminate services gracefully.")
    print("="*50 + "\n")
    
    # 4. Graceful Shutdown & Keep Main Thread Alive
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print("\n⚠️ Termination signal received. Shutting down gracefully...")
        
        # Stop background threads
        scheduler.stop()
        bot.stop_polling()
        
        # Short wait to let threads wrap up
        time.sleep(1.5)
        print("👋 Services successfully terminated. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
