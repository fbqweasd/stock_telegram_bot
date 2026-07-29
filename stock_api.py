import urllib.request
import urllib.parse
import json
import ssl
import time

def _make_request(url, retries=3, delay=2):
    """
    Helper to make HTTP requests with retry logic.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            raise e
    return None


def _get_realtime_price(ticker):
    """
    1분봉 + 5분봉 차트에서 마지막 유효 가격을 찾습니다.
    프리장(PRE) / 정규장(REGULAR) / 애프터장(POST) 모든 시간대 반영.
    데이터가 없으면 전날 종가로 fallback합니다.
    
    1순위: 1분봉(range=2d, interval=1m)
    2순위: 5분봉(range=5d, interval=5m) - 1분봉 실패 시 fallback
    
    반환: (current_price, previous_close, currency, market_state, chart_closes)
      - chart_closes: 1분봉/5분봉에서 추출한 실시간 close 리스트 (previous_close 계산 보조용)
    """
    encoded_ticker = urllib.parse.quote(ticker)
    
    current_price = None
    previous_close = None
    currency = None
    market_state = None
    chart_closes = None
    
    # ================================================================
    # 1순위: 1분봉 (range=2d, interval=1m)
    # ================================================================
    url_1m = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=2d&interval=1m"
    data_1m = _make_request(url_1m)
    
    if data_1m:
        try:
            result = data_1m.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            currency = meta.get("currency", "USD")
            market_state = meta.get("marketState", "UNKNOWN")
            
            # 전일 종가 (Yahoo chart meta)
            previous_close = (meta.get("chartPreviousClose") or 
                            meta.get("previousClose") or 
                            meta.get("regularMarketPreviousClose"))
            
            # 실시간 close 데이터 저장
            closes_1m = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            chart_closes = [c for c in closes_1m if c is not None]
            
            # 현재가: meta.regularMarketPrice
            current_price = meta.get("regularMarketPrice")
            
            # 현재가: 1분봉 마지막 유효 close
            if current_price is None:
                for i in range(len(closes_1m) - 1, -1, -1):
                    if closes_1m[i] is not None:
                        current_price = closes_1m[i]
                        break
        except (IndexError, AttributeError, TypeError):
            pass
    
    # ================================================================
    # 2순위: 5분봉 (range=5d, interval=5m) - 1분봉 실패 시 fallback
    # ================================================================
    if current_price is None:
        url_5m = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=5d&interval=5m"
        data_5m = _make_request(url_5m)
        
        if data_5m:
            try:
                result = data_5m.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                
                if currency is None:
                    currency = meta.get("currency", "USD")
                if market_state is None:
                    market_state = meta.get("marketState", "UNKNOWN")
                if previous_close is None:
                    previous_close = (meta.get("chartPreviousClose") or 
                                    meta.get("previousClose") or 
                                    meta.get("regularMarketPreviousClose"))
                
                closes_5m = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                if chart_closes is None:
                    chart_closes = [c for c in closes_5m if c is not None]
                
                current_price = meta.get("regularMarketPrice")
                if current_price is None:
                    for i in range(len(closes_5m) - 1, -1, -1):
                        if closes_5m[i] is not None:
                            current_price = closes_5m[i]
                            break
            except (IndexError, AttributeError, TypeError):
                pass
    
    return current_price, previous_close, currency, market_state, chart_closes


def _get_daily_data(ticker):
    """
    일봉 데이터를 가져옵니다 (기술적 지표 계산용 + 전일종가).
    반환: { closes, highs, lows, opens, volumes, timestamps, currency, previous_close }
    """
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=60d&interval=1d"
    
    data = _make_request(url)
    if not data:
        return None
    
    try:
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        currency = meta.get("currency", "USD")
        
        # 전일 종가
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        
        timestamps = result.get("timestamp", [])
        quote = result.get("indicators", {}).get("quote", [{}])[0]
        
        closes = quote.get("close", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        opens = quote.get("open", [])
        volumes = quote.get("volume", [])
        
        if not timestamps or not closes:
            return None
        
        # Data cleansing
        cleaned = {
            "timestamps": [],
            "closes": [],
            "highs": [],
            "lows": [],
            "opens": [],
            "volumes": []
        }
        
        for i in range(len(timestamps)):
            if (i < len(closes) and closes[i] is not None and
                i < len(highs) and highs[i] is not None and
                i < len(lows) and lows[i] is not None and
                i < len(opens) and opens[i] is not None):
                
                cleaned["timestamps"].append(timestamps[i])
                cleaned["closes"].append(closes[i])
                cleaned["highs"].append(highs[i])
                cleaned["lows"].append(lows[i])
                cleaned["opens"].append(opens[i])
                cleaned["volumes"].append(
                    volumes[i] if (i < len(volumes) and volumes[i] is not None) else 0
                )
        
        if len(cleaned["closes"]) < 20:
            return None
        
        cleaned["currency"] = currency
        cleaned["previous_close"] = previous_close
        return cleaned
        
    except (IndexError, AttributeError, TypeError):
        return None


def fetch_stock_data(ticker):
    """
    Fetches historical daily data + realtime price from Yahoo Finance API.
    
    - 일봉(1d interval, 60일): 기술적 지표 계산용
    - 5분봉(5m interval, 5일): 실시간 현재가 (프리장/애프터장 포함)
    
    Returns a dictionary of cleaned stock data or None if failed.
    """
    ticker = ticker.strip().upper()
    
    # 1. 일봉 데이터 (기술적 지표 계산용 + 전일종가)
    daily = _get_daily_data(ticker)
    if not daily:
        return None
    
    # 2. 실시간 현재가 (1분봉 + 5분봉) - 프리장/애프터장 포함
    realtime_price, realtime_prev_close, currency, market_state, _ = _get_realtime_price(ticker)
    
    # currency가 None이면 일봉 데이터에서 가져옴
    if currency is None:
        currency = daily.get("currency", "USD")
    
    # 3. 현재가 결정
    current_price = realtime_price
    if current_price is None:
        current_price = daily["closes"][-1]
    
    # 4. 전일 종가 결정 (5분봉 meta 우선, 없으면 일봉 데이터)
    previous_close = realtime_prev_close or daily.get("previous_close")
    if previous_close is None and len(daily["closes"]) >= 2:
        previous_close = daily["closes"][-2]  # 일봉 마지막에서 두번째 값
    
    return {
        "ticker": ticker,
        "currency": currency,
        "current_price": current_price,
        "previous_close": previous_close,
        "market_state": market_state or "UNKNOWN",
        "timestamps": daily["timestamps"],
        "closes": daily["closes"],
        "highs": daily["highs"],
        "lows": daily["lows"],
        "opens": daily["opens"],
        "volumes": daily["volumes"]
    }


def fetch_current_price_only(ticker):
    """
    가벼운 현재가 조회용 함수.
    1분봉/5분봉 API로 프리장/애프터장/정규장 실시간 가격을 조회합니다.
    전일 종가는 일봉 데이터의 chartPreviousClose를 우선 사용하여 정확도를 높입니다.
    반환: { price, previous_close, currency }
    """
    ticker = ticker.strip().upper()
    
    # 1순위: 1분봉 + 5분봉 API (가장 정확한 실시간 값, 프리장/애프터장 포함)
    price, prev_close, currency, _, chart_closes = _get_realtime_price(ticker)
    
    # 전일 종가 보정: 일봉 데이터의 previous_close가 더 정확한 경우가 많음
    # 특히 한국 주식의 경우 intraday API의 previousClose가 부정확할 수 있으므로
    # 일봉 API에서 정확한 전일 종가를 가져옴
    refined_prev_close = prev_close
    
    # intraday prev_close가 None이거나 현재가와 터무니없이 차이나면 일봉에서 보정
    if prev_close is None or prev_close <= 0:
        daily_for_prev = _get_daily_data(ticker)
        if daily_for_prev:
            refined_prev_close = daily_for_prev.get("previous_close")
            if refined_prev_close is None and len(daily_for_prev["closes"]) >= 2:
                refined_prev_close = daily_for_prev["closes"][-2]
    elif chart_closes and len(chart_closes) >= 391:
        # 1분봉 기준 하루 거래시간 약 390분(6.5시간). 391개 이상이면 2일치 데이터가 있음
        # 전일 마지막 봉의 종가를 전일 종가로 사용 (intraday chartPreviousClose보다 정확할 수 있음)
        prev_day_close = chart_closes[-391] if len(chart_closes) >= 391 else None
        if prev_day_close and prev_day_close > 0:
            # API의 previous_close와 차이가 5% 이상 나면 chart 데이터 우선
            if refined_prev_close and refined_prev_close > 0:
                diff_pct = abs(prev_day_close - refined_prev_close) / refined_prev_close
                if diff_pct > 0.05:
                    refined_prev_close = prev_day_close
            else:
                refined_prev_close = prev_day_close
    
    if price is not None:
        return {
            "price": price,
            "previous_close": refined_prev_close,
            "currency": currency or "USD"
        }
    
    # 2순위: spark API (fallback)
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v7/finance/spark?symbols={encoded_ticker}&range=1d&interval=1m"
    data = _make_request(url)
    if data:
        try:
            result = data.get("spark", {}).get("result", [{}])[0]
            response = result.get("response", [{}])[0]
            meta = response.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose")
            currency = meta.get("currency", "USD")
            if price is not None:
                return {"price": price, "previous_close": prev_close, "currency": currency}
        except (IndexError, AttributeError, TypeError):
            pass
    
    # 3순위: 일봉 API (최후의 fallback)
    daily = _get_daily_data(ticker)
    if daily and daily["closes"]:
        prev_close = daily.get("previous_close")
        if prev_close is None and len(daily["closes"]) >= 2:
            prev_close = daily["closes"][-2]
        return {
            "price": daily["closes"][-1],
            "previous_close": prev_close,
            "currency": daily.get("currency", "USD")
        }
    
    return None


if __name__ == "__main__":
    # Test
    for t in ["AAPL", "005930.KS"]:
        data = fetch_stock_data(t)
        if data:
            print(f"\n=== {t} ===")
            print(f"  Current Price: {data['current_price']} {data['currency']}")
            print(f"  Previous Close: {data['previous_close']}")
            print(f"  Market State: {data['market_state']}")
            print(f"  Daily Data Points: {len(data['closes'])}")
        else:
            print(f"\n=== {t} === Failed")
        
        price_only = fetch_current_price_only(t)
        if price_only:
            print(f"  [Light Fetch] Price: {price_only['price']} "
                  f"(Prev: {price_only['previous_close']}) {price_only['currency']}")