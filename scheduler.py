import time
import threading
from config import CHECK_INTERVAL
import database
import stock_api
import indicators

class AlertScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.is_running = False
        self.scheduler_thread = None

    def start(self):
        """
        Starts the background alert scheduler thread.
        """
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.scheduler_thread.start()
        print("Alert Scheduler Thread Started.")

    def stop(self):
        """
        Stops the background alert scheduler.
        """
        self.is_running = False
        print("Stopping Alert Scheduler...")

    def _run_loop(self):
        """
        Main loop for checking stock indicators periodically.
        """
        # Give the bot some time to start up before checking
        time.sleep(10)
        
        while self.is_running:
            try:
                print("⏳ Periodic stock check sequence initiated...")
                self._check_all_subscribed_stocks()
                print("✅ Periodic stock check complete.")
            except Exception as e:
                print(f"Error in Alert Scheduler Loop: {e}")
                
            # Sleep in smaller increments to allow rapid, graceful shutdown
            for _ in range(CHECK_INTERVAL):
                if not self.is_running:
                    break
                time.sleep(1)

    def _check_all_subscribed_stocks(self):
        """
        Gathers unique tickers, processes indicators, and sends alerts if events trigger.
        """
        # Get all tickers subscribed by at least one user
        tickers = database.get_unique_tickers()
        if not tickers:
            print("No subscriptions active. Skipping market scan.")
            return

        for ticker in tickers:
            try:
                stock_data = stock_api.fetch_stock_data(ticker)
                if not stock_data:
                    print(f"Skipping {ticker} scan - could not retrieve stock data.")
                    continue

                self._process_ticker_alerts(ticker, stock_data)
                # Small cool-off between stocks to respect API limits
                time.sleep(1)
            except Exception as e:
                print(f"Error processing scan for {ticker}: {e}")

    def _process_ticker_alerts(self, ticker, stock_data):
        """
        Evaluates technical criteria for a single ticker and alerts subscribers.
        Also checks price change % alerts.
        """
        closes = stock_data["closes"]
        highs = stock_data["highs"]
        lows = stock_data["lows"]
        current_price = stock_data["current_price"]
        currency = stock_data["currency"]

        # Get all users subscribed to this specific ticker
        subscribers = database.get_subscribers_for_ticker(ticker)
        if not subscribers:
            return

        # --- 1. Price Change % Alerts (works even with minimal data) ---
        self._check_price_change_alerts(ticker, current_price, currency, subscribers)

        # Basic validation for technical indicators
        if len(closes) < 21:
            return

        # Calculate indicators
        upper_bands, middle_bands, lower_bands = indicators.calculate_bollinger_bands(closes, period=20)
        rsi_list = indicators.calculate_rsi(closes, period=14)

        # Get latest and previous data points
        price_now = current_price
        price_prev = closes[-2]

        bb_upper_now, bb_middle_now, bb_lower_now = upper_bands[-1], middle_bands[-1], lower_bands[-1]
        bb_upper_prev, bb_middle_prev, bb_lower_prev = upper_bands[-2], middle_bands[-2], lower_bands[-2]

        rsi_now = rsi_list[-1]
        rsi_prev = rsi_list[-2]

        # Verify no calculated values are None
        if None in (bb_upper_now, bb_middle_now, bb_lower_now, bb_upper_prev, bb_middle_prev, bb_lower_prev, rsi_now, rsi_prev):
            return

        # Define alert event conditions
        events = {}

        # 1. Bollinger Band Lower Breach (Strong Buy Potential)
        if price_prev > bb_lower_prev and price_now <= bb_lower_now:
            events["BB_LOWER_BREACH"] = {
                "title": "⚡ 볼린저 밴드 하단 이탈 (매수 찬스)",
                "msg": f"현재가(<b>{price_now:.2f} {currency}</b>)가 볼린저 밴드 하단선(<b>{bb_lower_now:.2f}</b>)을 하향 돌파했습니다. 과매도 반등 가능성이 있습니다.",
                "type": "BB_LOWER"
            }
        # Clear signal when it returns inside bands
        elif price_now > bb_lower_now:
            self._clear_event_for_all(subscribers, ticker, "BB_LOWER")

        # 2. Bollinger Band Upper Breach (Strong Sell Potential)
        if price_prev < bb_upper_prev and price_now >= bb_upper_now:
            events["BB_UPPER_BREACH"] = {
                "title": "⚠️ 볼린저 밴드 상단 돌파 (과열 경보)",
                "msg": f"현재가(<b>{price_now:.2f} {currency}</b>)가 볼린저 밴드 상단선(<b>{bb_upper_now:.2f}</b>)을 상향 돌파했습니다. 단기 과열로 조정 가능성이 있습니다.",
                "type": "BB_UPPER"
            }
        elif price_now < bb_upper_now:
            self._clear_event_for_all(subscribers, ticker, "BB_UPPER")

        # 3. SMA 20 Cross Under (SMA 20 이탈 - 하향 돌파)
        if price_prev >= bb_middle_prev and price_now < bb_middle_now:
            events["SMA_20_CROSS_UNDER"] = {
                "title": "📉 20일 이동평균선 이탈 (추세 하락 우려)",
                "msg": f"현재가(<b>{price_now:.2f} {currency}</b>)가 20일선(<b>{bb_middle_now:.2f}</b>)을 아래로 뚫고 내려왔습니다. 지지선 하향 이탈에 주의하세요.",
                "type": "SMA_20_UNDER"
            }
        elif price_now >= bb_middle_now:
            self._clear_event_for_all(subscribers, ticker, "SMA_20_UNDER")

        # 4. SMA 20 Cross Over (20일선 돌파 - 상향 돌파)
        if price_prev <= bb_middle_prev and price_now > bb_middle_now:
            events["SMA_20_CROSS_OVER"] = {
                "title": "📈 20일 이동평균선 회복 (추세 상승 전환)",
                "msg": f"현재가(<b>{price_now:.2f} {currency}</b>)가 20일선(<b>{bb_middle_now:.2f}</b>) 위로 올라섰습니다. 단기 상승 추세로 전환될 수 있습니다.",
                "type": "SMA_20_OVER"
            }
        elif price_now <= bb_middle_now:
            self._clear_event_for_all(subscribers, ticker, "SMA_20_OVER")

        # 5. RSI Oversold Entrance (RSI 30 이하 과매도 진입)
        if rsi_prev > 30 and rsi_now <= 30:
            events["RSI_OVERSOLD"] = {
                "title": "⚡ RSI 과매도 진입 (반등 대기)",
                "msg": f"RSI 지표가 <b>{rsi_now:.1f}</b>로 과매도 기준선(30 이하)에 진입했습니다. 기술적 반등 유입을 기대해 볼 수 있습니다.",
                "type": "RSI_OVERSOLD"
            }
        elif rsi_now > 30:
            self._clear_event_for_all(subscribers, ticker, "RSI_OVERSOLD")

        # 6. RSI Overbought Entrance (RSI 70 이상 과매수 진입)
        if rsi_prev < 70 and rsi_now >= 70:
            events["RSI_OVERBOUGHT"] = {
                "title": "⚠️ RSI 과매수 진입 (추가 상승 주의)",
                "msg": f"RSI 지표가 <b>{rsi_now:.1f}</b>로 과매수 기준선(70 이상)에 진입했습니다. 고점 매도 매물이 출현할 위험이 큽니다.",
                "type": "RSI_OVERBOUGHT"
            }
        elif rsi_now < 70:
            self._clear_event_for_all(subscribers, ticker, "RSI_OVERBOUGHT")

        # Process and dispatch each triggered event to users
        for event_key, event_info in events.items():
            sig_type = event_info["type"]
            for chat_id in subscribers:
                # Check database to see if we already notified this user about this specific signal
                last_sig = database.get_last_signal(chat_id, ticker, sig_type)
                
                if last_sig is None:
                    # User hasn't been alerted about this current signal cycle yet
                    alert_text = (
                        f"<b>🔔 {event_info['title']}</b>\n"
                        f"종목: <b>{ticker}</b>\n"
                        f"시간: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                        f"{event_info['msg']}\n\n"
                        f"💡 실시간 차트 예측 리포트는 <code>/predict {ticker}</code> 를 입력하여 조회하세요!"
                    )
                    
                    self.bot.send_message(chat_id, alert_text)
                    # Register that we notified the user
                    database.set_last_signal(chat_id, ticker, sig_type, price_now)

    def _check_price_change_alerts(self, ticker, current_price, currency, subscribers):
        """
        전일 종가 대비 5%, 10%, 20% 변동 시 하루에 1번만 알림을 전송합니다.
        더 큰 변동이 먼저 발생하면 작은 변동은 알리지 않습니다.
        예: 본장 시작 직후 -10% 발생 → -5% 알림은 스킵
        """
        # 전일 종가 가져오기
        stock_data = stock_api.fetch_stock_data(ticker)
        if not stock_data:
            return
        prev_close = stock_data.get("previous_close")
        if prev_close is None or prev_close <= 0:
            return

        # 변동률 계산
        pct_change = ((current_price - prev_close) / prev_close) * 100
        abs_pct = abs(pct_change)

        # 오늘 날짜 (KST 기준)
        kst_offset = 9 * 60 * 60
        today_str = time.strftime("%Y-%m-%d", time.gmtime(time.time() + kst_offset))

        # 알림 임계값 리스트 (큰 순서대로)
        thresholds = [20, 10, 5]

        for chat_id in subscribers:
            try:
                # 오늘 이미 보낸 알림 확인
                sent_alerts = database.get_daily_alerts_for_date(chat_id, ticker, today_str)

                # 이미 보낸 최대 임계값 확인
                max_sent = 0
                for alert in sent_alerts:
                    if alert["threshold_pct"] > max_sent:
                        max_sent = alert["threshold_pct"]

                # 이미 더 큰 변동 알림을 보냈으면 스킵
                if max_sent > 0:
                    continue

                # 현재 변동률이 넘는 가장 큰 임계값 찾기
                triggered_threshold = None
                for t in thresholds:
                    if abs_pct >= t:
                        triggered_threshold = t
                        break

                if triggered_threshold is None:
                    continue

                direction = "📈 상승" if pct_change > 0 else "📉 하락"
                emoji = "🟢" if pct_change > 0 else "🔴"

                alert_text = (
                    f"<b>{emoji} [{ticker}] 전일 종가 대비 변동 알림</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💵 현재가: <b>{current_price:.2f} {currency}</b>\n"
                    f"📌 전일 종가: {prev_close:.2f} {currency}\n"
                    f"📊 변동: {direction} <b>{abs_pct:.2f}%</b> (기준: {triggered_threshold}%)\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 상세 분석 리포트는 <code>/predict {ticker}</code> 를 입력하세요!"
                )

                self.bot.send_message(chat_id, alert_text)
                database.record_daily_alert(chat_id, ticker, today_str, triggered_threshold,
                                           "up" if pct_change > 0 else "down")

                # Update last price and last alert price
                database.set_last_price(chat_id, ticker, current_price)

            except Exception as e:
                print(f"Error checking price change for {ticker} (chat {chat_id}): {e}")

    def _clear_event_for_all(self, subscribers, ticker, sig_type):
        """
        Clears the registered alert state for subscribers when conditions normalize.
        This enables them to receive alerts again when conditions are triggered in the future.
        """
        for chat_id in subscribers:
            database.clear_last_signal(chat_id, ticker, sig_type)
