import numpy as np
from typing import List, Dict, Any, Optional, Tuple


def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's smoothed RSI."""
    n = len(prices)
    rsi = np.full(n, np.nan)
    if n < period + 1 or period <= 0:
        return rsi

    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period

    if down == 0 and up == 0:
        rsi[period] = 50.0
    elif down == 0:
        rsi[period] = 100.0
    elif up == 0:
        rsi[period] = 0.0
    else:
        rsi[period] = 100.0 - (100.0 / (1.0 + up / down))

    up_val, down_val = up, down
    for i in range(period + 1, n):
        delta = deltas[i - 1]
        if delta > 0:
            up_val = (up_val * (period - 1) + delta) / period
            down_val = (down_val * (period - 1)) / period
        else:
            up_val = (up_val * (period - 1)) / period
            down_val = (down_val * (period - 1) - delta) / period

        if down_val == 0 and up_val == 0:
            rsi[i] = 50.0
        elif down_val == 0:
            rsi[i] = 100.0
        elif up_val == 0:
            rsi[i] = 0.0
        else:
            rsi[i] = 100.0 - (100.0 / (1.0 + up_val / down_val))

    return rsi


def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    n = len(prices)
    ema = np.full(n, np.nan)
    if n < period or period <= 0:
        return ema
    ema[period - 1] = np.mean(prices[:period])
    multiplier = 2.0 / (period + 1)
    for i in range(period, n):
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    n = len(prices)
    sma = np.full(n, np.nan)
    if n < period or period <= 0:
        return sma
    kernel = np.ones(period) / period
    sma[period - 1:] = np.convolve(prices, kernel, mode="valid")
    return sma


def calculate_macd(
    prices: np.ndarray,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD line, Signal line, Histogram."""
    ema_fast = calculate_ema(prices, fast_period)
    ema_slow = calculate_ema(prices, slow_period)
    macd_line = ema_fast - ema_slow

    n = len(prices)
    signal_line = np.full(n, np.nan)
    valid_idx = np.where(~np.isnan(macd_line))[0]
    if len(valid_idx) >= signal_period:
        first_valid = valid_idx[0]
        sig_ema = calculate_ema(macd_line[first_valid:], signal_period)
        signal_line[first_valid:] = sig_ema

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    prices: np.ndarray,
    period: int = 20,
    std_dev_multiplier: float = 2.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: Upper, Middle (SMA), Lower, Bandwidth, %B."""
    n = len(prices)
    middle = calculate_sma(prices, period)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    bandwidth = np.full(n, np.nan)
    percent_b = np.full(n, np.nan)

    if period <= 0:
        return upper, middle, lower, bandwidth, percent_b

    for i in range(period - 1, n):
        window = prices[i - period + 1: i + 1]
        std = np.std(window, ddof=0)
        m = middle[i]
        u = m + std_dev_multiplier * std
        l = m - std_dev_multiplier * std
        upper[i] = u
        lower[i] = l
        if m != 0:
            bandwidth[i] = (u - l) / m
        percent_b[i] = (prices[i] - l) / (u - l) if (u - l) != 0 else 0.5

    return upper, middle, lower, bandwidth, percent_b


def calculate_stoch_rsi(
    rsi_arr: np.ndarray,
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Stochastic RSI: converts RSI into a bounded 0-100 oscillator.
    %K = (RSI - Min(RSI, period)) / (Max(RSI, period) - Min(RSI, period)) * 100
    %D = SMA(%K, smooth_d)
    """
    n = len(rsi_arr)
    stoch_k = np.full(n, np.nan)
    stoch_d = np.full(n, np.nan)

    for i in range(period - 1, n):
        window = rsi_arr[i - period + 1: i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) < period:
            continue
        rsi_min = np.min(valid)
        rsi_max = np.max(valid)
        denom = rsi_max - rsi_min
        if denom == 0:
            stoch_k[i] = 50.0
        else:
            stoch_k[i] = (rsi_arr[i] - rsi_min) / denom * 100.0

    # Smooth %K
    smoothed_k = np.full(n, np.nan)
    for i in range(smooth_k - 1, n):
        window = stoch_k[i - smooth_k + 1: i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) == smooth_k:
            smoothed_k[i] = np.mean(valid)

    # %D is SMA of smoothed %K
    for i in range(smooth_d - 1, n):
        window = smoothed_k[i - smooth_d + 1: i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) == smooth_d:
            stoch_d[i] = np.mean(valid)

    return smoothed_k, stoch_d


def calculate_atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Average True Range (ATR) — measures market volatility.
    True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    """
    n = len(closes)
    atr = np.full(n, np.nan)
    if n < 2:
        return atr

    tr = np.full(n, np.nan)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hpc, lpc)

    # Wilder smoothed ATR
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def compute_all_indicators(
    candles: List[Dict[str, Any]],
    rsi_period: int = 9,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    sma_period: int = 20,
    ema_period: int = 50,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> Dict[str, Any]:
    """
    Computes all indicators including new Stochastic RSI and ATR.
    """
    if not candles:
        return {}

    closes = np.array([c["close"] for c in candles], dtype=float)
    highs = np.array([c["high"] for c in candles], dtype=float)
    lows = np.array([c["low"] for c in candles], dtype=float)
    volumes = np.array([c.get("volume", 0.0) for c in candles], dtype=float)
    times = [c["time"] for c in candles]

    # Core indicators
    rsi = calculate_rsi(closes, period=rsi_period)
    macd, macd_sig, macd_hist = calculate_macd(closes, fast_period=macd_fast, slow_period=macd_slow, signal_period=macd_signal)
    sma = calculate_sma(closes, period=sma_period)
    ema = calculate_ema(closes, period=ema_period)
    ema_21 = calculate_ema(closes, period=21)
    bb_upper, bb_mid, bb_lower, bb_width, bb_pct_b = calculate_bollinger_bands(closes, period=bb_period, std_dev_multiplier=bb_std)

    # New: Stochastic RSI
    stoch_k, stoch_d = calculate_stoch_rsi(rsi, period=14, smooth_k=3, smooth_d=3)

    # New: ATR (volatility filter)
    atr = calculate_atr(highs, lows, closes, period=14)

    # New: Volume SMA (to detect volume spikes)
    vol_sma = calculate_sma(volumes, period=20)

    def fmt(arr: np.ndarray) -> List[Dict]:
        return [{"time": t, "value": round(float(v), 4)} for t, v in zip(times, arr) if not np.isnan(v)]

    def fmt_hist(arr: np.ndarray) -> List[Dict]:
        return [
            {"time": t, "value": round(float(v), 4), "color": "#26a69a" if v >= 0 else "#ef5350"}
            for t, v in zip(times, arr) if not np.isnan(v)
        ]

    def to_raw(arr: np.ndarray) -> List:
        return [None if np.isnan(v) else float(v) for v in arr]

    return {
        "rsi": fmt(rsi),
        "macd": {
            "macd": fmt(macd),
            "signal": fmt(macd_sig),
            "histogram": fmt_hist(macd_hist),
        },
        "sma": fmt(sma),
        "ema": fmt(ema),
        "bollinger": {
            "upper": fmt(bb_upper),
            "middle": fmt(bb_mid),
            "lower": fmt(bb_lower),
        },
        "stoch_rsi": {
            "k": fmt(stoch_k),
            "d": fmt(stoch_d),
        },
        "atr": fmt(atr),
        "raw": {
            "times": times,
            "closes": closes.tolist(),
            "highs": highs.tolist(),
            "lows": lows.tolist(),
            "volumes": volumes.tolist(),
            "rsi": to_raw(rsi),
            "macd": to_raw(macd),
            "macd_signal": to_raw(macd_sig),
            "macd_hist": to_raw(macd_hist),
            "sma": to_raw(sma),
            "ema": to_raw(ema),
            "ema_21": to_raw(ema_21),
            "bb_upper": to_raw(bb_upper),
            "bb_middle": to_raw(bb_mid),
            "bb_lower": to_raw(bb_lower),
            "bb_width": to_raw(bb_width),
            "bb_pct_b": to_raw(bb_pct_b),
            "stoch_k": to_raw(stoch_k),
            "stoch_d": to_raw(stoch_d),
            "atr": to_raw(atr),
            "vol_sma": to_raw(vol_sma),
        }
    }
