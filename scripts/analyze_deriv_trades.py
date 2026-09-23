import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.deriv_auto_trader import DerivAutoTrader

async def analyze():
    trader = DerivAutoTrader()
    res = await trader.connect("pat_543859a4eafd961283e1449a6efdb8f1a94a407aaed712a0d513261698888f30", "34nZu00szxPcV0FfERyJF")
    if not res.get("success"):
        print("Auth failed")
        return

    pt = await trader._send_request({"profit_table": 1, "description": 1, "limit": 100, "sort": "DESC"})
    txs = pt.get("profit_table", {}).get("transactions", [])

    stats = {}
    dir_stats = {"CALL": {"wins": 0, "losses": 0}, "PUT": {"wins": 0, "losses": 0}}

    for t in txs:
        sc = t.get("shortcode", "")
        parts = sc.split("_")
        sym = "UNKNOWN"
        direction = parts[0] if len(parts) > 0 else "UNKNOWN"

        if len(parts) >= 3 and parts[1] == "R":
            sym = f"R_{parts[2]}"
        elif len(parts) >= 2:
            sym = parts[1]

        pnl = float(t.get("sell_price", 0)) - float(t.get("buy_price", 0))
        is_win = pnl > 0

        if sym not in stats:
            stats[sym] = {"wins": 0, "losses": 0, "pnl": 0.0}

        if is_win:
            stats[sym]["wins"] += 1
            if direction in dir_stats:
                dir_stats[direction]["wins"] += 1
        else:
            stats[sym]["losses"] += 1
            if direction in dir_stats:
                dir_stats[direction]["losses"] += 1

        stats[sym]["pnl"] += pnl

    print("================ EXACT PAIR WIN RATE BREAKDOWN ================")
    print(f"{'Asset':<12} | {'Trades':<7} | {'Wins':<5} | {'Losses':<6} | {'Win Rate':<10} | {'Net PnL':<10}")
    print("-" * 65)

    for k, v in sorted(stats.items(), key=lambda x: (x[1]["wins"] / (x[1]["wins"] + x[1]["losses"]) if (x[1]["wins"] + x[1]["losses"]) > 0 else 0), reverse=True):
        tot = v["wins"] + v["losses"]
        wr = (v["wins"] / tot * 100) if tot > 0 else 0
        print(f"{k:<12} | {tot:<7} | {v['wins']:<5} | {v['losses']:<6} | {wr:6.1f}%   | ${v['pnl']:+6.2f}")

    print("\n================ DIRECTION BREAKDOWN ================")
    for d, v in dir_stats.items():
        tot = v["wins"] + v["losses"]
        wr = (v["wins"] / tot * 100) if tot > 0 else 0
        print(f"{d:<6}: {tot} Trades | {v['wins']}W / {v['losses']}L ({wr:.1f}%)")

if __name__ == "__main__":
    asyncio.run(analyze())
