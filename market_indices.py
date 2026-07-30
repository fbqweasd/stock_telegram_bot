"""
시장 인덱스 데이터 수집 모듈
- CNN Fear & Greed Index (공포탐욕지수)
- VIX (변동성 지수)
- S&P 500, NASDAQ, DOW 지수
- USD/KRW 환율
- 미국 10년물 국채 수익률
"""

import urllib.request
import urllib.parse
import json
import ssl
import time
import re

def _make_request(url, headers=None, retries=3, delay=2):
    """
    HTTP 요청을 보내는 헬퍼 함수 (재시도 로직 포함)
    """
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                if response.status == 200:
                    return response.read().decode("utf-8")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            print(f"Request failed for {url}: {e}")
    return None


def fetch_fear_greed_index():
    """
    Fear & Greed Index (공포탐욕지수)를 가져옵니다.
    Alternative.me API 사용 (CNN 데이터 기반)
    반환: { value, classification, previous_close, week_ago, month_ago }
    
    classification:
    - 0-24: Extreme Fear (극도 공포)
    - 25-49: Fear (공포)
    - 50-74: Greed (탐욕)
    - 75-100: Extreme Greed (극도 탐욕)
    """
    # Alternative.me Fear & Greed Index API
    url = "https://api.alternative.me/fng/?limit=30&format=json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = _make_request(url, headers=headers)
        if response:
            data = json.loads(response)
            fng_data = data.get("data", [])
            
            if not fng_data:
                return None
            
            # 현재 값 (첫 번째 항목)
            current = fng_data[0]
            score = float(current.get("value", 0))
            classification_en = current.get("value_classification", "")
            
            # 분류 매핑
            classification_map = {
                "Extreme Fear": "극도 공포",
                "Fear": "공포",
                "Neutral": "중립",
                "Greed": "탐욕",
                "Extreme Greed": "극도 탐욕"
            }
            
            classification = classification_map.get(classification_en, classification_en)
            
            # 이전 값 (1일 전)
            previous_close = None
            week_ago = None
            month_ago = None
            
            if len(fng_data) > 1:
                previous_close = float(fng_data[1].get("value", 0))
            if len(fng_data) > 7:
                week_ago = float(fng_data[7].get("value", 0))
            if len(fng_data) > 30:
                month_ago = float(fng_data[30].get("value", 0))
            
            return {
                "value": round(score, 1),
                "classification": classification,
                "rating_en": classification_en,
                "previous_close": round(previous_close, 1) if previous_close else None,
                "week_ago": round(week_ago, 1) if week_ago else None,
                "month_ago": round(month_ago, 1) if month_ago else None
            }
    except Exception as e:
        print(f"Error fetching Fear & Greed Index: {e}")
    
    return None


def fetch_vix():
    """
    VIX (CBOE Volatility Index)를 가져옵니다.
    Yahoo Finance에서 ^VIX 티커로 조회
    반환: { value, change, change_pct, previous_close }
    """
    encoded_ticker = urllib.parse.quote("^VIX")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=5d&interval=1d"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            
            if current_price and previous_close:
                change = current_price - previous_close
                change_pct = (change / previous_close) * 100
                
                return {
                    "value": round(current_price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "previous_close": round(previous_close, 2)
                }
    except Exception as e:
        print(f"Error fetching VIX: {e}")
    
    return None


def fetch_market_indices():
    """
    주요 시장 지수를 가져옵니다.
    - S&P 500 (^GSPC)
    - NASDAQ Composite (^IXIC)
    - DOW Jones (^DJI)
    반환: { sp500: {...}, nasdaq: {...}, dow: {...} }
    """
    indices = {
        "sp500": {"symbol": "^GSPC", "name": "S&P 500"},
        "nasdaq": {"symbol": "^IXIC", "name": "NASDAQ"},
        "dow": {"symbol": "^DJI", "name": "DOW"}
    }
    
    result = {}
    
    for key, info in indices.items():
        encoded_symbol = urllib.parse.quote(info["symbol"])
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=5d&interval=1d"
        
        try:
            response = _make_request(url)
            if response:
                data = json.loads(response)
                chart_result = data.get("chart", {}).get("result", [{}])[0]
                meta = chart_result.get("meta", {})
                
                current_price = meta.get("regularMarketPrice")
                previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
                
                if current_price and previous_close:
                    change = current_price - previous_close
                    change_pct = (change / previous_close) * 100
                    
                    result[key] = {
                        "name": info["name"],
                        "value": round(current_price, 2),
                        "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                        "previous_close": round(previous_close, 2)
                    }
        except Exception as e:
            print(f"Error fetching {info['name']}: {e}")
        
        time.sleep(0.5)  # API rate limit 준수
    
    return result


def fetch_usd_krw():
    """
    USD/KRW 환율을 가져옵니다.
    Yahoo Finance에서 KRW=X 티커로 조회
    반환: { value, change, change_pct, previous_close }
    """
    encoded_ticker = urllib.parse.quote("KRW=X")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=5d&interval=1d"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            
            if current_price and previous_close:
                change = current_price - previous_close
                change_pct = (change / previous_close) * 100
                
                return {
                    "value": round(current_price, 2),
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 2),
                    "previous_close": round(previous_close, 2)
                }
    except Exception as e:
        print(f"Error fetching USD/KRW: {e}")
    
    return None


def fetch_us_treasury_10y():
    """
    미국 10년물 국채 수익률을 가져옵니다.
    Yahoo Finance에서 ^TNX 티커로 조회
    반환: { value, change, change_pct, previous_close }
    """
    encoded_ticker = urllib.parse.quote("^TNX")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=5d&interval=1d"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            
            if current_price and previous_close:
                change = current_price - previous_close
                change_pct = (change / previous_close) * 100 if previous_close != 0 else 0
                
                return {
                    "value": round(current_price, 3),
                    "change": round(change, 3),
                    "change_pct": round(change_pct, 2),
                    "previous_close": round(previous_close, 3)
                }
    except Exception as e:
        print(f"Error fetching US 10Y Treasury: {e}")
    
    return None


def fetch_all_indices():
    """
    모든 시장 인덱스 데이터를 한 번에 가져옵니다.
    반환: {
        fear_greed: {...},
        vix: {...},
        indices: { sp500: {...}, nasdaq: {...}, dow: {...} },
        usd_krw: {...},
        treasury_10y: {...},
        timestamp: "..."
    }
    """
    result = {
        "fear_greed": None,
        "vix": None,
        "indices": {},
        "usd_krw": None,
        "treasury_10y": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 60 * 60))
    }
    
    # Fear & Greed Index
    result["fear_greed"] = fetch_fear_greed_index()
    time.sleep(0.5)
    
    # VIX
    result["vix"] = fetch_vix()
    time.sleep(0.5)
    
    # Market Indices
    result["indices"] = fetch_market_indices()
    time.sleep(0.5)
    
    # USD/KRW
    result["usd_krw"] = fetch_usd_krw()
    time.sleep(0.5)
    
    # US 10Y Treasury
    result["treasury_10y"] = fetch_us_treasury_10y()
    
    return result


def check_extreme_conditions(data):
    """
    극단적 시장 조건을 감지합니다.
    반환: [(condition_type, message), ...]
    """
    alerts = []
    
    # 1. VIX 극단값 체크
    if data.get("vix"):
        vix_value = data["vix"]["value"]
        vix_change = data["vix"].get("change_pct", 0)
        
        if vix_value >= 30:
            alerts.append(("VIX_HIGH", f"🚨 VIX {vix_value:.1f} - 시장 공포 극대화 (30 이상)"))
        elif vix_value >= 25:
            alerts.append(("VIX_ELEVATED", f"⚠️ VIX {vix_value:.1f} - 변동성 확대 (25 이상)"))
        
        if vix_change >= 10:
            alerts.append(("VIX_SPIKE", f"📈 VIX 급등 +{vix_change:.1f}% - 시장 충격"))
        elif vix_change <= -10:
            alerts.append(("VIX_DROP", f"📉 VIX 급락 {vix_change:.1f}% - 시장 안정"))
    
    # 2. 공포탐욕지수 극단값 체크
    if data.get("fear_greed"):
        fg_value = data["fear_greed"]["value"]
        
        if fg_value is not None:
            if fg_value <= 15:
                alerts.append(("FG_EXTREME_FEAR", f"🔴 공포탐욕지수 {fg_value:.0f} - 극도 공포 (15 이하)"))
            elif fg_value <= 25:
                alerts.append(("FG_FEAR", f"🟠 공포탐욕지수 {fg_value:.0f} - 공포 (25 이하)"))
            elif fg_value >= 85:
                alerts.append(("FG_EXTREME_GREED", f"🟢 공포탐욕지수 {fg_value:.0f} - 극도 탐욕 (85 이상)"))
            elif fg_value >= 75:
                alerts.append(("FG_GREED", f"🟡 공포탐욕지수 {fg_value:.0f} - 탐욕 (75 이상)"))
    
    # 3. 지수 급등락 체크
    if data.get("indices"):
        for key, idx_data in data["indices"].items():
            change_pct = idx_data.get("change_pct", 0)
            name = idx_data.get("name", key)
            
            if change_pct <= -2:
                alerts.append((f"INDEX_DROP_{key}", f"📉 {name} {change_pct:.2f}% 하락"))
            elif change_pct >= 2:
                alerts.append((f"INDEX_RISE_{key}", f"📈 {name} +{change_pct:.2f}% 상승"))
    
    # 4. 환율 급변동 체크
    if data.get("usd_krw"):
        krw_change = data["usd_krw"].get("change_pct", 0)
        krw_value = data["usd_krw"].get("value", 0)
        
        if abs(krw_change) >= 2:
            direction = "상승" if krw_change > 0 else "하락"
            alerts.append(("KRW_SPIKE", f"💱 원/달러 {krw_value:.0f}원 ({direction} {abs(krw_change):.2f}%)"))
    
    # 5. 국채수익률 급변동 체크
    if data.get("treasury_10y"):
        tnx_change = data["treasury_10y"].get("change", 0)
        tnx_value = data["treasury_10y"].get("value", 0)
        
        if abs(tnx_change) >= 0.1:
            direction = "상승" if tnx_change > 0 else "하락"
            alerts.append(("TNX_MOVE", f"📊 미국 10년물 국채 {tnx_value:.3f}% ({direction} {abs(tnx_change):.3f}%p)"))
    
    return alerts


def format_indices_report(data):
    """
    인덱스 데이터를 보기 좋은 리포트 형식으로 변환합니다.
    """
    lines = []
    lines.append("<b>📊 시장 인덱스 현황</b>")
    lines.append(f"⏱ 조회시간: <code>{data.get('timestamp', '')}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    
    # Fear & Greed Index
    fg = data.get("fear_greed")
    if fg and fg.get("value") is not None:
        value = fg["value"]
        classification = fg.get("classification", "")
        
        # 이모지 선택
        if value <= 25:
            emoji = "🔴"
        elif value <= 45:
            emoji = "🟠"
        elif value <= 55:
            emoji = "🟡"
        elif value <= 75:
            emoji = "🟢"
        else:
            emoji = "🟢🔥"
        
        # 이전 대비 변화
        prev = fg.get("previous_close", 0)
        change = value - prev if prev else 0
        change_str = f" (전일 대비 {change:+.1f})" if prev else ""
        
        lines.append(f"\n<b>🎭 공포탐욕지수</b>")
        lines.append(f"{emoji} <b>{value:.1f}</b> - {classification}{change_str}")
        
        # 추이
        week_ago = fg.get("week_ago", 0)
        month_ago = fg.get("month_ago", 0)
        if week_ago:
            week_change = value - week_ago
            lines.append(f"• 1주 전: {week_ago:.1f} ({week_change:+.1f})")
        if month_ago:
            month_change = value - month_ago
            lines.append(f"• 1달 전: {month_ago:.1f} ({month_change:+.1f})")
    
    # VIX
    vix = data.get("vix")
    if vix:
        value = vix["value"]
        change_pct = vix.get("change_pct", 0)
        
        # 이모지 선택
        if value >= 30:
            emoji = "🔴"
        elif value >= 20:
            emoji = "🟠"
        else:
            emoji = "🟢"
        
        change_emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        
        lines.append(f"\n<b>📊 VIX (변동성 지수)</b>")
        lines.append(f"{emoji} <b>{value:.2f}</b> {change_emoji} {change_pct:+.2f}%")
        
        if value >= 25:
            lines.append(f"<i>⚠️ 변동성 확대 구간</i>")
        elif value >= 20:
            lines.append(f"<i>주의 필요</i>")
    
    # Market Indices
    indices = data.get("indices", {})
    if indices:
        lines.append(f"\n<b>📈 주요 지수</b>")
        for key in ["sp500", "nasdaq", "dow"]:
            idx = indices.get(key)
            if idx:
                name = idx.get("name", key)
                value = idx.get("value", 0)
                change_pct = idx.get("change_pct", 0)
                
                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""
                
                lines.append(f"• {emoji} <b>{name}</b>: {value:,.2f} ({sign}{change_pct:.2f}%)")
    
    # USD/KRW
    krw = data.get("usd_krw")
    if krw:
        value = krw["value"]
        change_pct = krw.get("change_pct", 0)
        
        emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        
        lines.append(f"\n<b>💱 USD/KRW 환율</b>")
        lines.append(f"{emoji} <b>{value:,.0f}원</b> ({change_pct:+.2f}%)")
    
    # US Treasury 10Y
    tnx = data.get("treasury_10y")
    if tnx:
        value = tnx["value"]
        change = tnx.get("change", 0)
        
        emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        
        lines.append(f"\n<b>🏛️ 미국 10년물 국채</b>")
        lines.append(f"{emoji} <b>{value:.3f}%</b> ({change:+.3f}%p)")
    
    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    
    return "\n".join(lines)


def format_pre_market_report(data):
    """
    장 시작 전 아침 리포트 형식
    """
    lines = []
    lines.append("<b>🌅 장 시작 전 시장 현황</b>")
    lines.append(f"⏱ 조회시간: <code>{data.get('timestamp', '')}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    
    # Fear & Greed Index
    fg = data.get("fear_greed")
    if fg and fg.get("value") is not None:
        value = fg["value"]
        classification = fg.get("classification", "")
        
        if value <= 25:
            emoji = "🔴"
        elif value <= 45:
            emoji = "🟠"
        elif value <= 55:
            emoji = "🟡"
        elif value <= 75:
            emoji = "🟢"
        else:
            emoji = "🟢🔥"
        
        lines.append(f"\n<b>🎭 공포탐욕지수: {emoji} {value:.1f} ({classification})</b>")
    
    # VIX
    vix = data.get("vix")
    if vix:
        value = vix["value"]
        change_pct = vix.get("change_pct", 0)
        
        if value >= 25:
            emoji = "⚠️"
        else:
            emoji = "✅"
        
        lines.append(f"<b>📊 VIX:</b> {value:.2f} ({change_pct:+.2f}%) {emoji}")
    
    # Market Indices
    indices = data.get("indices", {})
    if indices:
        lines.append("\n<b>📈 주요 지수</b>")
        for key in ["sp500", "nasdaq", "dow"]:
            idx = indices.get(key)
            if idx:
                name = idx.get("name", key)
                value = idx.get("value", 0)
                change_pct = idx.get("change_pct", 0)
                
                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""
                
                lines.append(f"• {emoji} {name}: {value:,.2f} ({sign}{change_pct:.2f}%)")
    
    # USD/KRW
    krw = data.get("usd_krw")
    if krw:
        value = krw["value"]
        change_pct = krw.get("change_pct", 0)
        lines.append(f"\n<b>💱 USD/KRW:</b> {value:,.0f}원 ({change_pct:+.2f}%)")
    
    # US Treasury 10Y
    tnx = data.get("treasury_10y")
    if tnx:
        value = tnx["value"]
        change = tnx.get("change", 0)
        lines.append(f"<b>🏛️ 미국 10년물:</b> {value:.3f}% ({change:+.3f}%p)")
    
    # 극단 조건 경고
    extreme_alerts = check_extreme_conditions(data)
    if extreme_alerts:
        lines.append("\n━━━━━━━━━━━━━━━━━━━")
        lines.append("<b>⚠️ 극단 조건 경고</b>")
        for alert_type, message in extreme_alerts:
            lines.append(f"• {message}")
    
    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    lines.append("<i>💡 오늘도 성공적인 투자 되세요!</i>")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 테스트
    print("Fetching all market indices...")
    data = fetch_all_indices()
    
    print("\n" + "="*50)
    print(format_indices_report(data))
    
    print("\n" + "="*50)
    print("\n극단 조건 체크:")
    alerts = check_extreme_conditions(data)
    for alert_type, message in alerts:
        print(f"  - {message}")