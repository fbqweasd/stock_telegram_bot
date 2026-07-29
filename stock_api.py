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


def _get_latest_price_from_5m(ticker):
    """
    5분봉 차트에서 마지막 유효 종가를 찾습니다.
    프리장/애프터장/정규장 모든 시간대의 가격을 반영합니다.
    """
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=2d&interval=5m"
    
    data = _make_request(url)
    if not data:
        return None, None, None
    
    try:
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        
        # 1순위: meta의 regularMarketPrice (가장 정확한 실시간 값)
        price = meta.get("regularMarketPrice")
        currency = meta.get("currency", "USD")
        market_state = meta.get("marketState", "UNKNOWN")
        
        if price is not None:
            return price, currency, market_state
        
        # 2순위: 5분봉 마지막 유효 close
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        for i in range(len(closes) - 1, -1, -1):
            if closes[i] is not None:
                return closes[i], currency, market_state
    except (IndexError, AttributeError, TypeError):
        pass
    
    return None, None, None


def _get_daily_data(ticker):
    """
    일봉 데이터를 가져옵니다 (기술적 지표 계산용).
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
        return cleaned
        
    except (IndexError, AttributeError, TypeError):
        return None


def fetch_stock_data(ticker):
    """
    Fetches historical daily data + realtime price from Yahoo Finance API.
    
    - 일봉(1d interval, 60일): 기술적 지표 계산용
    - 5분봉(5m interval, 2일): 실시간 현재가 (프리장/애프터장 포함)
    
    Returns a dictionary of cleaned stock data or None if failed.
    """
    ticker = ticker.strip().upper()
    
    # 1. 일봉 데이터 (기술적 지표 계산용)
    daily = _get_daily_data(ticker)
    if not daily:
        return None
    
    # 2. 실시간 현재가 (5분봉)
    realtime_price, currency, market_state = _get_latest_price_from_5m(ticker)
    
    # currency가 None이면 일봉 데이터에서 가져옴
    if currency is None:
        currency = daily.get("currency", "USD")
    
    # 3. 현재가 결정
    current_price = realtime_price
    if current_price is None:
        # 5분봉 실패 시 일봉 마지막 close 사용
        current_price = daily["closes"][-1]
    
    return {
        "ticker": ticker,
        "currency": currency,
        "current_price": current_price,
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
    5분봉 API로 프리장/애프터장/정규장 실시간 가격을 조회합니다.
    """
    ticker = ticker.strip().upper()
    
    # 1순위: 5분봉 API (가장 정확한 실시간 값)
    price, currency, _ = _get_latest_price_from_5m(ticker)
    if price is not None:
        return {"price": price, "currency": currency or "USD"}
    
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
            currency = meta.get("currency", "USD")
            if price is not None:
                return {"price": price, "currency": currency}
        except (IndexError, AttributeError, TypeError):
            pass
    
    # 3순위: 일봉 API (최후의 fallback)
    daily = _get_daily_data(ticker)
    if daily and daily["closes"]:
        return {"price": daily["closes"][-1], "currency": daily.get("currency", "USD")}
    
    return None


if __name__ == "__main__":
    # Test
    for t in ["AAPL", "005930.KS"]:
        data = fetch_stock_data(t)
        if data:
            print(f"\n=== {t} ===")
            print(f"  Current Price: {data['current_price']} {data['currency']}")
            print(f"  Market State: {data['market_state']}")
            print(f"  Daily Data Points: {len(data['closes'])}")
        else:
            print(f"\n=== {t} === Failed")
        
        price_only = fetch_current_price_only(t)
        if price_only:
            print(f"  [Light Fetch] Price: {price_only['price']} {price_only['currency']}")