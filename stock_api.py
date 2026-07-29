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

def fetch_stock_data(ticker):
    """
    Fetches historical daily data + realtime price from Yahoo Finance API.
    
    - 일봉(1d interval, 60일) 차트로 기술적 지표 계산용 데이터 확보
    - 추가로 당일 5분봉(5m interval, 2일)을 호출하여 장중 실시간 가격 반영
    - 프리장/애프터장 시간에도 현재가를 최대한 정확하게 추적
    
    Returns a dictionary of cleaned stock data or None if failed.
    """
    ticker = ticker.strip().upper()
    encoded_ticker = urllib.parse.quote(ticker)
    
    # ====================================================================
    # 1. 일봉 데이터 (기술적 지표 계산용 - SMA, BB, RSI 등)
    # ====================================================================
    daily_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=60d&interval=1d"
    
    daily_data = _make_request(daily_url)
    if not daily_data:
        return None
    
    daily_result = daily_data.get("chart", {}).get("result")
    if not daily_result or len(daily_result) == 0:
        return None
    
    daily = daily_result[0]
    meta = daily.get("meta", {})
    currency = meta.get("currency", "USD")
    
    timestamps = daily.get("timestamp", [])
    quote = daily.get("indicators", {}).get("quote", [{}])[0]
    
    closes = quote.get("close", [])
    highs = quote.get("high", [])
    lows = quote.get("low", [])
    opens = quote.get("open", [])
    volumes = quote.get("volume", [])
    
    if not timestamps or not closes:
        return None
    
    # Data cleansing for daily data
    cleaned_timestamps = []
    cleaned_closes = []
    cleaned_highs = []
    cleaned_lows = []
    cleaned_opens = []
    cleaned_volumes = []
    
    for i in range(len(timestamps)):
        if (i < len(closes) and closes[i] is not None and
            i < len(highs) and highs[i] is not None and
            i < len(lows) and lows[i] is not None and
            i < len(opens) and opens[i] is not None):
            
            cleaned_timestamps.append(timestamps[i])
            cleaned_closes.append(closes[i])
            cleaned_highs.append(highs[i])
            cleaned_lows.append(lows[i])
            cleaned_opens.append(opens[i])
            
            vol = volumes[i] if (i < len(volumes) and volumes[i] is not None) else 0
            cleaned_volumes.append(vol)
    
    if len(cleaned_closes) < 20:
        return None
    
    # ====================================================================
    # 2. 실시간/장중 현재가 추적 (5분봉, 2일 범위)
    # ====================================================================
    # 5분봉 데이터로 장중(pre-market, regular, after-hours) 현재가 추적
    # range=2d, interval=5m - 약 576개의 5분봉 데이터 제공
    realtime_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=2d&interval=5m"
    
    current_price = meta.get("regularMarketPrice")
    market_state = meta.get("marketState", "REGULAR")  # PRE, REGULAR, POST, CLOSED
    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    
    realtime_data = _make_request(realtime_url)
    
    if realtime_data:
        realtime_result = realtime_data.get("chart", {}).get("result")
        if realtime_result and len(realtime_result) > 0:
            rt = realtime_result[0]
            rt_meta = rt.get("meta", {})
            rt_timestamps = rt.get("timestamp", [])
            rt_quote = rt.get("indicators", {}).get("quote", [{}])[0]
            
            rt_closes = rt_quote.get("close", [])
            
            # meta에서 제공하는 현재가가 null이면 5분봉 마지막 close 사용
            rt_current_price = rt_meta.get("regularMarketPrice")
            
            # 5분봉 데이터에서 마지막 유효 close 찾기 (장중/프리장/애프터장 반영)
            last_valid_close = None
            for i in range(len(rt_closes) - 1, -1, -1):
                if rt_closes[i] is not None:
                    last_valid_close = rt_closes[i]
                    break
            
            # 현재가 우선순위:
            # 1) rt_meta.regularMarketPrice (가장 정확한 실시간 값)
            # 2) 일봉 meta.regularMarketPrice
            # 3) 5분봉 마지막 유효 close
            # 4) 일봉 마지막 close
            # 5) previous close
            if rt_current_price is not None:
                current_price = rt_current_price
            elif current_price is None and last_valid_close is not None:
                current_price = last_valid_close
            elif current_price is None:
                current_price = cleaned_closes[-1] if cleaned_closes else previous_close
    else:
        # 5분봉 조회 실패 시 일봉 데이터만으로 fallback
        if current_price is None:
            current_price = cleaned_closes[-1] if cleaned_closes else previous_close
    
    # 만약 여전히 current_price가 None이면 막힌 previous_close 사용
    if current_price is None or current_price == 0:
        # TradingView 등에서 사용하는 spark API 시도
        spark_url = f"https://query1.finance.yahoo.com/v7/finance/spark?symbols={encoded_ticker}&range=1d&interval=1m"
        spark_data = _make_request(spark_url)
        if spark_data:
            spark_result = spark_data.get("spark", {}).get("result", [])
            if spark_result and len(spark_result) > 0:
                spark_meta = spark_result[0].get("response", [{}])[0].get("meta", {})
                current_price = spark_meta.get("regularMarketPrice") or spark_meta.get("previousClose")
    
    # 최종 fallback
    if current_price is None:
        current_price = cleaned_closes[-1]
    
    return {
        "ticker": ticker,
        "currency": currency,
        "current_price": current_price,
        "previous_close": previous_close,
        "market_state": market_state,
        "timestamps": cleaned_timestamps,
        "closes": cleaned_closes,
        "highs": cleaned_highs,
        "lows": cleaned_lows,
        "opens": cleaned_opens,
        "volumes": cleaned_volumes
    }

def fetch_current_price_only(ticker):
    """
    가벼운 현재가 조회용 함수 (기술적 지표 계산 불필요할 때).
    프리장/애프터장 가격도 포함된 최신 가격만 빠르게 조회.
    """
    ticker = ticker.strip().upper()
    encoded_ticker = urllib.parse.quote(ticker)
    
    # spark API (가장 가벼움)
    url = f"https://query1.finance.yahoo.com/v7/finance/spark?symbols={encoded_ticker}&range=1d&interval=1m"
    data = _make_request(url)
    
    if data:
        try:
            result = data.get("spark", {}).get("result", [{}])[0]
            response = result.get("response", [{}])[0]
            meta = response.get("meta", {})
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            currency = meta.get("currency", "USD")
            if price:
                return {"price": price, "currency": currency}
        except (IndexError, AttributeError):
            pass
    
    # fallback: chart API
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=1d&interval=5m"
    data = _make_request(url)
    if data:
        try:
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice")
            if price is None:
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]
                closes = quote.get("close", [])
                for i in range(len(closes) - 1, -1, -1):
                    if closes[i] is not None:
                        price = closes[i]
                        break
            currency = meta.get("currency", "USD")
            if price:
                return {"price": price, "currency": currency}
        except (IndexError, AttributeError):
            pass
    
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
            print(f"Failed to fetch {t}")
        
        price_only = fetch_current_price_only(t)
        if price_only:
            print(f"  [Light Fetch] Price: {price_only['price']} {price_only['currency']}")