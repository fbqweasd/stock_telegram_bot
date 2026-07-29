from indicators import calculate_bollinger_bands, calculate_rsi, find_support_resistance

def predict_buy_sell_prices(stock_data):
    """
    Analyzes historical stock data and uses rule-based heuristics to estimate 
    the best buy/sell price targets and recommendations without external ML libraries.
    
    Returns a dictionary containing:
    - current_price
    - buy_target: Predicted optimal entry price.
    - sell_target: Predicted optimal exit price.
    - recommendation: 'STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL'
    - confidence: Score out of 100
    - indicators: Latest calculated technical values (RSI, Bollinger Bands, Support/Resistance)
    """
    closes = stock_data["closes"]
    highs = stock_data["highs"]
    lows = stock_data["lows"]
    current_price = stock_data["current_price"]
    
    # Calculate indicators
    upper_bands, middle_bands, lower_bands = calculate_bollinger_bands(closes, period=20)
    rsi_list = calculate_rsi(closes, period=14)
    support, resistance = find_support_resistance(highs, lows, period=20)
    
    # Extract latest values (last index)
    bb_upper = upper_bands[-1]
    bb_middle = middle_bands[-1]
    bb_lower = lower_bands[-1]
    rsi = rsi_list[-1]
    
    # Safety checks for missing or insufficient calculation data
    if None in (bb_upper, bb_middle, bb_lower, rsi, support, resistance):
        return {
            "current_price": current_price,
            "error": "Insufficient historical data to calculate technical indicators."
        }
    
    # Bandwidth to estimate volatility (narrower = potential breakout coming)
    bandwidth = (bb_upper - bb_lower) / bb_middle
    
    # ------------------ HEURISTIC PRICE PREDICTION ------------------
    # Buy Target: Weighted average of Bollinger Lower Band and the 20-day Support level.
    # In a downtrend, we slant closer to the support level; in a normal range, closer to Bollinger Lower.
    buy_target = (0.6 * bb_lower) + (0.4 * support)
    
    # Sell Target: Weighted average of Bollinger Upper Band and the 20-day Resistance level.
    # In an uptrend, we slant closer to resistance; in a normal range, closer to Bollinger Upper.
    sell_target = (0.6 * bb_upper) + (0.4 * resistance)
    
    # ------------------ RECOMMENDATION & CONFIDENCE ------------------
    # We judge the position of current price relative to the Bollinger Bands
    # 0% is lower band, 50% is middle band, 100% is upper band
    bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper != bb_lower) else 0.5
    
    recommendation = "HOLD"
    confidence = 50
    
    # Buy Signals
    if current_price <= bb_lower or rsi <= 30:
        if current_price <= support or rsi <= 25:
            recommendation = "STRONG BUY"
            # Higher confidence if indicators align (both price low and RSI oversold)
            confidence = 80 + min(15, max(0, (30 - rsi) * 2))
        else:
            recommendation = "BUY"
            confidence = 65 + min(15, max(0, (35 - rsi)))
            
    # Sell Signals
    elif current_price >= bb_upper or rsi >= 70:
        if current_price >= resistance or rsi >= 75:
            recommendation = "STRONG SELL"
            confidence = 80 + min(15, max(0, (rsi - 70) * 2))
        else:
            recommendation = "SELL"
            confidence = 65 + min(15, max(0, (rsi - 65)))
            
    # Gradual recommendations based on BB position and RSI when not in extremes
    else:
        # Slightly leaning Buy
        if bb_position < 0.3 and rsi < 45:
            recommendation = "BUY"
            confidence = 55
        # Slightly leaning Sell
        elif bb_position > 0.7 and rsi > 55:
            recommendation = "SELL"
            confidence = 55
        else:
            recommendation = "HOLD"
            # Confidence is high about HOLDing if price is in the middle and RSI is stable
            confidence = 70 - abs(50 - rsi)
            
    # Limit confidence to realistic boundaries
    confidence = min(95, max(20, round(confidence)))
    
    return {
        "ticker": stock_data["ticker"],
        "currency": stock_data["currency"],
        "current_price": round(current_price, 2),
        "buy_target": round(buy_target, 2),
        "sell_target": round(sell_target, 2),
        "recommendation": recommendation,
        "confidence": confidence,
        "indicators": {
            "rsi": round(rsi, 2),
            "bb_upper": round(bb_upper, 2),
            "bb_middle": round(bb_middle, 2),
            "bb_lower": round(bb_lower, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "bandwidth": round(bandwidth, 4)
        }
    }

if __name__ == "__main__":
    # Small local test
    mock_data = {
        "ticker": "TSLA",
        "currency": "USD",
        "current_price": 175.0,
        "closes": [180 - i*0.5 for i in range(30)], # downward trend
        "highs": [182 - i*0.5 for i in range(30)],
        "lows": [178 - i*0.5 for i in range(30)],
        "opens": [181 - i*0.5 for i in range(30)],
        "volumes": [100000] * 30
    }
    
    result = predict_buy_sell_prices(mock_data)
    import pprint
    pprint.pprint(result)
