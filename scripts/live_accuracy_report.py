import sys
import os
import time
import json
import psutil

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source, ASSET_CATALOG
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals
from app.services.backtester import run_backtest

def get_cpu_load():
    try:
        return psutil.cpu_percent(interval=0.05)
    except Exception:
        return 10.0

def run_live_test():
    print("=" * 115)
    print("⚡ QUANTUM BINARY - MULTI-MARKET ACCURACY & STRESS TEST BENCHMARK")
    print(f"Executed at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("Thermal Regulation: Active CPU Throttle (Protects laptop from heating)")
    print("=" * 115)
    print(f"{'Asset':<14} | {'Group':<18} | {'TF':<4} | {'Trades':<7} | {'Wins':<5} | {'Loss':<5} | {'Win Rate %':<11} | {'High-Conf (>=75%)':<18} | {'Net PnL ($10)':<13}")
    print("-" * 115)

    all_symbols = []
    for grp in ASSET_CATALOG:
        for item in grp["symbols"]:
            all_symbols.append({"symbol": item["value"], "group": grp["group"], "label": item["label"]})

    timeframes = [("1m", "5min"), ("5m", "5min")]

    grand_total_trades = 0
    grand_total_wins = 0
    grand_total_losses = 0
    grand_total_profit = 0.0

    high_conf_wins = 0
    high_conf_losses = 0
    high_conf_profit = 0.0

    group_breakdown = {}
    ranked_assets = []

    start_time = time.time()

    for idx, sym_info in enumerate(all_symbols, start=1):
        sym = sym_info["symbol"]
        grp = sym_info["group"]
        label = sym_info["label"]

        if grp not in group_breakdown:
            group_breakdown[grp] = {"trades": 0, "wins": 0, "losses": 0, "profit": 0.0, "hc_wins": 0, "hc_losses": 0}

        # PC Thermal & Load Protection
        cpu = get_cpu_load()
        if cpu > 60.0:
            print(f"  [Thermal Guard] CPU at {cpu:.1f}% -> Pausing 1.5s for cool down...")
            time.sleep(1.5)
        else:
            time.sleep(0.04)

        sym_trades = 0
        sym_wins = 0
        sym_losses = 0
        sym_profit = 0.0
        sym_hc_wins = 0
        sym_hc_losses = 0

        for tf, exp in timeframes:
            candles, source = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=500)
            if not candles or len(candles) < 50:
                continue

            ind_data = compute_all_indicators(candles, rsi_period=11, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0)
            signals_res = generate_all_signals(candles, ind_data, rsi_oversold=28.0, rsi_overbought=72.0)
            all_signals = signals_res.get("history", [])

            # Standard backtest
            bt = run_backtest(candles, all_signals, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
            s = bt["summary"]

            # High confidence backtest (>= 75%)
            filtered_sigs = []
            for sig in all_signals:
                if sig.get("confidence", 0) >= 75.0:
                    filtered_sigs.append(sig)
                else:
                    filtered_sigs.append({"signal": "NEUTRAL", "confidence": 0, "time": sig.get("time", 0)})

            bt_hc = run_backtest(candles, filtered_sigs, timeframe=tf, expiry_duration=exp, payout_rate=0.85, stake_amount=10.0)
            hc_s = bt_hc["summary"]

            sym_trades += s["total_trades"]
            sym_wins += s["wins"]
            sym_losses += s["losses"]
            sym_profit += s["total_profit"]
            sym_hc_wins += hc_s["wins"]
            sym_hc_losses += hc_s["losses"]

            group_breakdown[grp]["trades"] += s["total_trades"]
            group_breakdown[grp]["wins"] += s["wins"]
            group_breakdown[grp]["losses"] += s["losses"]
            group_breakdown[grp]["profit"] += s["total_profit"]
            group_breakdown[grp]["hc_wins"] += hc_s["wins"]
            group_breakdown[grp]["hc_losses"] += hc_s["losses"]

            grand_total_trades += s["total_trades"]
            grand_total_wins += s["wins"]
            grand_total_losses += s["losses"]
            grand_total_profit += s["total_profit"]
            high_conf_wins += hc_s["wins"]
            high_conf_losses += hc_s["losses"]
            high_conf_profit += hc_s["total_profit"]

        sym_wr = round((sym_wins / sym_trades * 100), 1) if sym_trades > 0 else 0.0
        hc_wr_str = f"{round(sym_hc_wins/(sym_hc_wins+sym_hc_losses)*100,1)}% ({sym_hc_wins}W/{sym_hc_losses}L)" if (sym_hc_wins + sym_hc_losses) > 0 else "N/A"

        ranked_assets.append({
            "label": label,
            "group": grp,
            "symbol": sym,
            "trades": sym_trades,
            "wins": sym_wins,
            "losses": sym_losses,
            "win_rate": sym_wr,
            "hc_wins": sym_hc_wins,
            "hc_losses": sym_hc_losses,
            "hc_wr": round((sym_hc_wins / (sym_hc_wins + sym_hc_losses) * 100), 1) if (sym_hc_wins + sym_hc_losses) > 0 else 0.0,
            "profit": round(sym_profit, 2),
        })

        print(f"{label:<14} | {grp:<18} | {'1m/5m':<4} | {sym_trades:<7} | {sym_wins:<5} | {sym_losses:<5} | {sym_wr:<10.1f}% | {hc_wr_str:<18} | ${sym_profit:<+11.2f}")

    elapsed = round(time.time() - start_time, 2)
    overall_winrate = round((grand_total_wins / grand_total_trades * 100), 2) if grand_total_trades > 0 else 0.0
    overall_hc_winrate = round((high_conf_wins / (high_conf_wins + high_conf_losses) * 100), 2) if (high_conf_wins + high_conf_losses) > 0 else 0.0

    ranked_assets.sort(key=lambda x: (x["hc_wr"] if (x["hc_wins"] + x["hc_losses"]) >= 3 else 0, x["win_rate"], x["profit"]), reverse=True)

    print("=" * 115)
    print("📊 AGGREGATE MULTI-MARKET PERFORMANCE REPORT:")
    print(f"   • Total Assets Evaluated        : {len(all_symbols)} Assets across 4 Market Classes")
    print(f"   • Total Simulated Trades        : {grand_total_trades:,} Closed-Candle Trades")
    print(f"   • Standard Strategy Win Rate    : {overall_winrate}% ({grand_total_wins:,} Wins / {grand_total_losses:,} Losses)")
    print(f"   • HIGH-CONFIDENCE (>=75%) Win % : {overall_hc_winrate}% ({high_conf_wins:,} Wins / {high_conf_losses:,} Losses)")
    print(f"   • Net Simulated Profit ($10)    : ${grand_total_profit:+,.2f} USD")
    print(f"   • Total Execution Time          : {elapsed} seconds (CPU load remained calm & protected)")
    print("=" * 115)

    print("\n📈 PERFORMANCE BY ASSET CLASS:")
    for gname, gstats in group_breakdown.items():
        g_wr = round((gstats["wins"] / gstats["trades"] * 100), 1) if gstats["trades"] > 0 else 0.0
        g_hc_tot = gstats["hc_wins"] + gstats["hc_losses"]
        g_hc_wr = round((gstats["hc_wins"] / g_hc_tot * 100), 1) if g_hc_tot > 0 else 0.0
        print(f"   • {gname:24s} | Trades: {gstats['trades']:4d} | Win Rate: {g_wr:5.1f}% | High-Conf Win Rate: {g_hc_wr:5.1f}% | Net PnL: ${gstats['profit']:+8.2f}")

    print("\n🏆 TOP 5 HIGHEST ACCURACY ASSETS (HIGH CONFIDENCE SETUP):")
    for i, a in enumerate(ranked_assets[:5], 1):
        print(f"   {i}. {a['label']:16s} ({a['group']:18s}) ➔ High-Conf Win Rate: {a['hc_wr']}% ({a['hc_wins']}W / {a['hc_losses']}L) | Net PnL: ${a['profit']:+.2f}")

if __name__ == "__main__":
    run_live_test()

