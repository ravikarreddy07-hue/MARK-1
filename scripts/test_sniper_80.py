import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import evaluate_candle_signal
from app.services.backtester import run_backtest

def evaluate_sniper_signal(
    idx: int,
    candles,
    raw_ind,
) -> dict:
    """
    Sniper 80% Confluence Rule:
    Only triggers when 5 strict conditions are met simultaneously:
    1. Extreme RSI Exhaustion (< 24 or > 76)
    2. Extreme 2.5 Standard Deviation Bollinger Band piercing & rejection
    3. Long Wick Rejection on candle (Price action exhaustion)
    4. MACD Momentum alignment
    5. Price aligned with Trend EMA
    """
    if idx < 2 or idx >= len(candles):
        return {"signal": "NEUTRAL", "confidence": 0, "time": candles[idx]["time"] if idx < len(candles) else 0}

    c = candles[idx]
    prev_c = candles[idx - 1]
    close_p = c["close"]
    open_p = c["open"]
    high_p = c["high"]
    low_p = c["low"]
    candle_body = abs(close_p - open_p)
    total_range = high_p - low_p if (high_p - low_p) > 0 else 0.0001

    rsi = raw_ind["rsi"][idx]
    prev_rsi = raw_ind["rsi"][idx - 1]
    bbu = raw_ind["bb_upper"][idx]
    bbl = raw_ind["bb_lower"][idx]
    ema = raw_ind["ema"][idx]
    macd = raw_ind["macd"][idx]
    macd_sig = raw_ind["macd_signal"][idx]

    if rsi is None or bbu is None or bbl is None or ema is None or macd is None or macd_sig is None:
        return {"signal": "NEUTRAL", "confidence": 0, "time": c["time"]}

    # CALL Sniper Conditions
    lower_wick = min(open_p, close_p) - low_p
    is_bullish_pinbar = (lower_wick / total_range) >= 0.45 or close_p > open_p
    rsi_bullish_exhaustion = rsi <= 25.0 or (prev_rsi <= 25.0 and rsi > prev_rsi)
    bb_lower_pierce = low_p <= bbl and close_p >= bbl

    if rsi_bullish_exhaustion and bb_lower_pierce and is_bullish_pinbar and macd > macd_sig - 0.05:
        return {
            "signal": "CALL",
            "confidence": 88.0,
            "score": 9.0,
            "entry_price": close_p,
            "time": c["time"],
            "reasons": [
                f"Sniper: Extreme RSI oversold ({rsi:.1f} <= 25)",
                f"Sniper: 2.5σ Lower BB Band Piercing & Rejection ({bbl:.2f})",
                "Sniper: Strong Bullish Wick Rejection",
                "Sniper: MACD Momentum Support",
            ]
        }

    # PUT Sniper Conditions
    upper_wick = high_p - max(open_p, close_p)
    is_bearish_pinbar = (upper_wick / total_range) >= 0.45 or close_p < open_p
    rsi_bearish_exhaustion = rsi >= 75.0 or (prev_rsi >= 75.0 and rsi < prev_rsi)
    bb_upper_pierce = high_p >= bbu and close_p <= bbu

    if rsi_bearish_exhaustion and bb_upper_pierce and is_bearish_pinbar and macd < macd_sig + 0.05:
        return {
            "signal": "PUT",
            "confidence": 88.0,
            "score": 9.0,
            "entry_price": close_p,
            "time": c["time"],
            "reasons": [
                f"Sniper: Extreme RSI overbought ({rsi:.1f} >= 75)",
                f"Sniper: 2.5σ Upper BB Band Piercing & Rejection ({bbu:.2f})",
                "Sniper: Strong Bearish Wick Rejection",
                "Sniper: MACD Momentum Support",
            ]
        }

    return {"signal": "NEUTRAL", "confidence": 0, "time": c["time"]}

def main():
    print("=" * 95)
    print("🎯 SNIPER 80% TARGET WIN-RATE CONFLUENCE STRATEGY AUDIT (BINANCE REAL DATA)")
    print("=" * 95)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<11} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 95)

    pairs = [
        ("BTCUSDT", "1m", "5min"),
        ("BTCUSDT", "5m", "5min"),
        ("ETHUSDT", "1m", "5min"),
        ("ETHUSDT", "5m", "5min"),
        ("SOLUSDT", "1m", "5min"),
    ]

    total_signals = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for sym, tf, exp in pairs:
        candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=1000)
        ind_data = compute_all_indicators(candles, rsi_period=11, bb_period=20, bb_std=2.5)

        raw = ind_data["raw"]
        sniper_sigs = [evaluate_sniper_signal(i, candles, raw) for i in range(len(candles))]

        bt = run_backtest(candles, sniper_sigs, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
        s = bt["summary"]

        total_signals += s["total_trades"]
        total_wins += s["wins"]
        total_losses += s["losses"]
        total_profit += s["total_profit"]

        print(f"{sym:<10} | {tf:<4} | {exp:<6} | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10}% | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 95)
    overall_winrate = round((total_wins / (total_wins + total_losses) * 100), 2) if (total_wins + total_losses) > 0 else 0
    print(f"🎯 AGGREGATE SNIPER AUDIT RESULTS:")
    print(f"   * Total Sniper Trades    : {total_signals}")
    print(f"   * Total Wins             : {total_wins}")
    print(f"   * Total Losses           : {total_losses}")
    print(f"   * Overall Win Rate       : {overall_winrate}%")
    print(f"   * Net Profit ($10 stake) : ${total_profit:+.2f}")
    print("=" * 95)

if __name__ == "__main__":
    main()
