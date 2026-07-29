from indicators import (
    calculate_bollinger_bands, calculate_rsi, find_support_resistance,
    calculate_macd, calculate_momentum, calculate_volume_trend,
    calculate_sma, calculate_ema
)

def predict_buy_sell_prices(stock_data):
    """
    Analyzes historical stock data with multiple technical indicators
    and uses rule-based scoring to estimate the best recommendation.
    
    Indicators used (8 types):
    - RSI (14)          : 과매수/과매도
    - MACD (12,26,9)    : 추세 전환
    - Momentum (10)     : 모멘텀
    - Bollinger Bands(20): 밴드 위치
    - SMA 20 vs 50     : 골든크로스/데드크로스
    - EMA 12 vs 26     : 단기 추세
    - Volume Trend      : 거래량 동향
    - Support/Resistance: 지지/저항
    
    Returns a dictionary containing:
    - recommendation: 'STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL'
    - confidence: Score out of 100
    - indicators: All latest technical values
    """
    closes = stock_data["closes"]
    highs = stock_data["highs"]
    lows = stock_data["lows"]
    volumes = stock_data.get("volumes", [0] * len(closes))
    current_price = stock_data["current_price"]
    
    # ============================================================
    # Calculate ALL indicators
    # ============================================================
    upper_bands, middle_bands, lower_bands = calculate_bollinger_bands(closes, period=20)
    rsi_list = calculate_rsi(closes, period=14)
    macd_line, signal_line, histogram = calculate_macd(closes, fast=12, slow=26, signal=9)
    momentum_list = calculate_momentum(closes, period=10)
    sma_20 = calculate_sma(closes, period=20)
    sma_50 = calculate_sma(closes, period=50)
    ema_12 = calculate_ema(closes, period=12)
    ema_26 = calculate_ema(closes, period=26)
    support, resistance = find_support_resistance(highs, lows, period=20)
    volume_ratio = calculate_volume_trend(volumes, period=20)
    
    # Extract latest values
    bb_upper = upper_bands[-1]
    bb_middle = middle_bands[-1]
    bb_lower = lower_bands[-1]
    rsi = rsi_list[-1]
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    hist_val = histogram[-1]
    momentum = momentum_list[-1]
    sma20_val = sma_20[-1]
    sma50_val = sma_50[-1] if sma_50[-1] is not None else sma20_val
    ema12_val = ema_12[-1]
    ema26_val = ema_26[-1]
    
    # Safety check
    required = [bb_upper, bb_middle, bb_lower, rsi, support, resistance]
    if None in required or macd_val is None or signal_val is None:
        return {
            "current_price": current_price,
            "error": "Insufficient historical data to calculate technical indicators."
        }
    
    bandwidth = (bb_upper - bb_lower) / bb_middle if bb_middle != 0 else 0
    bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper != bb_lower) else 0.5
    
    # ============================================================
    # SCORING SYSTEM: 각 지표별 점수 (-2 ~ +2)
    # 양수 = 매수 신호, 음수 = 매도 신호
    # ============================================================
    score = 0.0
    signals = []
    
    # 1. RSI Score (가중치 2.0)
    if rsi <= 25:
        score += 2.0
        signals.append("RSI 극단적 과매도")
    elif rsi <= 30:
        score += 1.5
        signals.append("RSI 과매도")
    elif rsi <= 40:
        score += 0.5
        signals.append("RSI 저평가 구간")
    elif 45 <= rsi <= 55:
        score += 0.0
        signals.append("RSI 중립")
    elif 60 <= rsi < 70:
        score -= 0.5
        signals.append("RSI 고평가 구간")
    elif rsi >= 70:
        score -= 1.5
        signals.append("RSI 과매수")
    elif rsi >= 75:
        score -= 2.0
        signals.append("RSI 극단적 과매수")
    
    # 2. MACD Score (가중치 2.0)
    if hist_val > 0 and macd_val > 0:
        score += 1.5
        signals.append("MACD 상승 추세 강화")
    elif hist_val > 0 and macd_val < 0:
        score += 1.0
        signals.append("MACD 반등 시도")
    elif hist_val < 0 and macd_val < 0:
        score -= 1.5
        signals.append("MACD 하락 추세 강화")
    elif hist_val < 0 and macd_val > 0:
        score -= 1.0
        signals.append("MACD 하락 반전")
    else:
        score += 0.0
        signals.append("MACD 중립")
    
    # 3. Momentum Score (가중치 1.5)
    if momentum is not None:
        if momentum > 5:
            score += 1.5
            signals.append("강한 상승 모멘텀")
        elif momentum > 2:
            score += 1.0
            signals.append("상승 모멘텀")
        elif momentum > 0:
            score += 0.5
            signals.append("약한 상승 모멘텀")
        elif momentum > -2:
            score -= 0.5
            signals.append("약한 하락 모멘텀")
        elif momentum > -5:
            score -= 1.0
            signals.append("하락 모멘텀")
        else:
            score -= 1.5
            signals.append("강한 하락 모멘텀")
    
    # 4. Bollinger Band Position Score (가중치 1.5)
    if bb_position <= 0.05:
        score += 1.5
        signals.append("볼린저 하단 하회")
    elif bb_position <= 0.2:
        score += 1.0
        signals.append("볼린저 하단 근접")
    elif bb_position <= 0.35:
        score += 0.5
        signals.append("볼린저 하단 부근")
    elif 0.4 <= bb_position <= 0.6:
        score += 0.0
        signals.append("볼린저 중앙")
    elif bb_position >= 0.95:
        score -= 1.5
        signals.append("볼린저 상단 상회")
    elif bb_position >= 0.8:
        score -= 1.0
        signals.append("볼린저 상단 근접")
    elif bb_position >= 0.65:
        score -= 0.5
        signals.append("볼린저 상단 부근")
    
    # 5. SMA 20 vs 50 (Golden Cross / Dead Cross) (가중치 1.5)
    if sma20_val is not None and sma50_val is not None:
        if sma20_val > sma50_val and closes[-2] <= sma50_val and current_price > sma50_val:
            score += 1.5
            signals.append("✅ 골든크로스 발생!")
        elif sma20_val > sma50_val:
            score += 1.0
            signals.append("단기 > 장기 이동평균 (우상향)")
        elif sma20_val < sma50_val and closes[-2] >= sma50_val and current_price < sma50_val:
            score -= 1.5
            signals.append("❌ 데드크로스 발생!")
        elif sma20_val < sma50_val:
            score -= 1.0
            signals.append("단기 < 장기 이동평균 (우하향)")
        else:
            score += 0.0
    
    # 6. EMA 12 vs 26 (단기 추세) (가중치 1.0)
    if ema12_val is not None and ema26_val is not None:
        if ema12_val > ema26_val:
            score += 1.0
            signals.append("EMA12 > EMA26 단기 상승 추세")
        else:
            score -= 1.0
            signals.append("EMA12 < EMA26 단기 하락 추세")
    
    # 7. Volume Trend (가중치 1.0)
    if volume_ratio > 1.5:
        if score > 0:
            score += 1.0
            signals.append("거래량 급증 (매수세 확인)")
        elif score < 0:
            score -= 1.0
            signals.append("거래량 급증 (매도세 확인)")
        else:
            score += 0.5
            signals.append("거래량 급증")
    elif volume_ratio > 1.2:
        if score > 0:
            score += 0.5
            signals.append("거래량 증가 (매수세 동반)")
        elif score < 0:
            score -= 0.5
            signals.append("거래량 증가 (매도세 동반)")
    else:
        score += 0.0
    
    # 8. Support/Resistance Proximity (가중치 1.0)
    if support is not None and resistance is not None:
        dist_to_support = abs(current_price - support) / current_price * 100
        dist_to_resistance = abs(current_price - resistance) / current_price * 100
        
        if dist_to_support < 1.5:  # 지지선 1.5% 이내
            score += 1.0
            signals.append("지지선 근접 (반등 가능)")
        elif dist_to_resistance < 1.5:  # 저항선 1.5% 이내
            score -= 1.0
            signals.append("저항선 근접 (조정 가능)")
    
    # ============================================================
    # FINAL RECOMMENDATION
    # ============================================================
    # 최대 점수: RSI(2.0) + MACD(2.0) + Momentum(1.5) + BB(1.5) + SMA(1.5) + EMA(1.0) + Volume(1.0) + S/R(1.0) = 11.5
    # 최소 점수: -11.5
    # 기준: score > 3 = BUY, score < -3 = SELL, 그외 HOLD
    
    recommendation = "HOLD"
    confidence = 50
    
    if score >= 4.0:
        recommendation = "STRONG BUY"
        confidence = min(95, 75 + int(abs(score) * 1.5))
    elif score >= 2.0:
        recommendation = "BUY"
        confidence = min(90, 60 + int(abs(score) * 3))
    elif score >= 0.5:
        recommendation = "BUY"
        confidence = 55
    elif score <= -4.0:
        recommendation = "STRONG SELL"
        confidence = min(95, 75 + int(abs(score) * 1.5))
    elif score <= -2.0:
        recommendation = "SELL"
        confidence = min(90, 60 + int(abs(score) * 3))
    elif score <= -0.5:
        recommendation = "SELL"
        confidence = 55
    else:
        recommendation = "HOLD"
        # 중립 구간에서도 점수 방향성 표시
        if score > 0:
            confidence = 55 + int(score * 5)
        elif score < 0:
            confidence = 55 + int(abs(score) * 5)
        else:
            confidence = 50
    
    # Limit confidence
    confidence = min(95, max(25, round(confidence)))
    
    # ============================================================
    # PRICE TARGETS
    # ============================================================
    # Buy Target: Bollinger Lower + Support weighted
    buy_target = (0.6 * bb_lower) + (0.4 * support)
    
    # Sell Target: Bollinger Upper + Resistance weighted
    sell_target = (0.6 * bb_upper) + (0.4 * resistance)
    
    return {
        "ticker": stock_data["ticker"],
        "currency": stock_data["currency"],
        "current_price": round(current_price, 2),
        "buy_target": round(buy_target, 2),
        "sell_target": round(sell_target, 2),
        "recommendation": recommendation,
        "confidence": confidence,
        "score": round(score, 2),
        "signals": signals[:5],  # 최대 5개 신호 표시
        "indicators": {
            "rsi": round(rsi, 2),
            "macd": round(macd_val, 4),
            "macd_histogram": round(hist_val, 4),
            "momentum": round(momentum, 2) if momentum is not None else 0,
            "bb_upper": round(bb_upper, 2),
            "bb_middle": round(bb_middle, 2),
            "bb_lower": round(bb_lower, 2),
            "sma_20": round(sma20_val, 2) if sma20_val else 0,
            "sma_50": round(sma50_val, 2) if sma50_val else 0,
            "ema_12": round(ema12_val, 2) if ema12_val else 0,
            "ema_26": round(ema26_val, 2) if ema26_val else 0,
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "bandwidth": round(bandwidth, 4),
            "volume_ratio": round(volume_ratio, 2)
        }
    }

if __name__ == "__main__":
    # Small local test - downtrend (should be SELL)
    mock_data = {
        "ticker": "TSLA",
        "currency": "USD",
        "current_price": 175.0,
        "closes": [180 - i*0.5 for i in range(30)],
        "highs": [182 - i*0.5 for i in range(30)],
        "lows": [178 - i*0.5 for i in range(30)],
        "opens": [181 - i*0.5 for i in range(30)],
        "volumes": [100000 + i*1000 for i in range(30)]
    }
    
    result = predict_buy_sell_prices(mock_data)
    import pprint
    pprint.pprint(result)