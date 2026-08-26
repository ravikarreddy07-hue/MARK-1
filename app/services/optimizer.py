import numpy as np
from typing import List, Dict, Any, Tuple
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals
from app.services.backtester import run_backtest
from app.services.data_fetcher import fetch_ohlcv_with_source

def optimize_strategy(
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    expiry_duration: str = "5min",
    limit: int = 1000,
    payout_rate: float = 0.85,
    stake: float = 10.0,
) -> Dict[str, Any]:
    """
    Quantitative Optimization Engine:
    Performs grid search and heuristic parameter tuning over historical data to discover
    the parameter combination that maximizes Win Rate % and Net Profit.
    """
    candles, source = fetch_ohlcv_with_source(symbol=symbol, interval=timeframe, limit=limit)
    if not candles or len(candles) < 100:
        return {"error": "Insufficient candle data for optimization"}

    # Parameter search space
    rsi_periods = [9, 11, 14, 18]
    rsi_thresholds = [(25.0, 75.0), (28.0, 72.0), (30.0, 70.0), (33.0, 67.0)]
    bb_settings = [(14, 2.0), (20, 2.0), (20, 2.2), (20, 2.5)]
    macd_settings = [(8, 21, 5), (12, 26, 9), (9, 26, 6)]
    min_confidence_levels = [60.0, 70.0, 75.0, 80.0]

    best_result = None
    best_score = -999999.0
    all_evaluated = []

    # Benchmark default settings first
    default_ind = compute_all_indicators(candles, rsi_period=14, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0)
    default_sigs = generate_all_signals(candles, default_ind, rsi_oversold=30.0, rsi_overbought=70.0)["history"]
    default_bt = run_backtest(candles, default_sigs, timeframe=timeframe, expiry_duration=expiry_duration, payout_rate=payout_rate, stake_amount=stake)

    # Grid search optimization
    for rsi_p in rsi_periods:
        for rsi_os, rsi_ob in rsi_thresholds:
            for bb_p, bb_std in bb_settings:
                for mf, ms, msig in macd_settings:
                    # Compute indicators
                    ind = compute_all_indicators(
                        candles,
                        rsi_period=rsi_p,
                        macd_fast=mf,
                        macd_slow=ms,
                        macd_signal=msig,
                        bb_period=bb_p,
                        bb_std=bb_std,
                        sma_period=20,
                        ema_period=50,
                    )
                    raw_sigs = generate_all_signals(candles, ind, rsi_oversold=rsi_os, rsi_overbought=rsi_ob)["history"]

                    for min_conf in min_confidence_levels:
                        # Filter by confidence threshold
                        filtered_sigs = []
                        for s in raw_sigs:
                            if s.get("confidence", 0) >= min_conf:
                                filtered_sigs.append(s)
                            else:
                                filtered_sigs.append({"signal": "NEUTRAL", "confidence": 0, "time": s.get("time", 0)})

                        bt = run_backtest(
                            candles=candles,
                            signals=filtered_sigs,
                            timeframe=timeframe,
                            expiry_duration=expiry_duration,
                            payout_rate=payout_rate,
                            stake_amount=stake,
                        )

                        summary = bt["summary"]
                        total_trades = summary["total_trades"]
                        win_rate = summary["win_rate"]
                        profit = summary["total_profit"]

                        # Need statistical significance (at least 20 trades per 1000 candles)
                        if total_trades >= 20:
                            # Objective function: Win Rate weighted by profit & sample size stability
                            score = (win_rate * 2.0) + (profit * 0.5) + min(total_trades, 100) * 0.1

                            entry = {
                                "win_rate": win_rate,
                                "total_profit": profit,
                                "total_trades": total_trades,
                                "wins": summary["wins"],
                                "losses": summary["losses"],
                                "profit_factor": summary["profit_factor"],
                                "params": {
                                    "rsi_period": rsi_p,
                                    "rsi_oversold": rsi_os,
                                    "rsi_overbought": rsi_ob,
                                    "bb_period": bb_p,
                                    "bb_std": bb_std,
                                    "macd_fast": mf,
                                    "macd_slow": ms,
                                    "macd_signal": msig,
                                    "min_confidence": min_conf,
                                },
                            }

                            if score > best_score and win_rate >= 55.0:
                                best_score = score
                                best_result = {
                                    "summary": summary,
                                    "equity_curve": bt["equity_curve"],
                                    "params": entry["params"],
                                }

    # Fallback if no configuration beat 55%
    if not best_result:
        best_result = {
            "summary": default_bt["summary"],
            "equity_curve": default_bt["equity_curve"],
            "params": {
                "rsi_period": 14,
                "rsi_oversold": 30.0,
                "rsi_overbought": 70.0,
                "bb_period": 20,
                "bb_std": 2.0,
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "min_confidence": 70.0,
            }
        }

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "expiry_duration": expiry_duration,
        "data_source": source,
        "candles_analyzed": len(candles),
        "default_baseline": {
            "win_rate": default_bt["summary"]["win_rate"],
            "total_profit": default_bt["summary"]["total_profit"],
            "total_trades": default_bt["summary"]["total_trades"],
        },
        "optimized_result": {
            "win_rate": best_result["summary"]["win_rate"],
            "total_profit": best_result["summary"]["total_profit"],
            "total_trades": best_result["summary"]["total_trades"],
            "wins": best_result["summary"]["wins"],
            "losses": best_result["summary"]["losses"],
            "profit_factor": best_result["summary"]["profit_factor"],
            "win_rate_boost": round(best_result["summary"]["win_rate"] - default_bt["summary"]["win_rate"], 2),
            "profit_boost": round(best_result["summary"]["total_profit"] - default_bt["summary"]["total_profit"], 2),
            "equity_curve": best_result["equity_curve"],
            "optimal_params": best_result["params"],
        }
    }
