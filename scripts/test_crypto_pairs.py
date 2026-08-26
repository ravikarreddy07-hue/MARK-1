import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals

test_pairs = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "PEPEUSDT",
    "SHIBUSDT",
    "DOTUSDT",
    "LTCUSDT",
]

def main():
    print("=" * 95)
    print("MULTI-CRYPTO PAIR LIVE SIGNAL TEST (BINANCE REAL DATA)")
    print("=" * 95)
    print(f"{'Pair':<12} | {'Source':<14} | {'Candles':<8} | {'Live Price':<16} | {'Signal':<10} | {'Confidence':<10}")
    print("-" * 95)

    for sym in test_pairs:
        candles, src = fetch_ohlcv_with_source(symbol=sym, interval="1m", limit=100)
        ind = compute_all_indicators(candles)
        sigs = generate_all_signals(candles, ind)
        curr = sigs.get("current", {})
        price = candles[-1]["close"] if candles else 0.0
        sig_text = curr.get("signal", "NEUTRAL")
        conf = curr.get("confidence", 0)

        price_str = f"${price:.8f}" if price < 0.01 else f"${price:.4f}" if price < 10 else f"${price:.2f}"
        print(f"{sym:<12} | {src:<14} | {len(candles):<8} | {price_str:<16} | {sig_text:<10} | {conf:.1f}%")

    print("=" * 95)

if __name__ == "__main__":
    main()
