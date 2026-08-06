import time
import threading
from config import CHECK_INTERVAL
import database
import stock_api
import indicators
import market_indices
import market_calendar

class AlertScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.is_running = False
        self.scheduler_thread = None
        self.last_extreme_check_date = None  # 극단 조건 체크 날짜 추적
        self.last_us_market_close_alert_date = None  # 미국장 마감 요약 알림 날짜 추적

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
                # 미국장 마감 요약 알림 체크 (미국 동부 기준 16:00~17:59)
                self._check_us_market_close_alert()
                
                # 극단적 시장 조건 체크 (하루 2~3번)
                self._check_extreme_market_conditions()
                
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

    def _check_us_market_close_alert(self):
        """
        미국장 마감 후 (미국 동부 기준 16:00~17:59) 시장 요약 알림을 전송합니다.
        하루에 한 번만 전송됩니다.
        휴장일(주말/공휴일)에는 전송하지 않습니다.
        """
        # 미국 동부 시간 기준
        now_et = market_calendar.get_us_eastern_now()
        today_str = now_et.strftime("%Y-%m-%d")
        hour = now_et.hour
        
        # 이미 오늘 보냈으면 스킵
        if self.last_us_market_close_alert_date == today_str:
            return
        
        # 미국 동부 시간 16:00~17:59 사이에만 전송 (정규장 마감 이후 요약)
        if not (16 <= hour <= 17):
            return
        
        # 휴장일(주말/미국 공휴일)에는 알림을 보내지 않음
        if not market_calendar.is_us_trading_day(now_et):
            print("📅 오늘은 미국 시장 휴장일입니다. 마감 요약 알림을 건너뜁니다.")
            return
        
        # 구독자가 없으면 스킵
        if not database.get_all_subscriptions():
            return
        
        try:
            print("🇺🇸 Sending US market close summary...")
            
            # 시장 인덱스 데이터 가져오기
            data = market_indices.fetch_all_indices()
            
            # 리포트 생성
            report_text = market_indices.format_us_market_close_report(data)
            
            # 모든 구독자에게 전송
            all_subscriptions = database.get_all_subscriptions()
            sent_to_chats = set()
            
            for chat_id, ticker in all_subscriptions:
                if chat_id in sent_to_chats:
                    continue
                
                topic_id = database.get_chat_topic(chat_id)
                self.bot.send_message(chat_id, report_text, message_thread_id=topic_id)
                sent_to_chats.add(chat_id)
            
            self.last_us_market_close_alert_date = today_str
            print("✅ US market close summary sent successfully.")
            
        except Exception as e:
            print(f"Error sending US market close summary: {e}")

    def _check_extreme_market_conditions(self):
        """
        극단적 시장 조건을 체크하고 알림을 전송합니다.
        - VIX 30 이상 (시장 공포 극대화)
        - 공포탐욕지수 15 이하 또는 85 이상
        - 주요 지수 3% 이상 급등락
        - 환율 2% 이상 급변동
        
        하루에 최대 3번까지 전송 (과도한 알림 방지)
        휴장일(주말/공휴일)에는 체크하지 않습니다.
        """
        kst_offset = 9 * 60 * 60
        now_kst = time.gmtime(time.time() + kst_offset)
        today_str = time.strftime("%Y-%m-%d", now_kst)
        hour = now_kst.tm_hour
        
        # 이미 오늘 3번 보냈으면 스킵
        if self.last_extreme_check_date == today_str:
            return
        
        # 장 시간 중에만 체크 (한국 시간 9:00~16:00)
        if hour < 9 or hour >= 16:
            return
        
        # 휴장일(주말/미국 공휴일)에는 알림을 보내지 않음
        if not market_calendar.is_us_trading_day():
            return
        
        # 구독자가 없으면 스킵
        if not database.get_all_subscriptions():
            return
        
        try:
            # 시장 인덱스 데이터 가져오기
            data = market_indices.fetch_all_indices()
            
            # 극단 조건 체크
            extreme_alerts = market_indices.check_extreme_conditions(data)
            
            if not extreme_alerts:
                return
            
            # 알림 생성
            alert_text = "<b>🚨 극단적 시장 조건 감지</b>\n"
            alert_text += f"⏱ 시간: <code>{time.strftime('%Y-%m-%d %H:%M', now_kst)}</code>\n"
            alert_text += "━━━━━━━━━━━━━━━━━━━\n\n"
            
            for alert_type, message in extreme_alerts:
                alert_text += f"{message}\n"
            
            alert_text += "\n━━━━━━━━━━━━━━━━━━━\n"
            alert_text += "<i>💡 /indices 명령어로 상세 현황을 확인하세요.</i>"
            
            # 모든 구독자에게 전송
            all_subscriptions = database.get_all_subscriptions()
            sent_to_chats = set()
            
            for chat_id, ticker in all_subscriptions:
                if chat_id in sent_to_chats:
                    continue
                if not database.get_chat_alerts_enabled(chat_id):
                    continue
                
                topic_id = database.get_chat_topic(chat_id)
                self.bot.send_message(chat_id, alert_text, message_thread_id=topic_id)
                sent_to_chats.add(chat_id)
            
            self.last_extreme_check_date = today_str
            print(f"⚠️ Extreme market alert sent: {len(extreme_alerts)} conditions detected.")
            
        except Exception as e:
            print(f"Error checking extreme market conditions: {e}")

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
        self._check_price_change_alerts(ticker, current_price, currency, subscribers, stock_data)

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
        stock_name = stock_data.get("name", ticker)
        
        for event_key, event_info in events.items():
            sig_type = event_info["type"]
            for chat_id in subscribers:
                if not database.get_chat_alerts_enabled(chat_id):
                    continue

                # Check database to see if we already notified this user about this specific signal
                last_sig = database.get_last_signal(chat_id, ticker, sig_type)
                
                if last_sig is None:
                    # User hasn't been alerted about this current signal cycle yet
                    alert_text = (
                        f"<b>🔔 {event_info['title']}</b>\n"
                        f"종목: <b>{stock_name}</b> ({ticker})\n"
                        f"시간: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                        f"{event_info['msg']}\n\n"
                        f"💡 실시간 차트 예측 리포트는 <code>/predict {ticker}</code> 를 입력하여 조회하세요!"
                    )
                    
                    # Get chat topic setting for this chat
                    topic_id = database.get_chat_topic(chat_id)
                    self.bot.send_message(chat_id, alert_text, message_thread_id=topic_id)
                    # Register that we notified the user
                    database.set_last_signal(chat_id, ticker, sig_type, price_now)

    def _check_price_change_alerts(self, ticker, current_price, currency, subscribers, stock_data):
        """
        전일 종가 대비 5%, 10%, 20% 변동 시 알림을 전송합니다.
        하루에 동일한 (임계값, 방향) 조합은 1번만 알림을 전송합니다.
        예: 5% 상승 알림을 보냈어도, 이후 10% 상승 또는 5% 하락 시에는 새로 알림을 보냅니다.
        """
        # 전일 종가 (이미 가져온 stock_data에서 사용 - 중복 API 호출 방지)
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

        # 현재 변동 방향
        direction = "up" if pct_change > 0 else "down"

        # 현재 변동률이 넘는 가장 큰 임계값 찾기
        triggered_threshold = None
        for t in thresholds:
            if abs_pct >= t:
                triggered_threshold = t
                break

        if triggered_threshold is None:
            return

        for chat_id in subscribers:
            if not database.get_chat_alerts_enabled(chat_id):
                continue

            try:
                # 오늘 이미 보낸 알림 확인
                sent_alerts = database.get_daily_alerts_for_date(chat_id, ticker, today_str)

                # 이미 보낸 (임계값, 방향) 조합 확인
                sent_keys = set()
                for alert in sent_alerts:
                    sent_keys.add((alert["threshold_pct"], alert["direction"]))

                # 같은 (임계값, 방향) 조합을 이미 오늘 보냈으면 스킵
                if (triggered_threshold, direction) in sent_keys:
                    continue

                direction_label = "📈 상승" if pct_change > 0 else "📉 하락"
                emoji = "🟢" if pct_change > 0 else "🔴"
                stock_name = stock_data.get("name", ticker)

                alert_text = (
                    f"<b>{emoji} [{stock_name}] 전일 종가 대비 변동 알림</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💵 현재가: <b>{current_price:.2f} {currency}</b>\n"
                    f"📌 전일 종가: {prev_close:.2f} {currency}\n"
                    f"📊 변동: {direction_label} <b>{abs_pct:.2f}%</b> (기준: {triggered_threshold}%)\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 상세 분석 리포트는 <code>/predict {ticker}</code> 를 입력하세요!"
                )

                topic_id = database.get_chat_topic(chat_id)
                self.bot.send_message(chat_id, alert_text, message_thread_id=topic_id)
                database.record_daily_alert(chat_id, ticker, today_str, triggered_threshold, direction)

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
