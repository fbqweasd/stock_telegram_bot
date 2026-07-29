import urllib.request
import urllib.parse
import json
import ssl

def fetch_stock_data(ticker):
    """
    Fetches historical and current stock data from Yahoo Finance API without external libraries.
    Returns a dictionary of cleaned stock data or None if failed.
    """
    ticker = ticker.strip().upper()
    # Encodes ticker just in case it contains special characters
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?range=60d&interval=1d"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    # Bypassing SSL verification if needed, although normally standard SSL is fine
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status != 200:
                return None
            
            raw_data = response.read().decode("utf-8")
            data = json.loads(raw_data)
            
            # Access chart result path
            chart_data = data.get("chart", {})
            result = chart_data.get("result")
            
            if not result or len(result) == 0:
                return None
            
            result_data = result[0]
            meta = result_data.get("meta", {})
            current_price = meta.get("regularMarketPrice")
            currency = meta.get("currency", "USD")
            
            timestamps = result_data.get("timestamp", [])
            indicators = result_data.get("indicators", {})
            quote = indicators.get("quote", [{}])[0]
            
            closes = quote.get("close", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            opens = quote.get("open", [])
            volumes = quote.get("volume", [])
            
            # Check for valid structure
            if not timestamps or not closes:
                return None
            
            # Data cleansing: some timestamps/prices might be None due to market closures or anomalies
            cleaned_timestamps = []
            cleaned_closes = []
            cleaned_highs = []
            cleaned_lows = []
            cleaned_opens = []
            cleaned_volumes = []
            
            for i in range(len(timestamps)):
                # Ensure we have all necessary non-None values at this index
                if (
                    i < len(closes) and closes[i] is not None and
                    i < len(highs) and highs[i] is not None and
                    i < len(lows) and lows[i] is not None and
                    i < len(opens) and opens[i] is not None
                ):
                    cleaned_timestamps.append(timestamps[i])
                    cleaned_closes.append(closes[i])
                    cleaned_highs.append(highs[i])
                    cleaned_lows.append(lows[i])
                    cleaned_opens.append(opens[i])
                    
                    # Volume is optional but good to clean if available
                    vol = volumes[i] if (i < len(volumes) and volumes[i] is not None) else 0
                    cleaned_volumes.append(vol)
            
            # If after cleaning we don't have enough data points, return None
            if len(cleaned_closes) < 20:
                return None
                
            # If current price is not in meta, use the last close
            if current_price is None and cleaned_closes:
                current_price = cleaned_closes[-1]
            
            return {
                "ticker": ticker,
                "currency": currency,
                "current_price": current_price,
                "timestamps": cleaned_timestamps,
                "closes": cleaned_closes,
                "highs": cleaned_highs,
                "lows": cleaned_lows,
                "opens": cleaned_opens,
                "volumes": cleaned_volumes
            }
            
    except Exception as e:
        # Silently catch and log to stdout or handle
        print(f"Error fetching stock data for {ticker}: {e}")
        return None

if __name__ == "__main__":
    # Small local test
    data = fetch_stock_data("AAPL")
    if data:
        print(f"AAPL current price: {data['current_price']} {data['currency']}")
        print(f"Cleaned data points: {len(data['closes'])}")
    else:
        print("Failed to fetch AAPL stock data.")
