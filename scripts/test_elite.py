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

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def test_elite():
    print("=" * 95)
    print("ELITE CONFLUENCE AUDIT (CONFIDENCE >= 85%)")
    print("=" * 95)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<11} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 95)

    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_profit = 0.0

    for sym in PAIRS:
        for tf in ["1m", "5m"]:
            candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=1000)
            ind_data = compute_all_indicators(candles, rsi_period=7, bb_period=20, bb_std=2.2)
            raw = generate_all_signals(candles, ind_data, rsi_oversold=25.0, rsi_overbought=75.0)["history"]

            # Filter for elite setups (>= 85%)
            elite_sigs = []
            for s in raw:
                if s.get("confidence", 0) >= 85.0:
                    elite_sigs.append(s)
                else:
                    elite_sigs.append({"signal": "NEUTRAL", "confidence": 0, "time": s.get("time", 0)})

            bt = run_backtest(candles, elite_sigs, timeframe=tf, expiry_duration="5min", payout_rate=0.85, stake_amount=10.0)
            s = bt["summary"]

            if s["total_trades"] > 0:
                tot_trades += s["total_trades"]
                tot_wins += s["wins"]
                tot_losses += s["losses"]
                tot_profit += s["total_profit"]
                print(f"{sym:<10} | {tf:<4} | 5min   | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10}% | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 95)
    overall_wr = round((tot_wins / (tot_wins + tot_losses) * 100), 2) if (tot_wins + tot_losses) > 0 else 0
    print(f"🎯 ELITE CONFLUENCE SUMMARY:")
    print(f"   • Total Trades  : {tot_trades}")
    print(f"   • Total Wins    : {tot_wins}")
    print(f"   • Total Losses  : {tot_losses}")
    print(f"   • Final Win Rate: {overall_wr}%")
    print(f"   • Net Profit    : ${tot_profit:+.2f}")
    print("=" * 95)

if __name__ == "__main__":
    test_elite()
