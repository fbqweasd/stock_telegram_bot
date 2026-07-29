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


def calculate_ema(prices, period=20):
    """
    Calculates Exponential Moving Average (EMA) of a list of prices.
    Returns a list of EMAs. The first (period - 1) elements will be None.
    
    Handles None values in the input list (e.g., from MACD calculation).
    """
    if len(prices) < period:
        return [None] * len(prices)
    
    ema = [None] * len(prices)
    multiplier = 2 / (period + 1)
    
    # Find first 'period' consecutive non-None values for initial SMA
    valid_indices = [i for i, p in enumerate(prices) if p is not None]
    if len(valid_indices) < period:
        return [None] * len(prices)
    
    first_valid_idx = valid_indices[period - 1]
    ema[first_valid_idx] = sum(prices[i] for i in valid_indices[:period]) / period
    
    # Calculate EMA for remaining indices
    for idx in valid_indices[period:]:
        if ema[idx - 1] is not None:
            ema[idx] = (prices[idx] - ema[idx - 1]) * multiplier + ema[idx - 1]
        else:
            # If previous EMA is None, find the last non-None EMA
            for j in range(idx - 1, -1, -1):
                if ema[j] is not None:
                    ema[idx] = (prices[idx] - ema[j]) * multiplier + ema[j]
                    break
    
    return ema


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


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """
    Calculates MACD (Moving Average Convergence Divergence).
    Returns (macd_line, signal_line, histogram).
    First (slow - 1 + signal - 1) elements will be None.
    """
    if len(prices) < slow + signal:
        return [None] * len(prices), [None] * len(prices), [None] * len(prices)
    
    fast_ema = calculate_ema(prices, fast)
    slow_ema = calculate_ema(prices, slow)
    
    macd_line = [None] * len(prices)
    for i in range(len(prices)):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i]
    
    # Signal line = EMA of MACD line
    signal_line = calculate_ema(macd_line, signal)
    
    # Histogram = MACD - Signal
    histogram = [None] * len(prices)
    for i in range(len(prices)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]
    
    return macd_line, signal_line, histogram


def calculate_momentum(prices, period=10):
    """
    Calculates price momentum (rate of change).
    Returns a list of momentum values. First 'period' elements will be None.
    """
    if len(prices) < period + 1:
        return [None] * len(prices)
    
    momentum = [None] * len(prices)
    for i in range(period, len(prices)):
        if prices[i - period] != 0:
            momentum[i] = ((prices[i] - prices[i - period]) / prices[i - period]) * 100
        else:
            momentum[i] = 0
    
    return momentum


def calculate_volume_trend(volumes, period=20):
    """
    Analyzes volume trend. Returns the average volume ratio.
    > 1.0 means recent volume is higher than average (increased activity)
    < 1.0 means recent volume is lower than average (decreased activity)
    """
    if len(volumes) < period + 5:
        return 1.0
    
    recent = volumes[-5:]  # last 5 days
    historical = volumes[-(period + 5):-5]  # previous 'period' days
    
    avg_recent = sum(recent) / len(recent)
    avg_historical = sum(historical) / len(historical)
    
    if avg_historical == 0:
        return 1.0
    
    return avg_recent / avg_historical


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