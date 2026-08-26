import sys
import os
import time
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "http://127.0.0.1:5000"

WATCHLIST = [
    # Major Forex Pairs
    {"symbol": "EURUSD", "market": "Forex", "name": "EUR / USD"},
    {"symbol": "GBPUSD", "market": "Forex", "name": "GBP / USD"},
    {"symbol": "USDJPY", "market": "Forex", "name": "USD / JPY"},
    {"symbol": "AUDUSD", "market": "Forex", "name": "AUD / USD"},
    {"symbol": "USDCAD", "market": "Forex", "name": "USD / CAD"},
    {"symbol": "EURGBP", "market": "Forex", "name": "EUR / GBP"},
    {"symbol": "GBPJPY", "market": "Forex", "name": "GBP / JPY"},
    # Commodities & Indices
    {"symbol": "GOLD",   "market": "Commodity", "name": "Gold (XAU / USD)"},
    {"symbol": "SPX",    "market": "Index",     "name": "S&P 500 Index"},
    # Top Crypto Pairs
    {"symbol": "BTCUSDT", "market": "Crypto",   "name": "BTC / USDT"},
    {"symbol": "ETHUSDT", "market": "Crypto",   "name": "ETH / USDT"},
    {"symbol": "SOLUSDT", "market": "Crypto",   "name": "SOL / USDT"},
]

def scan_and_trade():
    print("=" * 105)
    print("⚡ QUANTUM BINARY TRADINGVIEW AUTO-SCANNER ACTIVE")
    print(f"Server Target: {API_BASE} | Web Terminal: http://localhost:5000")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 105)
    print(f"{'Asset':<22} | {'Market':<12} | {'Live Price':<14} | {'Signal':<10} | {'Conf %':<8} | {'Status'}")
    print("-" * 105)

    signals_found = 0

    for item in WATCHLIST:
        sym = item["symbol"]
        market = item["market"]
        name = item["name"]

        try:
            url = f"{API_BASE}/api/market-data?symbol={sym}&interval=1m&limit=100"
            res = requests.get(url, timeout=5)
            if res.status_code != 200:
                continue

            data = res.json()
            candles = data.get("candles", [])
            if not candles:
                continue

            price = candles[-1]["close"]
            sig = data.get("signal", {})
            signal_type = sig.get("signal", "NEUTRAL")
            conf = sig.get("confidence", 0)

            digits = 5 if price < 5 else 2
            price_str = f"${price:.{digits}f}"

            if signal_type in ("CALL", "PUT") and conf >= 65.0:
                signals_found += 1
                status = f"🔥 EXECUTING {signal_type} @ {price_str}"
                print(f"{name:<22} | {market:<12} | {price_str:<14} | {signal_type:<10} | {conf:<7.1f}% | {status}")

                # Automatically record / execute trade in journal
                trade_payload = {
                    "symbol": sym,
                    "signal": signal_type,
                    "entry_price": float(price),
                    "duration_seconds": 300, # 5 min trade time
                    "stake": 10.0,
                    "payout_rate": 0.85,
                    "timeframe": "1m",
                }
                requests.post(f"{API_BASE}/api/trades", json=trade_payload, timeout=5)
            else:
                status = "Monitoring (Confluence filtering)"
                print(f"{name:<22} | {market:<12} | {price_str:<14} | {signal_type:<10} | {conf:<7.1f}% | {status}")

        except Exception as e:
            print(f"{name:<22} | {market:<12} | Error: {e}")

    print("=" * 105)
    print(f"Scan complete. Found {signals_found} actionable setups. Web terminal is live at http://localhost:5000")
    print("=" * 105)

if __name__ == "__main__":
    scan_and_trade()
