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

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
TIMEFRAMES = [("1m", "5min"), ("5m", "5min")]

def run_live_test():
    print("=" * 105)
    print("LIVE REAL-TIME BINANCE ACCURACY & WIN PERCENTAGE REPORT")
    print(f"Executed at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 105)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Live Price':<12} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<12} | {'High-Conf Win %':<16} | {'Net PnL ($10)':<13}")
    print("-" * 105)

    grand_total_trades = 0
    grand_total_wins = 0
    grand_total_losses = 0
    grand_total_profit = 0.0

    high_conf_wins = 0
    high_conf_losses = 0

    for symbol in PAIRS:
        for tf, exp in TIMEFRAMES:
            candles, source = fetch_ohlcv_with_source(symbol=symbol, interval=tf, limit=1000)
            if not candles:
                continue

            current_price = candles[-1]["close"]

            ind_data = compute_all_indicators(candles, rsi_period=11, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0)
            signals_res = generate_all_signals(candles, ind_data, rsi_oversold=28.0, rsi_overbought=72.0)
            all_signals = signals_res["history"]

            # 1. Standard Backtest
            bt = run_backtest(candles, all_signals, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
            s = bt["summary"]

            # 2. High-Confidence Filter (>= 75% confidence)
            filtered_sigs = []
            for sig in all_signals:
                if sig.get("confidence", 0) >= 75.0:
                    filtered_sigs.append(sig)
                else:
                    filtered_sigs.append({"signal": "NEUTRAL", "confidence": 0, "time": sig.get("time", 0)})

            bt_hc = run_backtest(candles, filtered_sigs, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
            hc_s = bt_hc["summary"]

            grand_total_trades += s["total_trades"]
            grand_total_wins += s["wins"]
            grand_total_losses += s["losses"]
            grand_total_profit += s["total_profit"]

            high_conf_wins += hc_s["wins"]
            high_conf_losses += hc_s["losses"]

            hc_wr_str = f"{hc_s['win_rate']:.1f}% ({hc_s['wins']}W/{hc_s['losses']}L)" if (hc_s["wins"] + hc_s["losses"]) > 0 else "N/A"

            print(f"{symbol:<10} | {tf:<4} | {exp:<6} | ${current_price:<11.2f} | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10.2f}% | {hc_wr_str:<16} | ${s['total_profit']:<+11.2f}")

    print("=" * 105)
    overall_winrate = round((grand_total_wins / (grand_total_wins + grand_total_losses) * 100), 2) if (grand_total_wins + grand_total_losses) > 0 else 0
    hc_overall_winrate = round((high_conf_wins / (high_conf_wins + high_conf_losses) * 100), 2) if (high_conf_wins + high_conf_losses) > 0 else 0

    print(f"📊 AGGREGATE SUMMARY (ACROSS ALL {len(PAIRS) * len(TIMEFRAMES)} LIVE ASSET CONFIGS / 1,000 CANDLES EACH):")
    print(f"   • Total Standard Signals Evaluated : {grand_total_trades}")
    print(f"   • Total Standard Wins / Losses     : {grand_total_wins} Wins / {grand_total_losses} Losses")
    print(f"   • Overall Standard Win Percentage  : {overall_winrate}%")
    print(f"   • Overall HIGH-CONFIDENCE Win Rate : {hc_overall_winrate}% ({high_conf_wins} Wins / {high_conf_losses} Losses)")
    print(f"   • Aggregate Net PnL ($10 stake)    : ${grand_total_profit:+.2f}")
    print("=" * 105)

if __name__ == "__main__":
    run_live_test()
