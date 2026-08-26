from typing import List, Dict, Any
from app.services.data_fetcher import INTERVAL_SECONDS

TRADE_TIME_DURATION_SECONDS = {
    "30s": 30,
    "1min": 60,
    "2min": 120,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hr": 3600,
}
EXPIRY_DURATION_SECONDS = TRADE_TIME_DURATION_SECONDS

def run_backtest(
    candles: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    timeframe: str = "1m",
    expiry_duration: str = "5min",
    payout_rate: float = 0.85, # 85% payout on win
    stake_amount: float = 10.0, # $10 per trade
) -> Dict[str, Any]:
    """
    Simulates binary options trades across historical signals with exact expiry calculation.
    """
    tf_seconds = INTERVAL_SECONDS.get(timeframe, 60)
    exp_seconds = EXPIRY_DURATION_SECONDS.get(expiry_duration, 300)
    
    # Calculate how many candles ahead corresponds to the expiry
    expiry_bars = max(1, int(round(exp_seconds / tf_seconds)))

    n = len(candles)
    trades = []
    wins = 0
    losses = 0
    ties = 0
    total_profit = 0.0
    equity_curve = [0.0]
    gross_profit = 0.0
    gross_loss = 0.0
    
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0

    # Ensure signals match candles length
    num_eval = min(n, len(signals))

    for i in range(num_eval):
        sig_info = signals[i]
        sig_type = sig_info.get("signal", "NEUTRAL")
        
        if sig_type not in ("CALL", "PUT"):
            continue

        target_idx = i + expiry_bars
        if target_idx >= n:
            # Cannot resolve outcome yet because data hasn't elapsed
            continue

        entry_candle = candles[i]
        exit_candle = candles[target_idx]

        entry_price = entry_candle["close"]
        exit_price = exit_candle["close"]
        entry_time = entry_candle["time"]
        exit_time = exit_candle["time"]

        outcome = "TIE"
        pnl = 0.0

        if sig_type == "CALL":
            if exit_price > entry_price:
                outcome = "WIN"
                pnl = stake_amount * payout_rate
                wins += 1
                gross_profit += pnl
                if current_streak > 0:
                    current_streak += 1
                else:
                    current_streak = 1
                max_win_streak = max(max_win_streak, current_streak)
            elif exit_price < entry_price:
                outcome = "LOSS"
                pnl = -stake_amount
                losses += 1
                gross_loss += stake_amount
                if current_streak < 0:
                    current_streak -= 1
                else:
                    current_streak = -1
                max_loss_streak = max(max_loss_streak, abs(current_streak))
            else:
                outcome = "TIE"
                pnl = 0.0
                ties += 1
                current_streak = 0
        elif sig_type == "PUT":
            if exit_price < entry_price:
                outcome = "WIN"
                pnl = stake_amount * payout_rate
                wins += 1
                gross_profit += pnl
                if current_streak > 0:
                    current_streak += 1
                else:
                    current_streak = 1
                max_win_streak = max(max_win_streak, current_streak)
            elif exit_price > entry_price:
                outcome = "LOSS"
                pnl = -stake_amount
                losses += 1
                gross_loss += stake_amount
                if current_streak < 0:
                    current_streak -= 1
                else:
                    current_streak = -1
                max_loss_streak = max(max_loss_streak, abs(current_streak))
            else:
                outcome = "TIE"
                pnl = 0.0
                ties += 1
                current_streak = 0

        total_profit += pnl
        equity_curve.append(round(total_profit, 2))

        trades.append({
            "id": len(trades) + 1,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "signal": sig_type,
            "confidence": sig_info.get("confidence", 0),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "outcome": outcome,
            "pnl": round(pnl, 2),
            "reasons": sig_info.get("reasons", []),
        })

    total_trades = wins + losses + ties
    win_rate = round((wins / (wins + losses) * 100), 2) if (wins + losses) > 0 else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.9 if gross_profit > 0 else 1.0)
    roi_percent = round((total_profit / (total_trades * stake_amount) * 100), 2) if total_trades > 0 else 0.0

    return {
        "summary": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "win_rate": win_rate,
            "total_profit": round(total_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": profit_factor,
            "roi_percent": roi_percent,
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "timeframe": timeframe,
            "expiry_duration": expiry_duration,
            "expiry_bars": expiry_bars,
            "payout_rate": payout_rate,
            "stake_per_trade": stake_amount,
        },
        "equity_curve": equity_curve,
        "trades": trades,
    }
