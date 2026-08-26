import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals
from app.services.backtester import run_backtest

def main():
    print("=" * 95)
    print("HIGH-CONFIDENCE FILTER ACCURACY AUDIT (SIGNALS WITH >= 75% CONFIDENCE)")
    print("=" * 95)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<11} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 95)

    configs = [
        {"symbol": "BTCUSDT", "timeframe": "1m", "expiry": "5min"},
        {"symbol": "BTCUSDT", "timeframe": "5m", "expiry": "5min"},
        {"symbol": "ETHUSDT", "timeframe": "5m", "expiry": "5min"},
        {"symbol": "SOLUSDT", "timeframe": "1m", "expiry": "5min"},
    ]

    total_signals = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for cfg in configs:
        symbol = cfg["symbol"]
        tf = cfg["timeframe"]
        expiry = cfg["expiry"]

        candles, source = fetch_ohlcv_with_source(symbol=symbol, interval=tf, limit=1000)
        ind_data = compute_all_indicators(candles)
        raw_signals = generate_all_signals(candles, ind_data)["history"]

        # Filter only high-confidence confluence signals (>= 75%)
        filtered_signals = []
        for s in raw_signals:
            if s.get("confidence", 0) >= 75.0:
                filtered_signals.append(s)
            else:
                filtered_signals.append({"signal": "NEUTRAL", "confidence": 0, "time": s.get("time", 0)})

        bt = run_backtest(
            candles=candles,
            signals=filtered_signals,
            timeframe=tf,
            expiry_duration=expiry,
            payout_rate=0.85,
            stake_amount=10.0,
        )

        s = bt["summary"]
        total_signals += s["total_trades"]
        total_wins += s["wins"]
        total_losses += s["losses"]
        total_profit += s["total_profit"]

        print(f"{symbol:<10} | {tf:<4} | {expiry:<6} | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10}% | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 95)
    overall_winrate = round((total_wins / (total_wins + total_losses) * 100), 2) if (total_wins + total_losses) > 0 else 0
    print(f"HIGH-CONFIDENCE SUMMARY:")
    print(f"   * Total High-Quality Trades : {total_signals}")
    print(f"   * Total Wins                : {total_wins}")
    print(f"   * Total Losses              : {total_losses}")
    print(f"   * Win Rate                  : {overall_winrate}%")
    print(f"   * Net Profit ($10 stake)    : ${total_profit:+.2f}")
    print("=" * 95)

if __name__ == "__main__":
    main()
