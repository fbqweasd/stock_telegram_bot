import math

def calculate_sma(prices, period=20):
    """
    Calculates Simple Moving Average (SMA) of a list of prices.
    Returns a list of SMAs. The first (period - 1) elements will be None.
    """
    if len(prices) < period:
        return [None] * len(prices)
        
    sma = [None] * len(prices)
    current_sum = sum(prices[:period])
    sma[period - 1] = current_sum / period
    
    for i in range(period, len(prices)):
        current_sum = current_sum - prices[i - period] + prices[i]
        sma[i] = current_sum / period
        
    return sma

def calculate_bollinger_bands(prices, period=20, num_std=2):
    """
    Calculates Bollinger Bands (Upper, Middle/SMA, Lower) of a list of prices.
    Returns three lists: (upper_band, middle_band, lower_band).
    First (period - 1) elements will be None.
    """
    if len(prices) < period:
        return [None] * len(prices), [None] * len(prices), [None] * len(prices)
        
    sma = calculate_sma(prices, period)
    upper_band = [None] * len(prices)
    lower_band = [None] * len(prices)
    
    for i in range(period - 1, len(prices)):
        mean = sma[i]
        # Calculate standard deviation for the period
        variance = sum((prices[j] - mean) ** 2 for j in range(i - period + 1, i + 1)) / period
        std_dev = math.sqrt(variance)
        
        upper_band[i] = mean + (num_std * std_dev)
        lower_band[i] = mean - (num_std * std_dev)
        
    return upper_band, sma, lower_band

def calculate_rsi(prices, period=14):
    """
    Calculates the Relative Strength Index (RSI) using Wilder's Smoothing.
    Returns a list of RSI values. First 'period' elements will be None.
    """
    if len(prices) < period + 1:
        return [None] * len(prices)
        
    rsi = [None] * len(prices)
    
    # Calculate daily price changes
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    
    # Separate gains and losses
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    # Calculate first average gain and loss (SMA)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rsi[period] = 100
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100 - (100 / (1 + rs))
        
    # Apply Wilder's smoothing technique for the remaining periods
    for i in range(period + 1, len(prices)):
        gain = gains[i - 1]
        loss = losses[i - 1]
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi[i] = 100
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))
            
    return rsi

def find_support_resistance(highs, lows, period=20):
    """
    Finds local support and resistance levels based on recent high/low price points.
    Returns (support_level, resistance_level).
    - Support is calculated as the minimum low price over the period.
    - Resistance is calculated as the maximum high price over the period.
    """
    if len(highs) < period or len(lows) < period:
        return None, None
        
    # Get the slice of recent prices
    recent_highs = highs[-period:]
    recent_lows = lows[-period:]
    
    resistance = max(recent_highs)
    support = min(recent_lows)
    
    return support, resistance
