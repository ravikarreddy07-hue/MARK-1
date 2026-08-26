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

CONFIGS = [
    ("BTCUSDT", "1m", "5min"),
    ("BTCUSDT", "5m", "5min"),
    ("ETHUSDT", "1m", "5min"),
    ("ETHUSDT", "5m", "5min"),
    ("BNBUSDT", "1m", "5min"),
    ("BNBUSDT", "5m", "5min"),
    ("SOLUSDT", "1m", "5min"),
]

def main():
    print("=" * 110)
    print("V3 PRECISION ENGINE — LIVE BINANCE ACCURACY REPORT")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 110)
    hdr = (f"{'Pair':<10} | {'TF':<4} | {'Exp':<6} | {'Live $':<12} | "
           f"{'Signals':<8} | {'Wins':<5} | {'Loss':<5} | {'Win %':<8} | "
           f"{'PF':<6} | {'Net PnL ($10)'}")
    print(hdr)
    print("-" * 110)

    tot_t = tot_w = tot_l = 0
    tot_pnl = 0.0

    for sym, tf, exp in CONFIGS:
        candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=1000)
        if not candles:
            continue

        price = candles[-1]["close"]
        ind   = compute_all_indicators(candles, rsi_period=9, macd_fast=12,
                                        macd_slow=26, macd_signal=9,
                                        bb_period=20, bb_std=2.0, ema_period=50)
        sigs  = generate_all_signals(candles, ind, rsi_oversold=28.0, rsi_overbought=72.0)["history"]
        bt    = run_backtest(candles, sigs, timeframe=tf, expiry_duration=exp,
                             payout_rate=0.85, stake_amount=10.0)
        s     = bt["summary"]

        tot_t   += s["total_trades"]
        tot_w   += s["wins"]
        tot_l   += s["losses"]
        tot_pnl += s["total_profit"]

        row = (f"{sym:<10} | {tf:<4} | {exp:<6} | ${price:<11.2f} | "
               f"{s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<5} | "
               f"{s['win_rate']:<7.2f}% | {s['profit_factor']:<6} | ${s['total_profit']:+.2f}")
        print(row)

    print("=" * 110)
    wr = round(tot_w / (tot_w + tot_l) * 100, 2) if (tot_w + tot_l) > 0 else 0
    print(f"AGGREGATE V3 RESULTS  |  Trades: {tot_t}  |  Wins: {tot_w}  |  Losses: {tot_l}")
    print(f"OVERALL WIN RATE      :  {wr}%")
    print(f"NET PROFIT ($10 stake):  ${tot_pnl:+.2f}")
    print("=" * 110)

if __name__ == "__main__":
    main()
