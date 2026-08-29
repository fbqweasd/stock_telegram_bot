"""
Market indices data collection module.
- CNN Fear & Greed Index
- VIX, S&P 500, NASDAQ, DOW
- USD/KRW exchange rate
- US 10Y Treasury yield
- US Dollar Index (DXY)
"""

import urllib.request
import urllib.parse
import json
import ssl
import time

def _make_request(url, headers=None, retries=3, delay=2):
    """HTTP request helper with retry logic."""
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
    Fetch Fear & Greed Index from CNN Money API.
    Returns: { value, classification, previous_close, week_ago, month_ago }
    """
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://money.cnn.com/",
        "Accept": "application/json"
    }
    
    try:
        response = _make_request(url, headers=headers)
        if response:
            data = json.loads(response)
            fg = data.get("fear_and_greed", {})
            
            if not fg or fg.get("score") is None:
                return None
            
            score = float(fg["score"])
            rating_en = fg.get("rating", "")
            
            # 분류 매핑
            classification_map = {
                "extreme fear": "극도 공포",
                "fear": "공포",
                "neutral": "중립",
                "greed": "탐욕",
                "extreme greed": "극도 탐욕"
            }
            
            classification = classification_map.get(rating_en.lower(), rating_en)
            
            # 이전 값들
            previous_close = fg.get("previous_close")
            week_ago = fg.get("previous_1_week")
            month_ago = fg.get("previous_1_month")
            
            return {
                "value": round(score, 1),
                "classification": classification,
                "rating_en": rating_en,
                "previous_close": round(previous_close, 1) if previous_close else None,
                "week_ago": round(week_ago, 1) if week_ago else None,
                "month_ago": round(month_ago, 1) if month_ago else None
            }
    except Exception as e:
        print(f"Error fetching Fear & Greed Index: {e}")
    
    return None


def _extract_previous_close_from_daily(chart_result):
    """
    Yahoo Finance chart API 결과에서 daily OHLC 데이터를 기반으로
    실제 전일 종가를 추출합니다.

    meta.chartPreviousClose는 range=10d로 요청 시 range 시작 이전 종가(약 며칠 전)를
    반환할 수 있어 부적합합니다. 또한 includePrePost=true 응답에서는 일부 캔들의 close가
    None 으로 섞여 있고, 조회 시점(장 전/장중/장마감)에 따라 현재가(regularMarketPrice)에
    해당하는 캔들의 위치가 달라질 수 있습니다.

    따라서 고정 인덱스(예: [-1], [-2])를 사용하지 않고 아래 우선순위로 동적으로 계산합니다.
      1. 현재가(regularMarketPrice)와 일치하는 캔들의 직전 유효 close
         (조회 시점이 달라도 항상 '현재 세션 이전 종가'를 정확히 찾음)
      2. 마지막 날짜 이전 날짜의 마지막 유효 close (타임스탬프 기반, stock_api.py와 동일 패턴)
      3. 유효 close가 1개뿐이면 그 값을 반환
    """
    try:
        quote = chart_result.get("indicators", {}).get("quote", [{}])[0]
        closes = quote.get("close", []) or []
        timestamps = chart_result.get("timestamp", []) or []
        meta = chart_result.get("meta", {})
        current_price = meta.get("regularMarketPrice")

        # 정렬된 (timestamp, close) 유효 페어만 추출 (None 제외)
        pairs = []
        for ts, c in zip(timestamps, closes):
            if c is None:
                continue
            pairs.append((ts, c))

        if not pairs:
            return None

        # 1순위: 현재가와 일치하는 캔들의 직전 유효 close
        if current_price is not None:
            tolerance = max(1e-6, abs(current_price) * 0.001)
            match_idx = None
            for i, (_, c) in enumerate(pairs):
                if abs(c - current_price) <= tolerance:
                    match_idx = i  # 마지막 일치 인덱스를 유지
            if match_idx is not None and match_idx > 0:
                return pairs[match_idx - 1][1]

        # 2순위: 타임스탬프 기반 - 마지막 날짜(오늘) 이전 날짜의 마지막 유효 close
        # 한국 지수이므로 KST(UTC+9) 기준으로 날짜를 판별
        def _kst_date(ts):
            return time.strftime("%Y-%m-%d", time.gmtime(ts + 9 * 60 * 60))

        last_date = _kst_date(pairs[-1][0])
        for i in range(len(pairs) - 1, -1, -1):
            ts, c = pairs[i]
            if _kst_date(ts) != last_date:
                return c

        # 3순위: 같은 날짜만 존재하면 마지막 유효 close
        return pairs[-1][1]
    except (IndexError, AttributeError, TypeError):
        return None


def fetch_vix():
    """
    VIX (CBOE Volatility Index)를 가져옵니다.
    Yahoo Finance에서 ^VIX 티커로 조회
    반환: { value, change, change_pct, previous_close }
    """
    encoded_ticker = urllib.parse.quote("^VIX")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=10d&interval=1d&includePrePost=true"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            
            # 전일 종가: daily OHLC 데이터에서 직접 추출 (meta.chartPreviousClose는 range=10d일 때 부정확)
            previous_close = _extract_previous_close_from_daily(result)
            if previous_close is None:
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
    - NASDAQ 100 (^NDX)
    - DOW Jones (^DJI)
    반환: { sp500: {...}, nasdaq: {...}, nasdaq100: {...}, dow: {...} }
    """
    indices = {
        "sp500": {"symbol": "^GSPC", "name": "S&P 500"},
        "nasdaq": {"symbol": "^IXIC", "name": "NASDAQ"},
        "nasdaq100": {"symbol": "^NDX", "name": "NASDAQ 100"},
        "dow": {"symbol": "^DJI", "name": "DOW"}
    }
    
    result = {}
    
    for key, info in indices.items():
        encoded_symbol = urllib.parse.quote(info["symbol"])
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=10d&interval=1d&includePrePost=true"
        
        try:
            response = _make_request(url)
            if response:
                data = json.loads(response)
                chart_result = data.get("chart", {}).get("result", [{}])[0]
                meta = chart_result.get("meta", {})
                
                current_price = meta.get("regularMarketPrice")
                
                # 전일 종가: daily OHLC 데이터에서 직접 추출 (meta.chartPreviousClose는 range=10d일 때 부정확)
                previous_close = _extract_previous_close_from_daily(chart_result)
                if previous_close is None:
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
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=10d&interval=1d&includePrePost=true"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            
            # 전일 종가: daily OHLC 데이터에서 직접 추출 (meta.chartPreviousClose는 range=10d일 때 부정확)
            previous_close = _extract_previous_close_from_daily(result)
            if previous_close is None:
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
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=10d&interval=1d&includePrePost=true"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            
            # 전일 종가: daily OHLC 데이터에서 직접 추출 (meta.chartPreviousClose는 range=10d일 때 부정확)
            previous_close = _extract_previous_close_from_daily(result)
            if previous_close is None:
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


def fetch_us_dollar_index():
    """
    US Dollar Index (달러 인덱스, DXY)를 가져옵니다.
    Yahoo Finance에서 DX-Y.NYB 티커로 조회
    반환: { value, change, change_pct, previous_close }
    """
    url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=10d&interval=1d&includePrePost=true"
    
    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_price = meta.get("regularMarketPrice")
            
            # 전일 종가
            previous_close = _extract_previous_close_from_daily(result)
            if previous_close is None:
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
        print(f"Error fetching US Dollar Index: {e}")
    
    return None


def fetch_weekly_indices_data():
    """
    주요 지수의 주간 변동 데이터를 가져옵니다.
    - 미국: S&P 500 (^GSPC), NASDAQ (^IXIC), DOW (^DJI)
    - 한국: KOSPI (^KS11), KOSDAQ (^KQ11)

    지난주(월~금)의 시작 시가와 마지막 종가를 비교하여 주간 변동률을 계산합니다.

    반환: {
        sp500: {...}, nasdaq: {...}, dow: {...},
        kospi: {...}, kosdaq: {...},
        timestamp: "..."
    }
    """
    indices = {
        "sp500": {"symbol": "^GSPC", "name": "S&P 500"},
        "nasdaq": {"symbol": "^IXIC", "name": "NASDAQ"},
        "dow": {"symbol": "^DJI", "name": "DOW"},
        "kospi": {"symbol": "^KS11", "name": "KOSPI"},
        "kosdaq": {"symbol": "^KQ11", "name": "KOSDAQ"}
    }

    result = {}

    for key, info in indices.items():
        weekly = _fetch_weekly_change(info["symbol"])
        if weekly:
            result[key] = {
                "name": info["name"],
                **weekly
            }
        time.sleep(0.5)  # API rate limit 준수

    result["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 60 * 60))

    return result


def _fetch_weekly_change(symbol):
    """
    지난주(월~금) 주간 변동률을 계산합니다.
    Yahoo Finance에서 range=1mo&interval=1d 데이터를 가져와
    지난주 월요일 시가와 금요일 종가를 비교합니다.

    한국 주식/지수: 월요일 시가 = 월요일 open, 금요일 종가 = 금요일 close
    미국 주식/지수: 한국 월요일 아침 = 미국 일요일 저녁이므로 실제 거래일이
                   한국 시간 기준으로 (월~금)이 아닌 (화~토)가 될 수 있습니다.
                   이 함수는 KST 기준 날짜로만 주를 구분하므로,
                   미국 지수는 한국 시각 월요일~금요일에 해당하는 거래일 데이터를 사용합니다.

    반환: {
        value: float,          # 지난주 마지막 거래일 종가
        week_change: float,    # 주간 변동 금액
        week_change_pct: float # 주간 변동률 (%)
    } 또는 None
    """
    encoded_symbol = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=1mo&interval=1d&includePrePost=false"

    try:
        response = _make_request(url)
        if response:
            data = json.loads(response)
            result = data.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp", [])
            quote = result.get("indicators", {}).get("quote", [{}])[0]
            closes = quote.get("close", [])
            opens = quote.get("open", [])

            # 유효한 (timestamp, open, close) 페어만 추출
            pairs = []
            for i in range(len(timestamps)):
                if i < len(closes) and closes[i] is not None and i < len(opens) and opens[i] is not None:
                    pairs.append((timestamps[i], opens[i], closes[i]))

            if len(pairs) < 2:
                return None

            # KST(UTC+9) 기준 날짜 변환
            def _kst_date(ts):
                return time.strftime("%Y-%m-%d", time.gmtime(ts + 9 * 60 * 60))

            def _kst_weekday(ts):
                # 0=월요일 ... 6=일요일 (KST 기준)
                return time.gmtime(ts + 9 * 60 * 60).tm_wday

            # 지난주(월~금) 범위 계산 (KST 기준)
            now_kst = time.gmtime(time.time() + 9 * 60 * 60)
            today_weekday = now_kst.tm_wday

            # 이번 주 월요일 00:00 (KST)
            this_monday_ts = time.time() - (today_weekday * 86400)
            this_monday = time.gmtime(this_monday_ts + 9 * 60 * 60)
            this_monday_str = time.strftime("%Y-%m-%d", this_monday)

            # 지난주 월요일~금요일 날짜 문자열
            last_monday_ts = this_monday_ts - 7 * 86400
            last_friday_ts = this_monday_ts - 3 * 86400
            last_monday_str = time.strftime("%Y-%m-%d", time.gmtime(last_monday_ts + 9 * 60 * 60))
            last_friday_str = time.strftime("%Y-%m-%d", time.gmtime(last_friday_ts + 9 * 60 * 60))

            # 지난주 월요일 시가와 금요일 종가 찾기
            week_start_price = None
            week_end_price = None

            for i in range(len(pairs)):
                ts, o, c = pairs[i]
                date_str = _kst_date(ts)
                if date_str == last_monday_str:
                    week_start_price = o
                if date_str == last_friday_str:
                    week_end_price = c

            # 금요일 데이터가 없으면 (휴장 등) 가장 가까운 이전 거래일 사용
            if week_end_price is None:
                for i in range(len(pairs) - 1, -1, -1):
                    ts, o, c = pairs[i]
                    date_str = _kst_date(ts)
                    if date_str < last_friday_str and date_str >= last_monday_str:
                        week_end_price = c
                        break

            # 월요일 데이터가 없으면 (휴장 등) 가장 가까운 이후 거래일 사용
            if week_start_price is None:
                for i in range(len(pairs)):
                    ts, o, c = pairs[i]
                    date_str = _kst_date(ts)
                    if date_str > last_monday_str and date_str <= last_friday_str:
                        week_start_price = o
                        break

            if week_start_price is None or week_end_price is None or week_start_price <= 0:
                return None

            week_change = week_end_price - week_start_price
            week_change_pct = (week_change / week_start_price) * 100

            return {
                "value": round(week_end_price, 2),
                "week_change": round(week_change, 2),
                "week_change_pct": round(week_change_pct, 2)
            }
    except Exception as e:
        print(f"Error fetching weekly change for {symbol}: {e}")

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
        us_dollar_index: {...},
        timestamp: "..."
    }
    """
    result = {
        "fear_greed": None,
        "vix": None,
        "indices": {},
        "usd_krw": None,
        "treasury_10y": None,
        "us_dollar_index": None,
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
    time.sleep(0.5)
    
    # US Dollar Index (DXY)
    result["us_dollar_index"] = fetch_us_dollar_index()
    
    return result


def fetch_korea_market_indices():
    """
    한국 주요 시장 지수를 가져옵니다.
    - KOSPI (^KS11)
    - KOSDAQ (^KQ11)
    반환: { kospi: {...}, kosdaq: {...} }
    각 항목: { name, value, change, change_pct, previous_close }
    """
    indices = {
        "kospi": {"symbol": "^KS11", "name": "KOSPI"},
        "kosdaq": {"symbol": "^KQ11", "name": "KOSDAQ"}
    }

    result = {}

    for key, info in indices.items():
        encoded_symbol = urllib.parse.quote(info["symbol"])
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=10d&interval=1d&includePrePost=true"

        try:
            response = _make_request(url)
            if response:
                data = json.loads(response)
                chart_result = data.get("chart", {}).get("result", [{}])[0]
                meta = chart_result.get("meta", {})

                current_price = meta.get("regularMarketPrice")

                # 전일 종가: daily OHLC 데이터에서 직접 추출
                previous_close = _extract_previous_close_from_daily(chart_result)
                if previous_close is None:
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


def fetch_korea_market_close_data():
    """
    한국장 마감 요약에 필요한 데이터를 한 번에 가져옵니다.
    - KOSPI, KOSDAQ (국내 지수)
    - USD/KRW 환율
    - (참고) 공포탐욕지수, VIX, 미국 주요 지수
    반환: {
        korea_indices: { kospi: {...}, kosdaq: {...} },
        usd_krw: {...},
        fear_greed: {...},
        vix: {...},
        us_indices: { sp500: {...}, nasdaq: {...}, dow: {...} },
        date: "...",
        timestamp: "..."
    }
    """
    result = {
        "korea_indices": {},
        "usd_krw": None,
        "fear_greed": None,
        "vix": None,
        "us_indices": {},
        "date": time.strftime("%Y-%m-%d", time.gmtime(time.time() + 9 * 60 * 60)),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 60 * 60))
    }

    # 국내 지수 (KOSPI, KOSDAQ)
    result["korea_indices"] = fetch_korea_market_indices()
    time.sleep(0.5)

    # USD/KRW 환율
    result["usd_krw"] = fetch_usd_krw()
    time.sleep(0.5)

    # 참고 정보
    result["fear_greed"] = fetch_fear_greed_index()
    time.sleep(0.5)
    result["vix"] = fetch_vix()
    time.sleep(0.5)
    result["us_indices"] = fetch_market_indices()

    return result


def fetch_index_highs(symbol):
    """
    지수의 역대 최고가와 52주 최고가를 가져옵니다.
    
    - 역대 최고가: range=max&interval=1d (전체 기간 일봉에서 최고가)
    - 52주 최고가: range=1y&interval=1d (1년치 일봉에서 최고가)
    
    반환: {
        all_time_high: float, all_time_high_date: "YYYY-MM-DD",
        week52_high: float, week52_high_date: "YYYY-MM-DD"
    } 또는 None
    """
    encoded_symbol = urllib.parse.quote(symbol)

    all_time_high = None
    all_time_high_date = None
    week52_high = None
    week52_high_date = None

    # ================================================================
    # 1. 역대 최고가: range=max&interval=1d (전체 기간 일봉)
    # ================================================================
    url_max = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?range=max&interval=1d&includePrePost=false"
    )
    response_max = _make_request(url_max)

    if response_max:
        try:
            data = json.loads(response_max)
            result = data.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp", [])
            quote = result.get("indicators", {}).get("quote", [{}])[0]
            highs = quote.get("high", [])

            # 유효한 고가 중 최대값과 해당 날짜 계산
            best_high = None
            best_ts = None
            for i in range(len(timestamps)):
                if i < len(highs) and highs[i] is not None:
                    if best_high is None or highs[i] > best_high:
                        best_high = highs[i]
                        best_ts = timestamps[i]

            if best_high is not None and best_ts is not None:
                all_time_high = best_high
                all_time_high_date = time.strftime("%Y-%m-%d", time.gmtime(best_ts))
        except (IndexError, AttributeError, TypeError, json.JSONDecodeError):
            pass

    # ================================================================
    # 2. 52주 최고가: range=1y&interval=1d (1년치 일봉)
    # ================================================================
    url_1y = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?range=1y&interval=1d&includePrePost=false"
    )
    response_1y = _make_request(url_1y)

    if response_1y:
        try:
            data = json.loads(response_1y)
            result = data.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp", [])
            quote = result.get("indicators", {}).get("quote", [{}])[0]
            highs = quote.get("high", [])

            # 유효한 고가 중 최대값과 해당 날짜 계산
            best_high = None
            best_ts = None
            for i in range(len(timestamps)):
                if i < len(highs) and highs[i] is not None:
                    if best_high is None or highs[i] > best_high:
                        best_high = highs[i]
                        best_ts = timestamps[i]

            if best_high is not None and best_ts is not None:
                week52_high = best_high
                week52_high_date = time.strftime("%Y-%m-%d", time.gmtime(best_ts))
        except (IndexError, AttributeError, TypeError, json.JSONDecodeError):
            pass

    if all_time_high is None and week52_high is None:
        return None

    return {
        "all_time_high": all_time_high,
        "all_time_high_date": all_time_high_date,
        "week52_high": week52_high,
        "week52_high_date": week52_high_date
    }


def fetch_all_index_highs():
    """
    주요 지수들의 역대 최고가와 52주 최고가를 한 번에 가져옵니다.
    - 미국: S&P 500 (^GSPC), NASDAQ (^IXIC), DOW (^DJI)
    - 한국: KOSPI (^KS11), KOSDAQ (^KQ11)
    
    반환: {
        "sp500": {...}, "nasdaq": {...}, "dow": {...},
        "kospi": {...}, "kosdaq": {...}
    }
    """
    indices = {
        "sp500": {"symbol": "^GSPC", "name": "S&P 500"},
        "nasdaq": {"symbol": "^IXIC", "name": "NASDAQ"},
        "dow": {"symbol": "^DJI", "name": "DOW"},
        "kospi": {"symbol": "^KS11", "name": "KOSPI"},
        "kosdaq": {"symbol": "^KQ11", "name": "KOSDAQ"}
    }

    result = {}

    for key, info in indices.items():
        highs = fetch_index_highs(info["symbol"])
        if highs:
            result[key] = {
                "name": info["name"],
                "symbol": info["symbol"],
                **highs
            }
        time.sleep(0.5)  # API rate limit 준수

    return result


def check_index_high_breakouts(data, current_prices):
    """
    지수들이 역대 최고가 또는 52주 최고가를 돌파했는지 감지합니다.
    
    data: fetch_all_index_highs() 결과
    current_prices: { key: current_price } 형태의 현재 지수 값
    
    반환: [(breakout_type, message), ...]
    - breakout_type: "ALL_TIME_HIGH" 또는 "WEEK52_HIGH"
    """
    alerts = []

    for key, info in data.items():
        name = info.get("name", key)
        current_price = current_prices.get(key)

        if current_price is None:
            continue

        all_time_high = info.get("all_time_high")
        all_time_high_date = info.get("all_time_high_date")
        week52_high = info.get("week52_high")
        week52_high_date = info.get("week52_high_date")

        # 역대 최고가 돌파 체크
        if all_time_high is not None and current_price > all_time_high:
            pct_above = ((current_price - all_time_high) / all_time_high) * 100
            alerts.append((
                "ALL_TIME_HIGH",
                f"🏆 <b>{name}</b> 역대 최고가 돌파! "
                f"현재 <b>{current_price:,.2f}</b> (기존 최고: {all_time_high:,.2f}, "
                f"{all_time_high_date or 'N/A'}) +{pct_above:.2f}%"
            ))
        # 52주 최고가 돌파 체크 (역대 최고가와 다를 때만)
        elif week52_high is not None and current_price > week52_high:
            pct_above = ((current_price - week52_high) / week52_high) * 100
            alerts.append((
                "WEEK52_HIGH",
                f"📈 <b>{name}</b> 52주 최고가 돌파! "
                f"현재 <b>{current_price:,.2f}</b> (기존 52주 최고: {week52_high:,.2f}, "
                f"{week52_high_date or 'N/A'}) +{pct_above:.2f}%"
            ))

    return alerts


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
    
    # 6. 달러 인덱스 급변동 체크
    if data.get("us_dollar_index"):
        dxy_change = data["us_dollar_index"].get("change_pct", 0)
        dxy_value = data["us_dollar_index"].get("value", 0)
        
        if abs(dxy_change) >= 1:
            direction = "상승" if dxy_change > 0 else "하락"
            alerts.append(("DXY_MOVE", f"💵 달러 인덱스 {dxy_value:.2f} ({direction} {abs(dxy_change):.2f}%)"))
    
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
        for key in ["sp500", "nasdaq", "nasdaq100", "dow"]:
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
    
    # US Dollar Index (DXY)
    dxy = data.get("us_dollar_index")
    if dxy:
        value = dxy["value"]
        change_pct = dxy.get("change_pct", 0)
        
        emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        
        lines.append(f"\n<b>💵 달러 인덱스 (DXY)</b>")
        lines.append(f"{emoji} <b>{value:.2f}</b> ({change_pct:+.2f}%)")
    
    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    
    return "\n".join(lines)


def format_us_market_close_report(data):
    """
    미국장 마감 후 (미국 동부 기준 16:00 이후) 시장 요약 리포트 형식
    """
    lines = []
    lines.append("<b>🇺🇸 미국장 마감 요약</b>")
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
        for key in ["sp500", "nasdaq", "nasdaq100", "dow"]:
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
    
    # US Dollar Index (DXY)
    dxy = data.get("us_dollar_index")
    if dxy:
        value = dxy["value"]
        change_pct = dxy.get("change_pct", 0)
        lines.append(f"<b>💵 달러 인덱스:</b> {value:.2f} ({change_pct:+.2f}%)")
    
    # 극단 조건 경고
    extreme_alerts = check_extreme_conditions(data)
    if extreme_alerts:
        lines.append("\n━━━━━━━━━━━━━━━━━━━")
        lines.append("<b>⚠️ 극단 조건 경고</b>")
        for alert_type, message in extreme_alerts:
            lines.append(f"• {message}")

    
    return "\n".join(lines)


def format_weekly_report(data):
    """
    주간 시장 요약 리포트 형식
    - 주요 지수 (미국: S&P 500, NASDAQ, DOW / 한국: KOSPI, KOSDAQ) 주간 변동
    - 관심 종목 주간 변동
    - 공포탐욕지수, VIX 참고 정보

    data: {
        indices: { sp500: {...}, nasdaq: {...}, dow: {...}, kospi: {...}, kosdaq: {...} },
        stocks: [ { ticker, name, currency, value, week_change, week_change_pct }, ... ],
        fear_greed: {...},
        vix: {...},
        week_start: "YYYY-MM-DD",
        week_end: "YYYY-MM-DD",
        timestamp: "..."
    }
    """
    lines = []
    lines.append("<b>📊 주간 시장 요약 리포트</b>")
    lines.append(f"📅 <code>{data.get('week_start', '')} ~ {data.get('week_end', '')}</code>")
    lines.append(f"⏱ 생성시간: <code>{data.get('timestamp', '')}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━")

    # 주요 지수 주간 변동
    indices = data.get("indices", {})
    if indices:
        lines.append("\n<b>📈 주요 지수 주간 변동</b>")
        for key in ["sp500", "nasdaq", "dow", "kospi", "kosdaq"]:
            idx = indices.get(key)
            if idx:
                name = idx.get("name", key)
                value = idx.get("value", 0)
                week_change = idx.get("week_change", 0)
                week_change_pct = idx.get("week_change_pct", 0)

                emoji = "🟢" if week_change_pct > 0 else "🔴" if week_change_pct < 0 else "⚪"
                sign = "+" if week_change_pct > 0 else ""

                lines.append(f"• {emoji} <b>{name}</b>: {value:,.2f} ({sign}{week_change_pct:.2f}% · {sign}{week_change:,.2f})")

    # 관심 종목 주간 변동
    stocks = data.get("stocks", [])
    if stocks:
        lines.append("\n<b>⭐ 관심 종목 주간 변동</b>")
        for stock in stocks:
            ticker = stock.get("ticker", "")
            name = stock.get("name", ticker)
            currency = stock.get("currency", "USD")
            value = stock.get("value", 0)
            week_change = stock.get("week_change", 0)
            week_change_pct = stock.get("week_change_pct", 0)

            emoji = "🟢" if week_change_pct > 0 else "🔴" if week_change_pct < 0 else "⚪"
            sign = "+" if week_change_pct > 0 else ""

            lines.append(f"• {emoji} <b>{name}</b> ({ticker}): {value:,.2f} {currency} ({sign}{week_change_pct:.2f}% · {sign}{week_change:,.2f})")

    # 참고 정보
    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    lines.append("<b>🌐 참고 정보</b>")

    fg = data.get("fear_greed")
    if fg and fg.get("value") is not None:
        value = fg["value"]
        classification = fg.get("classification", "")
        week_ago = fg.get("week_ago")
        week_change_str = ""
        if week_ago:
            week_change = value - week_ago
            week_change_str = f" (1주 전 대비 {week_change:+.1f})"
        lines.append(f"• 🎭 공포탐욕지수: <b>{value:.1f}</b> ({classification}){week_change_str}")

    vix = data.get("vix")
    if vix:
        value = vix["value"]
        change_pct = vix.get("change_pct", 0)
        lines.append(f"• 📊 VIX: {value:.2f} ({change_pct:+.2f}%)")


    return "\n".join(lines)


def format_korea_market_close_report(data):
    """
    한국장 마감 후 (한국 시간 15:30 이후) 시장 요약 리포트 형식
    - KOSPI, KOSDAQ (국내 지수)
    - USD/KRW 환율
    - (참고) 공포탐욕지수, VIX, 미국 주요 지수
    """
    lines = []
    lines.append("<b>🇰🇷 한국장 마감 요약</b>")
    lines.append(f"📅 <code>{data.get('date', '')}</code> · ⏱ <code>{data.get('timestamp', '')}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━")

    # 국내 주요 지수 (KOSPI, KOSDAQ)
    korea_indices = data.get("korea_indices", {})
    if korea_indices:
        lines.append("\n<b>📈 국내 주요 지수</b>")
        for key in ["kospi", "kosdaq"]:
            idx = korea_indices.get(key)
            if idx:
                name = idx.get("name", key)
                value = idx.get("value", 0)
                change = idx.get("change", 0)
                change_pct = idx.get("change_pct", 0)

                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""

                lines.append(f"• {emoji} <b>{name}</b>: {value:,.2f} ({sign}{change_pct:.2f}% · {sign}{change:,.2f})")

    # USD/KRW 환율
    krw = data.get("usd_krw")
    if krw:
        value = krw["value"]
        change = krw.get("change", 0)
        change_pct = krw.get("change_pct", 0)

        emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"

        lines.append("\n<b>💱 USD/KRW 환율</b>")
        lines.append(f"{emoji} <b>{value:,.0f}원</b> ({change_pct:+.2f}% · {change:+,.0f}원)")

    # 참고 정보
    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    lines.append("<b>🌐 참고 정보</b>")

    fg = data.get("fear_greed")
    if fg and fg.get("value") is not None:
        value = fg["value"]
        classification = fg.get("classification", "")
        lines.append(f"• 🎭 공포탐욕지수: <b>{value:.1f}</b> ({classification})")

    vix = data.get("vix")
    if vix:
        value = vix["value"]
        change_pct = vix.get("change_pct", 0)
        lines.append(f"• 📊 VIX: {value:.2f} ({change_pct:+.2f}%)")

    us_indices = data.get("us_indices", {})
    if us_indices:
        for key in ["sp500", "nasdaq", "dow"]:
            idx = us_indices.get(key)
            if idx:
                name = idx.get("name", key)
                value = idx.get("value", 0)
                change_pct = idx.get("change_pct", 0)

                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""

                lines.append(f"• {emoji} {name}: {value:,.2f} ({sign}{change_pct:.2f}%)")


    return "\n".join(lines)


if __name__ == "__main__":
    # 테스트
    print("국내 시장 (KOSPI/KOSDAQ) 데이터 가져오는 중...")
    data = fetch_korea_market_close_data()

    print("\n" + "=" * 50)
    print(format_korea_market_close_report(data))

    print("\n" + "=" * 50)
    print("\n전체 시장 인덱스 가져오는 중...")
    all_data = fetch_all_indices()
    print(format_indices_report(all_data))
