import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.backtester import run_backtest

def evaluate_sniper_calibrated(idx, candles, raw_ind):
    if idx < 2 or idx >= len(candles):
        return {"signal": "NEUTRAL", "confidence": 0, "time": candles[idx]["time"] if idx < len(candles) else 0}

    c = candles[idx]
    prev_c = candles[idx - 1]
    close_p = c["close"]
    open_p = c["open"]
    high_p = c["high"]
    low_p = c["low"]

    rsi = raw_ind["rsi"][idx]
    prev_rsi = raw_ind["rsi"][idx - 1]
    bbu = raw_ind["bb_upper"][idx]
    bbl = raw_ind["bb_lower"][idx]
    ema = raw_ind["ema"][idx]
    macd = raw_ind["macd"][idx]
    macd_sig = raw_ind["macd_signal"][idx]

    if rsi is None or bbu is None or bbl is None or ema is None:
        return {"signal": "NEUTRAL", "confidence": 0, "time": c["time"]}

    # CALL Sniper
    is_rebounding_low = (low_p <= bbl or prev_c["low"] <= raw_ind["bb_lower"][idx-1]) and close_p > open_p
    rsi_oversold = rsi <= 30.0 or (prev_rsi <= 28.0 and rsi > prev_rsi)
    
    if rsi_oversold and is_rebounding_low and close_p > ema * 0.998:
        return {
            "signal": "CALL",
            "confidence": 85.0,
            "score": 8.5,
            "entry_price": close_p,
            "time": c["time"],
            "reasons": [
                f"Sniper: RSI oversold hook ({rsi:.1f} <= 30)",
                f"Sniper: Lower BB Band bounce ({bbl:.2f})",
                "Sniper: Bullish candle close above lower band",
            ]
        }

    # PUT Sniper
    is_rejecting_high = (high_p >= bbu or prev_c["high"] >= raw_ind["bb_upper"][idx-1]) and close_p < open_p
    rsi_overbought = rsi >= 70.0 or (prev_rsi >= 72.0 and rsi < prev_rsi)

    if rsi_overbought and is_rejecting_high and close_p < ema * 1.002:
        return {
            "signal": "PUT",
            "confidence": 85.0,
            "score": 8.5,
            "entry_price": close_p,
            "time": c["time"],
            "reasons": [
                f"Sniper: RSI overbought hook ({rsi:.1f} >= 70)",
                f"Sniper: Upper BB Band rejection ({bbu:.2f})",
                "Sniper: Bearish candle close below upper band",
            ]
        }

    return {"signal": "NEUTRAL", "confidence": 0, "time": c["time"]}

def main():
    print("=" * 95)
    print("🎯 CALIBRATED 80% TARGET CONFLUENCE AUDIT")
    print("=" * 95)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<11} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 95)

    pairs = [
        ("BTCUSDT", "1m", "5min"),
        ("BTCUSDT", "5m", "5min"),
        ("ETHUSDT", "5m", "5min"),
        ("SOLUSDT", "1m", "5min"),
    ]

    total_signals = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for sym, tf, exp in pairs:
        candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=1000)
        ind_data = compute_all_indicators(candles, rsi_period=11, bb_period=20, bb_std=2.2)

        raw = ind_data["raw"]
        sigs = [evaluate_sniper_calibrated(i, candles, raw) for i in range(len(candles))]

        bt = run_backtest(candles, sigs, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
        s = bt["summary"]

        total_signals += s["total_trades"]
        total_wins += s["wins"]
        total_losses += s["losses"]
        total_profit += s["total_profit"]

        print(f"{sym:<10} | {tf:<4} | {exp:<6} | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10}% | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 95)
    overall_winrate = round((total_wins / (total_wins + total_losses) * 100), 2) if (total_wins + total_losses) > 0 else 0
    print(f"🎯 AGGREGATE SUMMARY:")
    print(f"   * Total Trades           : {total_signals}")
    print(f"   * Total Wins             : {total_wins}")
    print(f"   * Total Losses           : {total_losses}")
    print(f"   * Overall Win Rate       : {overall_winrate}%")
    print(f"   * Net Profit ($10 stake) : ${total_profit:+.2f}")
    print("=" * 95)

if __name__ == "__main__":
    main()
