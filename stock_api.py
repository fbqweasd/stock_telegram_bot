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
            # chartPreviousClose는 range 시작 이전 종가이므로 부적합할 수 있음
            # previousClose / regularMarketPreviousClose가 실제 전일 종가
            previous_close = (meta.get("previousClose") or
                            meta.get("regularMarketPreviousClose") or
                            meta.get("chartPreviousClose"))

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
                    previous_close = (meta.get("previousClose") or
                                    meta.get("regularMarketPreviousClose") or
                                    meta.get("chartPreviousClose"))

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
        
        # 전일 종가 계산
        # includePrePost=true로 인해 하루에 여러 캔들(프리/정규/애프터)이 생길 수 있음
        # meta.previousClose는 includePrePost와 함께 사용될 때 왜곡될 수 있으므로
        # 타임스탬프 기반 계산을 우선 사용합니다.
        #
        # 1순위: 타임스탬프 기반 계산
        #   - 마지막 날짜(오늘) 이전 날짜(전일)의 마지막 캔들 종가
        # 2순위: Yahoo Finance meta 값 (fallback)
        #   - previousClose / regularMarketPreviousClose / chartPreviousClose
        cleaned["currency"] = currency

        # 타임스탬프를 날짜(YYYY-MM-DD)로 변환
        dates = []
        for ts in cleaned["timestamps"]:
            dt = time.gmtime(ts)
            dates.append(time.strftime("%Y-%m-%d", dt))

        # 마지막 날짜 찾기
        last_date = dates[-1] if dates else None

        # 전일 종가: 마지막 날짜 이전의 마지막 캔들 종가
        prev_close = None
        if last_date:
            for i in range(len(dates) - 1, -1, -1):
                if dates[i] != last_date:
                    prev_close = cleaned["closes"][i]
                    break

        if prev_close is None or prev_close <= 0:
            # 타임스탬프 기반 계산 실패 시 meta 값 사용 (fallback)
            prev_close = (meta.get("previousClose") or
                         meta.get("regularMarketPreviousClose") or
                         meta.get("chartPreviousClose"))

        if prev_close is None or prev_close <= 0:
            # 전일 데이터가 없으면 마지막 종가 사용 (최종 fallback)
            prev_close = cleaned["closes"][-1]

        cleaned["previous_close"] = prev_close
        return cleaned
        
    except (IndexError, AttributeError, TypeError):
        return None


def _get_intraday_data(ticker, interval="5m", range_str="5d"):
    """
    분/시간봉 데이터를 가져옵니다 (기술적 지표 계산용).
    
    interval: 5m, 15m, 30m, 60m, 1h
    range: 1d, 5d, 1mo, 3mo (interval에 따라 적절히 선택)
    
    반환: { closes, highs, lows, opens, volumes, timestamps, currency }
    """
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range={range_str}&interval={interval}&includePrePost=true"
    
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
        
        # 지표 계산에 필요한 최소 데이터 포인트 (MACD에 slow(26) + signal(9) = 35 필요)
        if len(cleaned["closes"]) < 40:
            return None
        
        cleaned["currency"] = currency
        return cleaned
        
    except (IndexError, AttributeError, TypeError):
        return None


def _get_weekly_data(ticker):
    """
    주봉 데이터를 가져옵니다 (기술적 지표 계산용).
    range=2y, interval=1wk → 약 104개의 주봉 데이터
    반환: { closes, highs, lows, opens, volumes, timestamps, currency }
    """
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=2y&interval=1wk&includePrePost=true"
    
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
        
        if len(cleaned["closes"]) < 40:
            return None
        
        cleaned["currency"] = currency
        return cleaned
        
    except (IndexError, AttributeError, TypeError):
        return None


def fetch_stock_name(ticker):
    """
    Yahoo Finance에서 종목명(회사명)을 가져옵니다.
    chart API의 meta.longName 또는 meta.shortName에서 추출합니다.
    실패 시 티커를 그대로 반환합니다.
    """
    ticker = ticker.strip().upper()
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=1d&interval=1d"
    
    try:
        data = _make_request(url)
        if data:
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            name = meta.get("longName") or meta.get("shortName")
            if name:
                return name
    except Exception as e:
        print(f"Error fetching stock name for {ticker}: {e}")
    
    return ticker


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
    
    # 5. 종목명 가져오기
    stock_name = fetch_stock_name(ticker)
    
    return {
        "ticker": ticker,
        "name": stock_name,
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


def fetch_stock_data_intraday(ticker, interval="5m", range_str="5d"):
    """
    5분봉(기본) 단기 데이터를 가져와서 기술적 지표 분석에 사용합니다.
    단기 트레이딩(1~2일) 예측에 적합합니다.
    
    interval: 5m, 15m, 30m, 60m, 1h
    range_str: 1d, 5d, 1mo (interval에 따라 자동 조정 권장)
    
    Returns a dictionary compatible with predictor functions, or None if failed.
    """
    ticker = ticker.strip().upper()
    
    # 1. 분봉 데이터
    intraday = _get_intraday_data(ticker, interval=interval, range_str=range_str)
    if not intraday:
        return None
    
    # 2. 현재가 (마지막 유효 close)
    closes = intraday["closes"]
    current_price = closes[-1] if closes else None
    if current_price is None:
        return None
    
    currency = intraday.get("currency", "USD")
    
    # interval에 따른 봉 이름
    interval_names = {
        "5m": "5분봉", "15m": "15분봉", "30m": "30분봉",
        "60m": "60분봉", "1h": "1시간봉"
    }
    candle_name = interval_names.get(interval, f"{interval}봉")
    
    return {
        "ticker": ticker,
        "currency": currency,
        "current_price": current_price,
        "timeframe": "intraday",
        "candle_name": candle_name,
        "interval": interval,
        "timestamps": intraday["timestamps"],
        "closes": intraday["closes"],
        "highs": intraday["highs"],
        "lows": intraday["lows"],
        "opens": intraday["opens"],
        "volumes": intraday["volumes"]
    }


def fetch_stock_data_weekly(ticker):
    """
    주봉 데이터를 가져와서 기술적 지표 분석에 사용합니다.
    장기 트레이딩(1~3개월) 예측에 적합합니다.
    
    Returns a dictionary compatible with predictor functions, or None if failed.
    """
    ticker = ticker.strip().upper()
    
    # 1. 주봉 데이터
    weekly = _get_weekly_data(ticker)
    if not weekly:
        return None
    
    # 2. 현재가 (마지막 유효 close)
    closes = weekly["closes"]
    current_price = closes[-1] if closes else None
    if current_price is None:
        return None
    
    currency = weekly.get("currency", "USD")
    
    return {
        "ticker": ticker,
        "currency": currency,
        "current_price": current_price,
        "timeframe": "weekly",
        "candle_name": "주봉",
        "interval": "1wk",
        "timestamps": weekly["timestamps"],
        "closes": weekly["closes"],
        "highs": weekly["highs"],
        "lows": weekly["lows"],
        "opens": weekly["opens"],
        "volumes": weekly["volumes"]
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
        # 1. 기존 일봉 데이터
        data = fetch_stock_data(t)
        if data:
            print(f"\n=== {t} (일봉) ===")
            print(f"  Current Price: {data['current_price']} {data['currency']}")
            print(f"  Previous Close: {data['previous_close']}")
            print(f"  Market State: {data['market_state']}")
            print(f"  Daily Data Points: {len(data['closes'])}")
        else:
            print(f"\n=== {t} (일봉) === Failed")
        
        # 2. 5분봉 데이터
        data5 = fetch_stock_data_intraday(t, interval="5m", range_str="5d")
        if data5:
            print(f"\n=== {t} (5분봉) ===")
            print(f"  Current Price: {data5['current_price']} {data5['currency']}")
            print(f"  Candle: {data5['candle_name']}")
            print(f"  Data Points: {len(data5['closes'])}")
        else:
            print(f"\n=== {t} (5분봉) === Failed")
        
        # 3. 주봉 데이터
        data_w = fetch_stock_data_weekly(t)
        if data_w:
            print(f"\n=== {t} (주봉) ===")
            print(f"  Current Price: {data_w['current_price']} {data_w['currency']}")
            print(f"  Candle: {data_w['candle_name']}")
            print(f"  Data Points: {len(data_w['closes'])}")
        else:
            print(f"\n=== {t} (주봉) === Failed")
        
        price_only = fetch_current_price_only(t)
        if price_only:
            print(f"  [Light Fetch] Price: {price_only['price']} "
                  f"(Prev: {price_only['previous_close']}) {price_only['currency']}")