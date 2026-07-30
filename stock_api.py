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

    includePrePost=true 파라미터를 사용하여 프리마켓/애프터마켓 거래 데이터를
    포함한 캔들을 가져옵니다. marketState에 관계없이 가장 최근 실제 거래 가격을
    반환하는 것이 목표입니다.

    1순위: 1분봉(range=2d, interval=1m, includePrePost=true)
    2순위: 5분봉(range=5d, interval=5m, includePrePost=true) - 1분봉 실패 시 fallback

    가격 선택 우선순위:
    - 1분봉 캔들 중 마지막 유효 close (프리/본장/애프터 모두 포함)
    - meta.regularMarketPrice (fallback)
    - 5분봉 캔들 중 마지막 유효 close (1분봉 실패 시)

    반환: (current_price, previous_close, currency, market_state)
    """
    encoded_ticker = urllib.parse.quote(ticker)

    current_price = None
    previous_close = None
    currency = None
    market_state = None

    # ================================================================
    # 1순위: 1분봉 (range=2d, interval=1m, includePrePost=true)
    # includePrePost=true: 프리마켓(04:00~09:30 ET) / 애프터마켓(16:00~20:00 ET) 캔들 포함
    # ================================================================
    url_1m = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}"
        f"?range=2d&interval=1m&includePrePost=true"
    )
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

            # 핵심 수정: 1분봉 캔들 중 마지막 유효 close를 우선 사용
            # includePrePost=true 덕분에 PRE/POST 시간대의 실제 거래가도 포함됨
            closes_1m = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            for i in range(len(closes_1m) - 1, -1, -1):
                if closes_1m[i] is not None:
                    current_price = closes_1m[i]
                    break

            # 캔들 데이터가 없는 경우에만 meta.regularMarketPrice로 fallback
            if current_price is None:
                current_price = meta.get("regularMarketPrice")
        except (IndexError, AttributeError, TypeError):
            pass

    # ================================================================
    # 2순위: 5분봉 (range=5d, interval=5m, includePrePost=true) - 1분봉 실패 시 fallback
    # ================================================================
    if current_price is None:
        url_5m = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}"
            f"?range=5d&interval=5m&includePrePost=true"
        )
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

                # 5분봉 캔들 중 마지막 유효 close 우선 사용
                closes_5m = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                for i in range(len(closes_5m) - 1, -1, -1):
                    if closes_5m[i] is not None:
                        current_price = closes_5m[i]
                        break

                # 캔들 데이터가 없는 경우에만 regularMarketPrice로 fallback
                if current_price is None:
                    current_price = meta.get("regularMarketPrice")
            except (IndexError, AttributeError, TypeError):
                pass

    return current_price, previous_close, currency, market_state


def _get_daily_data(ticker):
    """
    일봉 데이터를 가져옵니다 (기술적 지표 계산용 + 전일종가).
    includePrePost=true로 요청하여 장 시작 전/후에도 당일 데이터가 포함되도록 합니다.
    반환: { closes, highs, lows, opens, volumes, timestamps, currency, previous_close }
    """
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=60d&interval=1d&includePrePost=true"
    
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
        
        # 전일 종가: meta.chartPreviousClose는 range=60d 기준 첫 데이터 이전(약 60거래일 전) 종가이므로
        # 실제 전일 종가는 마지막에서 두 번째 값(closes[-2])을 사용
        # closes[-1]은 오늘 종가(장중이면 현재가와 유사)이므로 부적합
        cleaned["currency"] = currency
        if len(cleaned["closes"]) >= 2:
            cleaned["previous_close"] = cleaned["closes"][-2]
        else:
            cleaned["previous_close"] = cleaned["closes"][-1]
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
    realtime_price, realtime_prev_close, currency, market_state = _get_realtime_price(ticker)
    
    # currency가 None이면 일봉 데이터에서 가져옴
    if currency is None:
        currency = daily.get("currency", "USD")
    
    # 3. 현재가 결정
    current_price = realtime_price
    if current_price is None:
        current_price = daily["closes"][-1]
    
    # 4. 전일 종가: _get_daily_data에서 이미 closes[-1]로 정확한 값을 제공
    previous_close = daily.get("previous_close")
    if previous_close is None:
        previous_close = realtime_prev_close
    
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
    실시간 현재가는 1분봉/5분봉 API로, 전일 종가는 일봉 API로 조회합니다.
    반환: { price, previous_close, currency }
    """
    ticker = ticker.strip().upper()
    
    # 1. 일봉 데이터에서 전일 종가 조회 (가장 정확한 기준)
    daily = _get_daily_data(ticker)
    daily_prev_close = daily.get("previous_close") if daily else None
    
    # 2. 실시간 현재가 (1분봉 + 5분봉 API, 프리장/애프터장 포함)
    price, _, currency, _ = _get_realtime_price(ticker)
    
    if price is not None:
        return {
            "price": price,
            "previous_close": daily_prev_close,
            "currency": currency or "USD"
        }
    
    # 3. intraday 실패 시: 일봉 데이터로 fallback
    if daily and daily["closes"]:
        return {
            "price": daily["closes"][-1],
            "previous_close": daily_prev_close,
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