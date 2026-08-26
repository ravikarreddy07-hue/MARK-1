import sys
import os
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals
from app.services.backtester import run_backtest

PAIRS_CONFIG = [
    {"symbol": "BTCUSDT", "tf": "1m", "exp": "5min"},
    {"symbol": "BTCUSDT", "tf": "5m", "exp": "5min"},
    {"symbol": "ETHUSDT", "tf": "5m", "exp": "5min"},
    {"symbol": "SOLUSDT", "tf": "1m", "exp": "5min"},
    {"symbol": "BNBUSDT", "tf": "1m", "exp": "5min"},
    {"symbol": "BNBUSDT", "tf": "5m", "exp": "5min"},
]

def main():
    print("=" * 105)
    print("UPGRADED HIGH-PRECISION STRATEGY - LIVE BINANCE ACCURACY & WIN PERCENTAGE AUDIT")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 105)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Live Price':<12} | {'High-Conf Signals':<18} | {'High-Conf Win %':<17} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 105)

    total_hc_trades = 0
    total_hc_wins = 0
    total_hc_losses = 0
    total_hc_profit = 0.0

    for cfg in PAIRS_CONFIG:
        sym = cfg["symbol"]
        tf = cfg["tf"]
        exp = cfg["exp"]

        candles, source = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=1000)
        if not candles:
            continue

        live_price = candles[-1]["close"]
        ind_data = compute_all_indicators(candles, rsi_period=9, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0)
        raw_signals = generate_all_signals(candles, ind_data, rsi_oversold=28.0, rsi_overbought=72.0)["history"]

        # Filter High-Confidence (>= 75% score)
        hc_signals = []
        for s in raw_signals:
            if s.get("confidence", 0) >= 75.0:
                hc_signals.append(s)
            else:
                hc_signals.append({"signal": "NEUTRAL", "confidence": 0, "time": s.get("time", 0)})

        bt = run_backtest(candles, hc_signals, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
        s = bt["summary"]

        total_hc_trades += s["total_trades"]
        total_hc_wins += s["wins"]
        total_hc_losses += s["losses"]
        total_hc_profit += s["total_profit"]

        wr_str = f"{s['win_rate']:.2f}% ({s['wins']}W / {s['losses']}L)"

        print(f"{sym:<10} | {tf:<4} | {exp:<6} | ${live_price:<11.2f} | {s['total_trades']:<18} | {wr_str:<17} | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 105)
    overall_wr = round((total_hc_wins / (total_hc_wins + total_hc_losses) * 100), 2) if (total_hc_wins + total_hc_losses) > 0 else 0
    print(f"🎯 AGGREGATE HIGH-CONFIDENCE WIN METRICS (1,000 CANDLES EACH):")
    print(f"   • Total High-Probability Setups : {total_hc_trades}")
    print(f"   • Total Wins                     : {total_hc_wins}")
    print(f"   • Total Losses                   : {total_hc_losses}")
    print(f"   • Aggregate Win Percentage       : {overall_wr}%")
    print(f"   • Net Profit ($10 flat stake)    : ${total_hc_profit:+.2f}")
    print("=" * 105)

if __name__ == "__main__":
    main()
