import sys, os, time, psutil

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_fetcher import fetch_ohlcv_with_source, ASSET_CATALOG
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals
from app.services.backtester import run_backtest

# ── Thermal limits ──────────────────────────────────────────────
CPU_WARN     = 55   # % - slow down
CPU_PAUSE    = 70   # % - pause 5s and retry
CPU_STOP     = 85   # % - FULL STOP to protect PC
TEMP_STOP    = 85   # degC - FULL STOP if sensor available

def get_thermal():
    """Returns (cpu_percent, temp_c_or_None)"""
    c = psutil.cpu_percent(interval=0.3)
    temp = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
                if key in temps and temps[key]:
                    temp = max(t.current for t in temps[key])
                    break
    except Exception:
        pass
    return c, temp

def check_thermal(label=""):
    """Check CPU/temp. Returns True=OK, False=STOP."""
    while True:
        cpu, temp = get_thermal()
        status = f"CPU:{cpu:.0f}%"
        if temp: status += f" | Temp:{temp:.0f}C"

        # Hard stop conditions
        if cpu >= CPU_STOP:
            print(f"\n  !!! OVERHEAT STOP !!! {status} >= {CPU_STOP}% CPU - STOPPING TO PROTECT YOUR PC")
            return False
        if temp and temp >= TEMP_STOP:
            print(f"\n  !!! OVERHEAT STOP !!! {status} >= {TEMP_STOP}C - STOPPING TO PROTECT YOUR PC")
            return False

        # Pause condition - wait and recheck
        if cpu >= CPU_PAUSE:
            print(f"  [THERMAL] {status} - Pausing 5s to cool...", end="\r")
            time.sleep(5)
            continue

        # Warn but continue slow
        if cpu >= CPU_WARN:
            print(f"  [WARM] {status} - Slowing down...", end="\r")
            time.sleep(1.5)

        return True  # OK to continue

def run_round(n, cum):
    print(f"\n{'='*110}")
    print(f"  ROUND {n}  |  {time.strftime('%H:%M:%S')}  |  Cumulative Trades: {cum['trades']:,}")
    print(f"{'='*110}")
    print(f"{'Asset':<14} | {'Group':<18} | {'Trades':<6} | {'W':<4} | {'L':<4} | {'Win%':<6} | {'HiConf%':<12} | PnL")
    print("-"*110)

    syms = [{"symbol": s["value"], "group": g["group"], "label": s["label"]}
            for g in ASSET_CATALOG for s in g["symbols"]]
    tfs = [("1m","5min"), ("5m","5min")]

    rt=rw=rl=rhw=rhl=0; rp=0.0
    grp_stats={}; ranked=[]
    overheat = False

    for si in syms:
        sym, grp, lbl = si["symbol"], si["group"], si["label"]
        if grp not in grp_stats:
            grp_stats[grp]={"t":0,"w":0,"l":0,"p":0.0,"hw":0,"hl":0}

        # Thermal check before each asset
        ok = check_thermal(lbl)
        if not ok:
            overheat = True
            break

        time.sleep(0.04)

        st=sw=sl=shw=shl=0; sp=0.0
        for tf, exp in tfs:
            candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=tf, limit=500)
            if not candles or len(candles) < 50:
                continue

            ind = compute_all_indicators(candles, rsi_period=11, macd_fast=12, macd_slow=26,
                                         macd_signal=9, bb_period=20, bb_std=2.0)
            sigs = generate_all_signals(candles, ind,
                                        rsi_oversold=28.0, rsi_overbought=72.0).get("history", [])

            s = run_backtest(candles, sigs, timeframe=tf, expiry_duration=exp,
                             payout_rate=0.85, stake_amount=10.0)["summary"]
            hc_sigs = [sig if sig.get("confidence", 0) >= 75
                       else {"signal":"NEUTRAL","confidence":0,"time":sig.get("time",0)}
                       for sig in sigs]
            h = run_backtest(candles, hc_sigs, timeframe=tf, expiry_duration=exp,
                             payout_rate=0.85, stake_amount=10.0)["summary"]

            st+=s["total_trades"]; sw+=s["wins"]; sl+=s["losses"]; sp+=s["total_profit"]
            shw+=h["wins"]; shl+=h["losses"]
            grp_stats[grp]["t"]+=s["total_trades"]; grp_stats[grp]["w"]+=s["wins"]
            grp_stats[grp]["l"]+=s["losses"];       grp_stats[grp]["p"]+=s["total_profit"]
            grp_stats[grp]["hw"]+=h["wins"];         grp_stats[grp]["hl"]+=h["losses"]
            rt+=s["total_trades"]; rw+=s["wins"]; rl+=s["losses"]; rp+=s["total_profit"]
            rhw+=h["wins"]; rhl+=h["losses"]

        wr  = round(sw/st*100, 1) if st > 0 else 0.0
        hct = shw + shl
        hcs = f"{round(shw/hct*100,1)}% ({shw}W/{shl}L)" if hct > 0 else "N/A"
        ranked.append({"label":lbl,"group":grp,"trades":st,"wr":wr,
                       "hc_wins":shw,"hc_losses":shl,
                       "hc_wr":round(shw/hct*100,1) if hct>0 else 0.0,
                       "profit":round(sp,2)})
        print(f"{lbl:<14} | {grp:<18} | {st:<6} | {sw:<4} | {sl:<4} | {wr:<5.1f}% | {hcs:<12} | ${sp:+.2f}")

    # Round summary
    ov_wr = round(rw/rt*100, 2) if rt > 0 else 0.0
    hct   = rhw + rhl
    hc_wr = round(rhw/hct*100, 2) if hct > 0 else 0.0
    ranked.sort(key=lambda x:(x["hc_wr"] if x["hc_wins"]+x["hc_losses"]>=3 else 0, x["wr"], x["profit"]), reverse=True)

    print(f"{'='*110}")
    print(f"  ROUND {n} | Trades:{rt:,} | Win%:{ov_wr}% | HiConf%:{hc_wr}% | PnL:${rp:+,.2f}")
    if overheat:
        print(f"  *** Round cut short due to overheating! ***")

    print(f"\n  BY CLASS:")
    for gn, gs in grp_stats.items():
        g_wr = round(gs["w"]/gs["t"]*100, 1) if gs["t"] > 0 else 0.0
        gh   = gs["hw"] + gs["hl"]
        ghw  = round(gs["hw"]/gh*100, 1) if gh > 0 else 0.0
        print(f"    {gn:<26} | Trades:{gs['t']:4d} | Win%:{g_wr:5.1f}% | HiConf%:{ghw:5.1f}% | PnL:${gs['p']:+8.2f}")

    print(f"\n  TOP 5 THIS ROUND:")
    for i, a in enumerate(ranked[:5], 1):
        print(f"    {i}. {a['label']:<16} ({a['group']:<18}) HiConf:{a['hc_wr']}% ({a['hc_wins']}W/{a['hc_losses']}L) PnL:${a['profit']:+.2f}")

    cum["trades"]+=rt; cum["wins"]+=rw; cum["losses"]+=rl; cum["profit"]+=rp
    cum["hc_wins"]+=rhw; cum["hc_losses"]+=rhl
    cw  = round(cum["wins"]/cum["trades"]*100, 2) if cum["trades"] > 0 else 0.0
    cht = cum["hc_wins"] + cum["hc_losses"]
    chw = round(cum["hc_wins"]/cht*100, 2) if cht > 0 else 0.0
    print(f"\n  CUMULATIVE after {n} round(s): Trades:{cum['trades']:,} | Win%:{cw}% | HiConf%:{chw}% | PnL:${cum['profit']:+,.2f}")

    return overheat

def print_final(cum, n, reason):
    cw  = round(cum["wins"]/cum["trades"]*100, 2) if cum["trades"] > 0 else 0.0
    cht = cum["hc_wins"] + cum["hc_losses"]
    chw = round(cum["hc_wins"]/cht*100, 2) if cht > 0 else 0.0
    print(f"\n{'='*110}")
    print(f"  STOPPED: {reason} | Rounds completed: {n}")
    print(f"  FINAL RESULTS:")
    print(f"    Total Trades : {cum['trades']:,}")
    print(f"    Win Rate     : {cw}%")
    print(f"    HiConf Win%  : {chw}%")
    print(f"    Net PnL      : ${cum['profit']:+,.2f}")
    print("="*110)

if __name__ == "__main__":
    print("="*110)
    print("  QUANTUM BINARY - CONTINUOUS STRESS TEST")
    print(f"  Thermal limits: WARN>{CPU_WARN}% | PAUSE>{CPU_PAUSE}% | HARD STOP>{CPU_STOP}% CPU / {TEMP_STOP}C")
    print("  Tell the agent 'stop' whenever you want to end the test.")
    print("="*110)

    cum = {"trades":0,"wins":0,"losses":0,"profit":0.0,"hc_wins":0,"hc_losses":0}
    n = 0
    try:
        while True:
            n += 1
            overheat = run_round(n, cum)
            if overheat:
                print_final(cum, n, "OVERHEATING - PC PROTECTED")
                break
            print(f"\n  Round {n} complete. Starting round {n+1} in 3s... (Ctrl+C to stop)\n")
            time.sleep(3)
    except KeyboardInterrupt:
        print_final(cum, n, "Stopped by user")
