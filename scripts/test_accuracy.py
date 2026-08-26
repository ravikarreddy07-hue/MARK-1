import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals
from app.services.backtester import run_backtest

TEST_CONFIGS = [
    {"symbol": "BTCUSDT", "timeframe": "1m", "expiry": "5min", "limit": 1000},
    {"symbol": "BTCUSDT", "timeframe": "5m", "expiry": "5min", "limit": 1000},
    {"symbol": "BTCUSDT", "timeframe": "15m", "expiry": "15min", "limit": 1000},
    {"symbol": "ETHUSDT", "timeframe": "1m", "expiry": "5min", "limit": 1000},
    {"symbol": "ETHUSDT", "timeframe": "5m", "expiry": "5min", "limit": 1000},
    {"symbol": "SOLUSDT", "timeframe": "1m", "expiry": "5min", "limit": 1000},
    {"symbol": "SOLUSDT", "timeframe": "5m", "expiry": "5min", "limit": 1000},
    {"symbol": "BNBUSDT", "timeframe": "5m", "expiry": "5min", "limit": 1000},
]

def main():
    print("=" * 95)
    print("QUANTUM BINARY - HISTORICAL & LIVE ACCURACY AUDIT (BINANCE REAL DATA)")
    print("=" * 95)
    print(f"{'Pair':<10} | {'TF':<4} | {'Expiry':<6} | {'Source':<9} | {'Signals':<8} | {'Wins':<5} | {'Losses':<6} | {'Win Rate %':<11} | {'Profit Factor':<13} | {'Net PnL ($10)':<12}")
    print("-" * 95)

    total_signals = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for cfg in TEST_CONFIGS:
        symbol = cfg["symbol"]
        tf = cfg["timeframe"]
        expiry = cfg["expiry"]
        limit = cfg["limit"]

        candles, source = fetch_ohlcv_with_source(symbol=symbol, interval=tf, limit=limit)
        if not candles:
            print(f"{symbol:<10} | {tf:<4} | {expiry:<6} | FAILED TO FETCH DATA")
            continue

        ind_data = compute_all_indicators(candles)
        signals = generate_all_signals(candles, ind_data)
        
        bt = run_backtest(
            candles=candles,
            signals=signals.get("history", []),
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

        print(f"{symbol:<10} | {tf:<4} | {expiry:<6} | {source:<9} | {s['total_trades']:<8} | {s['wins']:<5} | {s['losses']:<6} | {s['win_rate']:<10}% | {s['profit_factor']:<13} | ${s['total_profit']:<+11.2f}")

    print("=" * 95)
    overall_winrate = round((total_wins / (total_wins + total_losses) * 100), 2) if (total_wins + total_losses) > 0 else 0
    print(f"AGGREGATE SUMMARY ACROSS {len(TEST_CONFIGS)} CONFIGURATIONS (1,000 CANDLES EACH):")
    print(f"   * Total Trades Evaluated : {total_signals}")
    print(f"   * Total Wins             : {total_wins}")
    print(f"   * Total Losses           : {total_losses}")
    print(f"   * Overall Win Rate       : {overall_winrate}%")
    print(f"   * Aggregate Net Profit   : ${total_profit:+.2f} (based on $10 flat stake)")
    print("=" * 95)

if __name__ == "__main__":
    main()
