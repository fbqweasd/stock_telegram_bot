import urllib.request
import urllib.parse
import json
import ssl
import time
import threading
from config import TELEGRAM_BOT_TOKEN
import database
import stock_api
import predictor

class TelegramBot:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = None
        self.is_running = False
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
    def _api_call(self, method, data=None):
        """
        Helper method to make HTTP requests to the Telegram Bot API.
        """
        if not self.token:
            print("Telegram Bot Token is not configured. API call skipped.")
            return None
            
        url = f"{self.base_url}/{method}"
        headers = {"Content-Type": "application/json"}
        
        req_data = None
        if data:
            req_data = json.dumps(data).encode("utf-8")
            
        req = urllib.request.Request(url, data=req_data, headers=headers, method="POST" if data else "GET")
        
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=25) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"Telegram API Error on {method}: {e}")
        return None

    def send_message(self, chat_id, text, parse_mode="HTML", reply_to_message_id=None, message_thread_id=None):
        """
        Sends a message to the specified chat_id.
        - reply_to_message_id: 특정 메시지에 답장(Reply) 형태로 보냅니다.
        - message_thread_id: Topics(스레드)가 활성화된 그룹에서 특정 스레드에 메시지를 보냅니다.
        """
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
            
        return self._api_call("sendMessage", payload)

    def get_updates(self):
        """
        Retrieves new messages via Long Polling.
        """
        payload = {"timeout": 20}
        if self.offset is not None:
            payload["offset"] = self.offset
            
        updates = self._api_call("getUpdates", payload)
        if updates and updates.get("ok"):
            return updates.get("result", [])
        return []

    def start_polling(self):
        """
        Starts the long polling thread.
        """
        if not self.token:
            print("Cannot start Telegram Bot: TELEGRAM_BOT_TOKEN is empty.")
            return
            
        self.is_running = True
        self.polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.polling_thread.start()
        print("Telegram Bot Polling Thread Started.")

    def stop_polling(self):
        """
        Stops the long polling thread.
        """
        self.is_running = False
        print("Stopping Telegram Bot Polling...")

    def _poll_loop(self):
        """
        Infinite polling loop running in the background thread.
        """
        while self.is_running:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.offset = update["update_id"] + 1
                    
                    if "message" in update:
                        self._handle_message(update["message"])
            except Exception as e:
                print(f"Error in Polling Loop: {e}")
                time.sleep(5)  # Rest before retrying to prevent aggressive loops
            time.sleep(0.5)

    def _handle_message(self, message):
        """
        Processes incoming messages and dispatches commands.
        단체방 Topics(스레드) 기능을 지원합니다.
        """
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        message_id = message.get("message_id")
        
        # Topics(스레드)가 활성화된 그룹에서 메시지가 속한 스레드 ID
        # is_topic_message: Topics 그룹 여부
        # message_thread_id: 스레드 ID (일반 메시지면 None)
        is_topic_message = message.get("is_topic_message", False)
        message_thread_id = message.get("message_thread_id")
        
        if not chat_id or not text:
            return
            
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            command = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""
            
            # 단체방 Topics 지원: 봇의 응답을 같은 스레드에 보냄
            self._dispatch_command(chat_id, command, arg, reply_to_message_id=message_id, message_thread_id=message_thread_id)

    def _dispatch_command(self, chat_id, command, arg, reply_to_message_id=None, message_thread_id=None):
        """
        Routes the command to the appropriate handler.
        모든 핸들러에 reply_to_message_id와 message_thread_id를 전달합니다.
        한국어 명령어도 지원합니다.
        """
        # 한국어 명령어 매핑
        command_map = {
            "/start": "/start",
            "/시작": "/start",
            "/help": "/help",
            "/도움말": "/help",
            "/add": "/add",
            "/추가": "/add",
            "/del": "/del",
            "/삭제": "/del",
            "/list": "/list",
            "/목록": "/list",
            "/predict": "/predict",
            "/예측": "/predict",
            "/setalert": "/setalert",
            "/알림설정": "/setalert"
        }
        
        # 명령어 정규화
        normalized_cmd = command_map.get(command, command)
        
        if normalized_cmd == "/start":
            self._handle_start(chat_id, reply_to_message_id, message_thread_id)
        elif normalized_cmd == "/help":
            self._handle_help(chat_id, reply_to_message_id, message_thread_id)
        elif normalized_cmd == "/add":
            self._handle_add(chat_id, arg, reply_to_message_id, message_thread_id)
        elif normalized_cmd == "/del":
            self._handle_del(chat_id, arg, reply_to_message_id, message_thread_id)
        elif normalized_cmd == "/list":
            self._handle_list(chat_id, reply_to_message_id, message_thread_id)
        elif normalized_cmd == "/predict":
            self._handle_predict(chat_id, arg, reply_to_message_id, message_thread_id)
        elif normalized_cmd == "/setalert":
            self._handle_setalert(chat_id, arg, reply_to_message_id, message_thread_id)
        else:
            self.send_message(chat_id, "⚠️ 알 수 없는 명령어입니다. 사용 가능한 명령어를 보려면 /help 를 입력하세요.",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_start(self, chat_id, reply_to_message_id=None, message_thread_id=None):
        welcome_text = (
            "<b>📈 주식 모니터링 & 알림 봇에 오신 것을 환영합니다!</b>\n\n"
            "이 봇은 등록하신 관심 주식을 주기적으로 모니터링하여 "
            "<b>20일선 이탈, 볼린저 밴드 하단 돌파, RSI 과매수/과매도</b> 등 "
            "주요 기술적 이벤트 발생 시 자동으로 알림을 전송해 줍니다.\n\n"
            "또한, 순수 기술적 지표들을 종합 분석하여 최적의 매수/매도 가격과 "
            "매매 추천 정보를 언제든지 바로 예측해서 제공합니다.\n\n"
            "<b>ℹ️ 시작하려면 /help 를 입력하여 사용 가능한 명령어 목록을 확인하세요!</b>"
        )
        self.send_message(chat_id, welcome_text, reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_help(self, chat_id, reply_to_message_id=None, message_thread_id=None):
        help_text = (
            "<b>🛠️ 사용 가능한 명령어 목록</b>\n\n"
            "📌 <b>/add [티커]</b> 또는 <b>/추가 [티커]</b> - 관심 주식을 등록합니다.\n"
            "<i>예시: /add AAPL (미국), /추가 005930.KS (삼성전자)</i>\n\n"
            "📌 <b>/del [티커]</b> 또는 <b>/삭제 [티커]</b> - 관심 주식을 삭제합니다.\n"
            "<i>예시: /del AAPL, /삭제 TSLA</i>\n\n"
            "📌 <b>/list</b> 또는 <b>/목록</b> - 내가 구독 중인 주식 리스트와 현재가를 조회합니다.\n\n"
            "📌 <b>/predict [티커]</b> 또는 <b>/예측 [티커]</b> - 특정 주식의 기술적 지표 분석 및 매수/매도 예측 가격을 즉시 조회합니다.\n"
            "<i>예시: /predict TSLA, /예측 AAPL</i>\n\n"
            "📌 <b>/setalert [티커] [변동%]</b> 또는 <b>/알림설정 [티커] [변동%]</b> - 가격 변동 알림 기준을 설정합니다.\n"
            "<i>예시: /setalert AAPL 5, /알림설정 005930.KS 3</i>\n\n"
            "📌 <b>/help</b> 또는 <b>/도움말</b> - 이 도움말을 표시합니다.\n\n"
            "💡 <b>티커 팁:</b>\n"
            "- 미국 주식: 티커명 그대로 입력 (AAPL, TSLA, MSFT)\n"
            "- 한국 코스피: 종목코드.KS 입력 (005930.KS, 000660.KS)\n"
            "- 한국 코스닥: 종목코드.KQ 입력 (247540.KQ)"
        )
        self.send_message(chat_id, help_text, reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_add(self, chat_id, arg, reply_to_message_id=None, message_thread_id=None):
        if not arg:
            self.send_message(chat_id, "⚠️ 사용법: <code>/add [티커]</code> 형태로 입력해 주세요.\n예시: <code>/add AAPL</code>",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
            return
            
        ticker = arg.upper().strip()
        self.send_message(chat_id, f"🔍 <code>{ticker}</code>의 유효성을 검증하는 중입니다...",
                        reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
        
        # Validate stock ticker from API
        stock_data = stock_api.fetch_stock_data(ticker)
        if not stock_data:
            self.send_message(
                chat_id, 
                f"❌ <code>{ticker}</code>는 유효하지 않은 티커이거나 데이터를 가져올 수 없습니다.\n"
                f"티커명이 올바른지 확인해 주세요. (예: AAPL, 005930.KS)",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
            return
            
        # Add to database
        success = database.add_subscription(chat_id, ticker)
        if success:
            self.send_message(
                chat_id, 
                f"✅ <code>{ticker}</code> ({stock_data['currency']})가 성공적으로 등록되었습니다!\n"
                f"실시간 현재가: <b>{stock_data['current_price']:.2f} {stock_data['currency']}</b>\n"
                f"주기적으로 주가를 검사하여 특이사항 발생 시 알림을 보내드릴게요.",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
        else:
            self.send_message(chat_id, f"ℹ️ <code>{ticker}</code>는 이미 등록된 관심 주식입니다.",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_del(self, chat_id, arg, reply_to_message_id=None, message_thread_id=None):
        if not arg:
            self.send_message(chat_id, "⚠️ 사용법: <code>/del [티커]</code> 형태로 입력해 주세요.\n예시: <code>/del AAPL</code>",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
            return
            
        ticker = arg.upper().strip()
        success = database.remove_subscription(chat_id, ticker)
        
        if success:
            # Clear signal history to free up memory
            database.clear_all_signals_for_ticker(chat_id, ticker)
            self.send_message(chat_id, f"✅ <code>{ticker}</code>가 관심 주식에서 성공적으로 삭제되었습니다.",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
        else:
            self.send_message(chat_id, f"⚠️ 등록되지 않은 티커입니다. 등록 정보는 <b>/list</b> 명령어로 확인해 보세요.",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_list(self, chat_id, reply_to_message_id=None, message_thread_id=None):
        subscriptions = database.get_user_subscriptions(chat_id)
        if not subscriptions:
            self.send_message(
                chat_id, 
                "📂 구독 중인 관심 주식이 없습니다.\n"
                "<code>/add [티커]</code> 명령어로 먼저 등록해 보세요!",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
            return
            
        self.send_message(chat_id, "🔄 구독 중인 종목들의 현재가를 가져오는 중...",
                        reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
        
        # 한국 시간 (KST = UTC + 9)
        kst_offset = 9 * 60 * 60
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + kst_offset))
        lines = [f"<b>📋 나의 관심 주식 리스트</b>\n⏱ 조회시간: <code>{now_str}</code>\n"]
        for idx, ticker in enumerate(subscriptions, 1):
            # 빠른 현재가 조회 (프리장/애프터장 포함)
            price_data = stock_api.fetch_current_price_only(ticker)
            if price_data:
                price = price_data['price']
                prev_close = price_data.get('previous_close')
                currency = price_data['currency']
                
                # 전일 대비 등락률 계산
                change_str = ""
                if prev_close is not None and prev_close > 0:
                    pct_change = ((price - prev_close) / prev_close) * 100
                    if abs(pct_change) < 0.01:
                        change_str = " (보합)"
                    elif pct_change > 0:
                        change_str = f" (📈 <b>+{pct_change:.2f}%</b>)"
                    else:
                        change_str = f" (📉 <b>{pct_change:.2f}%</b>)"
                
                # 추천 등급 조회 (predictor 사용)
                rec_str = ""
                try:
                    full_data = stock_api.fetch_stock_data(ticker)
                    if full_data:
                        analysis = predictor.predict_buy_sell_prices(full_data)
                        if "error" not in analysis:
                            rec = analysis["recommendation"]
                            conf = analysis["confidence"]
                            if "STRONG BUY" in rec:
                                rec_str = f" 🟢🔥 <b>{rec}</b> ({conf}%)"
                            elif "BUY" in rec:
                                rec_str = f" 🟢 <b>{rec}</b> ({conf}%)"
                            elif "STRONG SELL" in rec:
                                rec_str = f" 🔴🔥 <b>{rec}</b> ({conf}%)"
                            elif "SELL" in rec:
                                rec_str = f" 🔴 <b>{rec}</b> ({conf}%)"
                            else:
                                rec_str = f" 🟡 <b>{rec}</b> ({conf}%)"
                except Exception:
                    pass
                
                lines.append(f"{idx}. <b>{ticker}</b>: {price:.2f} {currency}{change_str}{rec_str}")
            else:
                # fallback: 전체 데이터 조회
                data = stock_api.fetch_stock_data(ticker)
                if data:
                    price = data['current_price']
                    prev_close = data.get('previous_close')
                    currency = data['currency']
                    
                    change_str = ""
                    if prev_close is not None and prev_close > 0:
                        pct_change = ((price - prev_close) / prev_close) * 100
                        if abs(pct_change) < 0.01:
                            change_str = " (보합)"
                        elif pct_change > 0:
                            change_str = f" (📈 <b>+{pct_change:.2f}%</b>)"
                        else:
                            change_str = f" (📉 <b>{pct_change:.2f}%</b>)"
                    
                    # 추천 등급 조회
                    rec_str = ""
                    try:
                        analysis = predictor.predict_buy_sell_prices(data)
                        if "error" not in analysis:
                            rec = analysis["recommendation"]
                            conf = analysis["confidence"]
                            if "STRONG BUY" in rec:
                                rec_str = f" 🟢🔥 <b>{rec}</b> ({conf}%)"
                            elif "BUY" in rec:
                                rec_str = f" 🟢 <b>{rec}</b> ({conf}%)"
                            elif "STRONG SELL" in rec:
                                rec_str = f" 🔴🔥 <b>{rec}</b> ({conf}%)"
                            elif "SELL" in rec:
                                rec_str = f" 🔴 <b>{rec}</b> ({conf}%)"
                            else:
                                rec_str = f" 🟡 <b>{rec}</b> ({conf}%)"
                    except Exception:
                        pass
                    
                    lines.append(f"{idx}. <b>{ticker}</b>: {price:.2f} {currency}{change_str}{rec_str}")
                else:
                    lines.append(f"{idx}. <b>{ticker}</b>: 데이터 로드 실패 ⚠️")
                
        self.send_message(chat_id, "\n".join(lines), reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_predict(self, chat_id, arg, reply_to_message_id=None, message_thread_id=None):
        if not arg:
            self.send_message(chat_id, "⚠️ 사용법: <code>/predict [티커]</code> 형태로 입력해 주세요.\n예시: <code>/predict TSLA</code>",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
            return
            
        ticker = arg.upper().strip()
        self.send_message(chat_id, f"📊 <code>{ticker}</code> 기술적 지표를 분석하여 매매 가격을 예측하고 있습니다...",
                        reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
        
        stock_data = stock_api.fetch_stock_data(ticker)
        if not stock_data:
            self.send_message(chat_id, f"❌ <code>{ticker}</code> 데이터를 가져오지 못했습니다. 티커명을 확인하세요.",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
            return
            
        analysis = predictor.predict_buy_sell_prices(stock_data)
        if "error" in analysis:
            self.send_message(chat_id, f"⚠️ 분석 실패: {analysis['error']}",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
            return
            
        # Format prediction response
        currency = analysis["currency"]
        rec = analysis["recommendation"]
        
        # Color rating decoration
        emoji = "⚪"
        if "STRONG BUY" in rec:
            emoji = "🟢🔥"
        elif "BUY" in rec:
            emoji = "🟢"
        elif "STRONG SELL" in rec:
            emoji = "🔴🔥"
        elif "SELL" in rec:
            emoji = "🔴"
        else:
            emoji = "🟡"
            
        indicators = analysis["indicators"]
        
        # 판단 근거 설명 추가
        signals = analysis.get("signals", [])
        score = analysis.get("score", 0)
        
        # 점수 해석
        score_interpretation = ""
        if score >= 4.0:
            score_interpretation = "매우 강한 매수 신호 (점수: +{:.1f})".format(score)
        elif score >= 2.0:
            score_interpretation = "강한 매수 신호 (점수: +{:.1f})".format(score)
        elif score >= 0.5:
            score_interpretation = "약한 매수 신호 (점수: +{:.1f})".format(score)
        elif score <= -4.0:
            score_interpretation = "매우 강한 매도 신호 (점수: {:.1f})".format(score)
        elif score <= -2.0:
            score_interpretation = "강한 매도 신호 (점수: {:.1f})".format(score)
        elif score <= -0.5:
            score_interpretation = "약한 매도 신호 (점수: {:.1f})".format(score)
        else:
            score_interpretation = "중립 (점수: {:.1f})".format(score)
        
        report_text = (
            f"<b>📊 [{analysis['ticker']}] 기술적 분석 & 예측 리포트</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💵 현재가: <b>{analysis['current_price']:.2f} {currency}</b>\n"
            f"📢 추천 등급: <b>{emoji} {rec}</b>\n"
            f"🎯 예측 신뢰도: <b>{analysis['confidence']}%</b>\n"
            f"📊 종합 점수: <b>{score_interpretation}</b>\n\n"
            f"🎯 <b>최적의 매수 목표가:</b>\n"
            f"👉 <code>{analysis['buy_target']:.2f} {currency}</code> 이하 추천\n"
            f"<i>(최근 지지선 & 볼린저 하단 조합)</i>\n\n"
            f"🎯 <b>최적의 매도 목표가:</b>\n"
            f"👉 <code>{analysis['sell_target']:.2f} {currency}</code> 이상 추천\n"
            f"<i>(최근 저항선 & 볼린저 상단 조합)</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<b>🔍 판단 근거 (8개 지표 분석)</b>\n"
        )
        
        # 신호 설명 추가 (최대 5개)
        if signals:
            for i, signal in enumerate(signals[:5], 1):
                report_text += f"{i}. {signal}\n"
        else:
            report_text += "분석된 신호가 없습니다.\n"
            
        report_text += (
            f"\n<b>📈 주요 실시간 보조지표</b>\n"
            f"• <b>RSI (14일):</b> {indicators['rsi']} "
            f"{' (과매수 ⚠️)' if indicators['rsi'] >= 70 else ' (과매도 ⚡)' if indicators['rsi'] <= 30 else ' (보통)'}\n"
            f"• <b>MACD:</b> {indicators['macd']:.4f} / Histogram: {indicators['macd_histogram']:.4f}\n"
            f"• <b>모멘텀 (10일):</b> {indicators['momentum']:.2f}%\n"
            f"• <b>볼린저 밴드:</b> {indicators['bb_lower']:.2f} ~ {indicators['bb_upper']:.2f} {currency}\n"
            f"• <b>20일선 vs 50일선:</b> {indicators['sma_20']:.2f} vs {indicators['sma_50']:.2f} {currency}\n"
            f"• <b>지지선/저항선:</b> {indicators['support']:.2f} / {indicators['resistance']:.2f} {currency}\n"
            f"• <b>거래량 동향:</b> {indicators['volume_ratio']:.2f}x (1.0 = 평균)\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ 본 예측치는 단순 보조지표를 바탕으로 한 휴리스틱 연산이며 투자 권유가 아닙니다."
        )
        
        self.send_message(chat_id, report_text, reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)

    def _handle_setalert(self, chat_id, arg, reply_to_message_id=None, message_thread_id=None):
        """
        Sets a custom price change alert threshold (%) for a subscribed ticker.
        Usage: /setalert [티커] [퍼센트]
        Example: /setalert AAPL 5
        """
        if not arg:
            self.send_message(
                chat_id,
                "⚠️ 사용법: <code>/setalert [티커] [변동%]</code> 형태로 입력해 주세요.\n\n"
                "예시:\n"
                "<code>/setalert AAPL 5</code> - AAPL이 5% 이상 변동 시 알림\n"
                "<code>/setalert 005930.KS 3</code> - 삼성전자 3% 이상 변동 시 알림\n\n"
                "📌 현재 설정된 알림 기준은 <code>/list</code> 명령어로 확인 가능합니다.",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
            return

        parts = arg.split()
        if len(parts) != 2:
            self.send_message(
                chat_id,
                "⚠️ 티커와 퍼센트 값을 모두 입력해 주세요.\n"
                "예시: <code>/setalert AAPL 5</code>",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
            return

        ticker = parts[0].upper().strip()
        try:
            threshold = float(parts[1].strip())
            if threshold <= 0 or threshold > 100:
                self.send_message(chat_id, "⚠️ 변동%는 1~100 사이의 값을 입력해 주세요.",
                                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
                return
        except ValueError:
            self.send_message(chat_id, "⚠️ 변동%는 숫자로 입력해 주세요. (예: 5, 3.5, 10)",
                            reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id)
            return

        # Check if user is subscribed to this ticker
        subscriptions = database.get_user_subscriptions(chat_id)
        if ticker not in subscriptions:
            self.send_message(
                chat_id,
                f"⚠️ <code>{ticker}</code>는 등록되지 않은 티커입니다.\n"
                f"먼저 <code>/add {ticker}</code> 명령어로 등록해 주세요.",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
            return

        # Set the threshold
        success = database.set_alert_threshold(chat_id, ticker, threshold)
        if success:
            self.send_message(
                chat_id,
                f"✅ <code>{ticker}</code>의 가격 변동 알림 기준이 <b>{threshold:.1f}%</b>로 설정되었습니다.\n"
                f"이제 {ticker}의 가격이 기준가 대비 {threshold:.1f}% 이상 변동하면 알림을 보내드립니다.",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )
        else:
            self.send_message(
                chat_id,
                f"⚠️ <code>{ticker}</code>의 알림 기준 설정에 실패했습니다. 다시 시도해 주세요.",
                reply_to_message_id=reply_to_message_id, message_thread_id=message_thread_id
            )

if __name__ == "__main__":
    # Local dry run
    bot = TelegramBot()
    # It won't actually poll if TOKEN is empty, but will print info.
    bot.start_polling()
    time.sleep(2)
    bot.stop_polling()