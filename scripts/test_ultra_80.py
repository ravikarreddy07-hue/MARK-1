import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.backtester import run_backtest

def evaluate_ultra_80_signal(idx, candles, raw_ind):
    if idx < 3 or idx >= len(candles):
        return {"signal": "NEUTRAL", "confidence": 0, "time": candles[idx]["time"] if idx < len(candles) else 0}

    c = candles[idx]
    prev1 = candles[idx - 1]
    prev2 = candles[idx - 2]

    close_p = c["close"]
    open_p = c["open"]
    high_p = c["high"]
    low_p = c["low"]

    rsi = raw_ind["rsi"][idx]
    prev_rsi = raw_ind["rsi"][idx - 1]
    bbu = raw_ind["bb_upper"][idx]
    bbl = raw_ind["bb_lower"][idx]
    ema = raw_ind["ema"][idx]
    sma = raw_ind["sma"][idx]
    macd = raw_ind["macd"][idx]
    macd_sig = raw_ind["macd_signal"][idx]

    if rsi is None or bbu is None or bbl is None or ema is None:
        return {"signal": "NEUTRAL", "confidence": 0, "time": c["time"]}

    candle_range = max(high_p - low_p, 0.0001)
    lower_wick = min(open_p, close_p) - low_p
    upper_wick = high_p - max(open_p, close_p)

    # 1. ULTRA CALL (BUY) SETUP:
    # - Extreme oversold (RSI <= 26 or crossing above 26)
    # - Low touched or pierced 2.2-2.5 std dev Lower Bollinger Band
    # - Bullish pinbar / wick rejection (lower wick >= 35% of range) OR bullish close above open
    # - Price above or near 50 EMA (uptrend pullback)
    is_oversold = rsi <= 26.0 or (prev_rsi <= 25.0 and rsi > prev_rsi)
    is_lower_bb_touch = low_p <= bbl or prev1["low"] <= raw_ind["bb_lower"][idx - 1]
    is_bullish_reaction = close_p > open_p or (lower_wick / candle_range >= 0.35)
    is_trend_aligned_call = close_p >= ema * 0.995

    if is_oversold and is_lower_bb_touch and is_bullish_reaction and is_trend_aligned_call:
        return {
            "signal": "CALL",
            "confidence": 88.5,
            "score": 9.2,
            "entry_price": close_p,
            "time": c["time"],
            "reasons": [
                f"Ultra 80%: RSI extreme oversold hook ({rsi:.1f})",
                f"Ultra 80%: Pierced & rejected Lower Bollinger Band ({bbl:.2f})",
                "Ultra 80%: Bullish pinbar / reversal candle confirmation",
                "Ultra 80%: Trendline support alignment",
            ]
        }

    # 2. ULTRA PUT (SELL) SETUP:
    # - Extreme overbought (RSI >= 74 or crossing below 74)
    # - High touched or pierced 2.2-2.5 std dev Upper Bollinger Band
    # - Bearish pinbar / wick rejection (upper wick >= 35% of range) OR bearish close below open
    # - Price below or near 50 EMA (downtrend pullback)
    is_overbought = rsi >= 74.0 or (prev_rsi >= 75.0 and rsi < prev_rsi)
    is_upper_bb_touch = high_p >= bbu or prev1["high"] >= raw_ind["bb_upper"][idx - 1]
    is_bearish_reaction = close_p < open_p or (upper_wick / candle_range >= 0.35)
    is_trend_aligned_put = close_p <= ema * 1.005

    if is_overbought and is_upper_bb_touch and is_bearish_reaction and is_trend_aligned_put:
        return {
            "signal": "PUT",
            "confidence": 88.5,
            "score": 9.2,
            "entry_price": close_p,
            "time": c["time"],
            "reasons": [
                f"Ultra 80%: RSI extreme overbought hook ({rsi:.1f})",
                f"Ultra 80%: Pierced & rejected Upper Bollinger Band ({bbu:.2f})",
                "Ultra 80%: Bearish pinbar / reversal candle confirmation",
                "Ultra 80%: Resistance alignment",
            ]
        }

    return {"signal": "NEUTRAL", "confidence": 0, "time": c["time"]}

def test_ultra():
    configs = [
        ("BTCUSDT", "1m", "5min"),
        ("BTCUSDT", "1m", "3min"),
        ("BTCUSDT", "5m", "15min"),
        ("ETHUSDT", "1m", "5min"),
        ("SOLUSDT", "1m", "5min"),
        ("BNBUSDT", "1m", "5min"),
    ]

    print("=" * 95)
    print("ULTRA 80% WIN-RATE STRATEGY VERIFICATION (BINANCE LIVE HISTORICAL DATA)")
    print("=" * 95)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<11} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 95)

    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_profit = 0.0

    for sym, tf, exp in configs:
        candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=1000)
        ind = compute_all_indicators(candles, rsi_period=9, bb_period=20, bb_std=2.2, ema_period=50)

        sigs = [evaluate_ultra_80_signal(i, candles, ind["raw"]) for i in range(len(candles))]
        bt = run_backtest(candles, sigs, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
        s = bt["summary"]

        tot_trades += s["total_trades"]
        tot_wins += s["wins"]
        tot_losses += s["losses"]
        tot_profit += s["total_profit"]

        print(f"{sym:<10} | {tf:<4} | {exp:<6} | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10}% | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 95)
    overall_wr = round((tot_wins / (tot_wins + tot_losses) * 100), 2) if (tot_wins + tot_losses) > 0 else 0
    print(f"📊 OVERALL ULTRA STRATEGY RESULTS:")
    print(f"   • Total Trades  : {tot_trades}")
    print(f"   • Total Wins    : {tot_wins}")
    print(f"   • Total Losses  : {tot_losses}")
    print(f"   • Final Win Rate: {overall_wr}%")
    print(f"   • Net Profit    : ${tot_profit:+.2f}")
    print("=" * 95)

if __name__ == "__main__":
    test_ultra()
