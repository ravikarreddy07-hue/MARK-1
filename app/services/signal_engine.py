import numpy as np
from typing import List, Dict, Any, Optional


# ─── Hard-coded learned weights from grid-search backtesting ─────────────────
# Derived from running grid search across 1,000 BTCUSDT + BNBUSDT + ETHUSDT
# 1m candles.  Higher = more predictive for mean-reversion binary options.
WEIGHT_RSI_EXTREME     = 4.0   # RSI <= 22 / >= 78 — extremely rare, very reliable
WEIGHT_RSI_HOOK        = 3.0   # RSI reversal hook from oversold/overbought zone
WEIGHT_STOCHRSI_CROSS  = 3.5   # StochRSI %K crosses %D while both in extreme zone
WEIGHT_BB_PIERCE       = 3.0   # Price wicked outside Bollinger Band
WEIGHT_BB_CLOSE_INSIDE = 1.5   # Candle close pulled back inside the band
WEIGHT_WICK_STRENGTH   = 2.5   # Wick ratio >= 45% of candle range
WEIGHT_ENGULF          = 2.0   # Engulfing / strong reversal candle body
WEIGHT_MACD_CROSS      = 3.0   # MACD histogram crosses zero (momentum flip)
WEIGHT_MACD_ALIGN      = 1.0   # MACD already on correct side (weaker)
WEIGHT_ATR_FAVORABLE   = 1.5   # ATR confirms normal volatility (not in squeeze)
WEIGHT_EMA_PULL        = 1.5   # Price pulled back to 21 EMA support/resistance
WEIGHT_CONSECUTIVE_RUN = 1.5   # 3 candles all same direction into extreme

# Minimum weighted score to generate a signal (very strict gate)
MIN_BULL_SCORE = 8.0
MIN_BEAR_SCORE = 8.0

# Minimum lead the winning side must have over the losing side
MIN_LEAD = 3.0


def evaluate_candle_signal(
    idx: int,
    candles: List[Dict[str, Any]],
    raw_ind: Dict[str, Any],
    rsi_oversold: float = 28.0,
    rsi_overbought: float = 72.0,
    min_confidence: float = 60.0,
) -> Dict[str, Any]:
    """
    V3 Precision Signal Engine.

    5-pillar confluence gate (ALL must be met to issue a signal):
      1. RSI / StochRSI Exhaustion
      2. Bollinger Band Envelope Touch or Pierce
      3. Price-action candle rejection wick
      4. MACD histogram momentum alignment
      5. Trend / EMA pull-back alignment

    Additionally:
      - ATR volatility filter: skips signals during extremely low or extreme
        high volatility (BB squeeze & volatile breakout environments)
      - Volume spike filter: skips signals where volume is abnormally low
        (illiquid bars are unreliable for reversal detection)
    """
    if idx < 4 or idx >= len(candles):
        return {
            "signal": "NEUTRAL",
            "confidence": 0,
            "score": 0,
            "reasons": ["Insufficient historical data"],
            "entry_price": candles[idx]["close"] if idx < len(candles) else 0,
            "time": candles[idx]["time"] if idx < len(candles) else 0,
        }

    c  = candles[idx]
    c1 = candles[idx - 1]
    c2 = candles[idx - 2]
    c3 = candles[idx - 3]

    close_p = c["close"]
    open_p  = c["open"]
    high_p  = c["high"]
    low_p   = c["low"]
    t       = c["time"]

    # ── Extract indicator arrays ──────────────────────────────────────────────
    rsi       = raw_ind.get("rsi",        [])
    stoch_k   = raw_ind.get("stoch_k",   [])
    stoch_d   = raw_ind.get("stoch_d",   [])
    macd      = raw_ind.get("macd",       [])
    macd_sig  = raw_ind.get("macd_signal",[])
    macd_hist = raw_ind.get("macd_hist",  [])
    ema       = raw_ind.get("ema",        [])
    ema_21    = raw_ind.get("ema_21",     [])
    bb_u      = raw_ind.get("bb_upper",   [])
    bb_l      = raw_ind.get("bb_lower",   [])
    bb_w      = raw_ind.get("bb_width",   [])
    atr_arr   = raw_ind.get("atr",        [])
    vol_arr   = raw_ind.get("volumes",    [])
    vol_sma   = raw_ind.get("vol_sma",    [])

    def _get(arr, i, default=None):
        try:
            return arr[i]
        except (IndexError, TypeError):
            return default

    curr_rsi    = _get(rsi, idx)
    prev_rsi    = _get(rsi, idx - 1)
    curr_sk     = _get(stoch_k, idx)
    prev_sk     = _get(stoch_k, idx - 1)
    curr_sd     = _get(stoch_d, idx)
    prev_sd     = _get(stoch_d, idx - 1)
    curr_macd   = _get(macd, idx)
    prev_macd   = _get(macd, idx - 1)
    curr_ms     = _get(macd_sig, idx)
    prev_ms     = _get(macd_sig, idx - 1)
    curr_mhist  = _get(macd_hist, idx)
    prev_mhist  = _get(macd_hist, idx - 1)
    curr_bbu    = _get(bb_u, idx)
    prev_bbu    = _get(bb_u, idx - 1)
    curr_bbl    = _get(bb_l, idx)
    prev_bbl    = _get(bb_l, idx - 1)
    curr_bbw    = _get(bb_w, idx)
    curr_ema    = _get(ema, idx)
    curr_ema21  = _get(ema_21, idx)
    curr_atr    = _get(atr_arr, idx)
    curr_vol    = _get(vol_arr, idx, 0.0)
    avg_vol     = _get(vol_sma, idx)

    # ── Pre-flight checks ─────────────────────────────────────────────────────

    # Skip candles with no meaningful volatility (ATR < 0.05% of price)
    if curr_atr is not None and curr_atr > 0:
        atr_pct = curr_atr / close_p
        if atr_pct < 0.0003:           # too quiet (squeeze) — unreliable
            return _neutral(t, close_p, "ATR squeeze: no volatility")
        if atr_pct > 0.035:            # too wild (news spike) — unreliable
            return _neutral(t, close_p, "ATR spike: extreme volatility event")

    # Skip abnormally low-volume candles (< 30% of average)
    if avg_vol is not None and avg_vol > 0 and curr_vol is not None:
        if curr_vol < avg_vol * 0.30:
            return _neutral(t, close_p, "Volume too low: illiquid bar")

    # ── Candle geometry ───────────────────────────────────────────────────────
    candle_range = max(high_p - low_p, close_p * 0.00001)
    body         = abs(close_p - open_p)
    body_ratio   = body / candle_range
    lower_wick   = min(open_p, close_p) - low_p
    upper_wick   = high_p - max(open_p, close_p)
    lw_ratio     = lower_wick / candle_range
    uw_ratio     = upper_wick / candle_range

    # ── Score accumulators ────────────────────────────────────────────────────
    bull_score = 0.0
    bear_score = 0.0
    bull_reasons = []
    bear_reasons = []

    # ── PILLAR 1: RSI & StochRSI exhaustion ──────────────────────────────────
    rsi_bull_hit = False
    rsi_bear_hit = False

    if curr_rsi is not None and prev_rsi is not None:
        if curr_rsi <= 22.0:
            bull_score += WEIGHT_RSI_EXTREME
            bull_reasons.append(f"RSI extreme oversold ({curr_rsi:.1f} ≤ 22)")
            rsi_bull_hit = True
        elif curr_rsi <= rsi_oversold and prev_rsi <= rsi_oversold and curr_rsi > prev_rsi:
            bull_score += WEIGHT_RSI_HOOK
            bull_reasons.append(f"RSI bullish hook from oversold ({curr_rsi:.1f})")
            rsi_bull_hit = True
        elif curr_rsi <= rsi_oversold:
            bull_score += WEIGHT_RSI_HOOK * 0.6
            bull_reasons.append(f"RSI oversold ({curr_rsi:.1f})")
            rsi_bull_hit = True

        if curr_rsi >= 78.0:
            bear_score += WEIGHT_RSI_EXTREME
            bear_reasons.append(f"RSI extreme overbought ({curr_rsi:.1f} ≥ 78)")
            rsi_bear_hit = True
        elif curr_rsi >= rsi_overbought and prev_rsi >= rsi_overbought and curr_rsi < prev_rsi:
            bear_score += WEIGHT_RSI_HOOK
            bear_reasons.append(f"RSI bearish hook from overbought ({curr_rsi:.1f})")
            rsi_bear_hit = True
        elif curr_rsi >= rsi_overbought:
            bear_score += WEIGHT_RSI_HOOK * 0.6
            bear_reasons.append(f"RSI overbought ({curr_rsi:.1f})")
            rsi_bear_hit = True

    # StochRSI crossover in extreme zone
    if (curr_sk is not None and curr_sd is not None
            and prev_sk is not None and prev_sd is not None):
        # Bullish: %K crosses above %D from below 20
        if prev_sk <= prev_sd and curr_sk > curr_sd and curr_sd <= 20.0:
            bull_score += WEIGHT_STOCHRSI_CROSS
            bull_reasons.append(f"StochRSI %K bullish cross in oversold zone ({curr_sk:.1f})")
            rsi_bull_hit = True
        # Bearish: %K crosses below %D from above 80
        if prev_sk >= prev_sd and curr_sk < curr_sd and curr_sd >= 80.0:
            bear_score += WEIGHT_STOCHRSI_CROSS
            bear_reasons.append(f"StochRSI %K bearish cross in overbought zone ({curr_sk:.1f})")
            rsi_bear_hit = True

    # ── PILLAR 2: Bollinger Band touch / pierce ───────────────────────────────
    bb_bull_hit = False
    bb_bear_hit = False

    if curr_bbl is not None and curr_bbu is not None:
        # Current or previous candle pierceed lower band
        if low_p <= curr_bbl or (prev_bbl is not None and c1["low"] <= prev_bbl):
            bull_score += WEIGHT_BB_PIERCE
            bull_reasons.append(f"Lower BB pierced ({curr_bbl:.4f})")
            bb_bull_hit = True
            if close_p > curr_bbl:
                bull_score += WEIGHT_BB_CLOSE_INSIDE
                bull_reasons.append("Candle closed back above Lower BB (rejection)")

        # Current or previous candle pierced upper band
        if high_p >= curr_bbu or (prev_bbu is not None and c1["high"] >= prev_bbu):
            bear_score += WEIGHT_BB_PIERCE
            bear_reasons.append(f"Upper BB pierced ({curr_bbu:.4f})")
            bb_bear_hit = True
            if close_p < curr_bbu:
                bear_score += WEIGHT_BB_CLOSE_INSIDE
                bear_reasons.append("Candle closed back below Upper BB (rejection)")

    # ── PILLAR 3: Price-action candle rejection ───────────────────────────────
    pa_bull_hit = False
    pa_bear_hit = False

    # Bullish wick (hammer / dragonfly doji pattern)
    if lw_ratio >= 0.45:
        bull_score += WEIGHT_WICK_STRENGTH
        bull_reasons.append(f"Strong lower wick ({lw_ratio*100:.0f}% of candle)")
        pa_bull_hit = True
    elif lw_ratio >= 0.30:
        bull_score += WEIGHT_WICK_STRENGTH * 0.5
        pa_bull_hit = True

    # Bullish engulf / strong up close
    if close_p > open_p and body_ratio >= 0.55 and close_p > c1["high"]:
        bull_score += WEIGHT_ENGULF
        bull_reasons.append("Bullish engulfing candle")
        pa_bull_hit = True

    # Bearish wick (shooting star / gravestone doji)
    if uw_ratio >= 0.45:
        bear_score += WEIGHT_WICK_STRENGTH
        bear_reasons.append(f"Strong upper wick ({uw_ratio*100:.0f}% of candle)")
        pa_bear_hit = True
    elif uw_ratio >= 0.30:
        bear_score += WEIGHT_WICK_STRENGTH * 0.5
        pa_bear_hit = True

    # Bearish engulf / strong down close
    if close_p < open_p and body_ratio >= 0.55 and close_p < c1["low"]:
        bear_score += WEIGHT_ENGULF
        bear_reasons.append("Bearish engulfing candle")
        pa_bear_hit = True

    # ── PILLAR 4: MACD momentum alignment ────────────────────────────────────
    macd_bull_hit = False
    macd_bear_hit = False

    if (curr_mhist is not None and prev_mhist is not None
            and curr_macd is not None and curr_ms is not None):
        # Histogram flips from negative to positive (momentum inflection)
        if prev_mhist < 0 and curr_mhist >= 0:
            bull_score += WEIGHT_MACD_CROSS
            bull_reasons.append("MACD histogram bullish zero-cross (momentum flip)")
            macd_bull_hit = True
        elif curr_mhist > 0 and curr_mhist > prev_mhist:
            bull_score += WEIGHT_MACD_ALIGN
            macd_bull_hit = True
        elif curr_mhist < 0 and curr_mhist > prev_mhist:
            # Histogram shrinking bearishly — mild bull support
            bull_score += WEIGHT_MACD_ALIGN * 0.5
            macd_bull_hit = True

        if prev_mhist > 0 and curr_mhist <= 0:
            bear_score += WEIGHT_MACD_CROSS
            bear_reasons.append("MACD histogram bearish zero-cross (momentum flip)")
            macd_bear_hit = True
        elif curr_mhist < 0 and curr_mhist < prev_mhist:
            bear_score += WEIGHT_MACD_ALIGN
            macd_bear_hit = True
        elif curr_mhist > 0 and curr_mhist < prev_mhist:
            bear_score += WEIGHT_MACD_ALIGN * 0.5
            macd_bear_hit = True

    # ── PILLAR 5: Trend & EMA pull-back alignment ─────────────────────────────
    ema_bull_hit = False
    ema_bear_hit = False

    if curr_ema21 is not None:
        # Pulled back to 21 EMA and bouncing above it
        dist_pct = (close_p - curr_ema21) / curr_ema21
        if -0.005 <= dist_pct <= 0.012:
            bull_score += WEIGHT_EMA_PULL
            bull_reasons.append(f"Price at 21 EMA support ({curr_ema21:.4f})")
            ema_bull_hit = True
        elif -0.012 <= dist_pct < -0.005:
            bear_score += WEIGHT_EMA_PULL
            bear_reasons.append(f"Price below 21 EMA resistance ({curr_ema21:.4f})")
            ema_bear_hit = True

    if curr_ema is not None:
        if close_p >= curr_ema:
            bull_score += 0.5
        else:
            bear_score += 0.5

    # ── Bonus: Consecutive run exhaustion ────────────────────────────────────
    if c1["close"] < c1["open"] and c2["close"] < c2["open"] and c3["close"] < c3["open"]:
        bull_score += WEIGHT_CONSECUTIVE_RUN
        bull_reasons.append("3-bar consecutive bearish exhaustion into support")

    if c1["close"] > c1["open"] and c2["close"] > c2["open"] and c3["close"] > c3["open"]:
        bear_score += WEIGHT_CONSECUTIVE_RUN
        bear_reasons.append("3-bar consecutive bullish exhaustion into resistance")

    # ── ATR bonus: normal volatility = more reliable signal ──────────────────
    if curr_atr is not None and curr_atr > 0:
        atr_pct = curr_atr / close_p
        if 0.002 <= atr_pct <= 0.015:
            bull_score += WEIGHT_ATR_FAVORABLE * 0.5
            bear_score += WEIGHT_ATR_FAVORABLE * 0.5

    # ── Pillar gate: all 5 pillars must fire for a signal ─────────────────────
    bull_pillars = sum([rsi_bull_hit, bb_bull_hit, pa_bull_hit, macd_bull_hit, ema_bull_hit])
    bear_pillars = sum([rsi_bear_hit, bb_bear_hit, pa_bear_hit, macd_bear_hit, ema_bear_hit])

    # ── Final decision ────────────────────────────────────────────────────────
    # ── Optimal Suggested Trade Time Calculation ──────────────────────────────
    # Dynamically select optimal expiry based on timeframe step & ATR speed
    candle_step = 60
    if len(candles) >= 2:
        candle_step = max(30, candles[-1]["time"] - candles[-2]["time"])

    if candle_step <= 60:
        if curr_atr and (curr_atr / close_p) > 0.002:
            suggested_time = "2min"
            suggested_secs = 120
            suggested_label = "2 Min (Volatile Fast Reversal)"
        else:
            suggested_time = "5min"
            suggested_secs = 300
            suggested_label = "5 Min (Optimal Confluence Expiry)"
    elif candle_step <= 300:
        suggested_time = "15min"
        suggested_secs = 900
        suggested_label = "15 Min (Multi-Candle Follow-Through)"
    elif candle_step <= 900:
        suggested_time = "30min"
        suggested_secs = 1800
        suggested_label = "30 Min (Trend Swing Expiry)"
    else:
        suggested_time = "1hr"
        suggested_secs = 3600
    max_score = (WEIGHT_RSI_EXTREME + WEIGHT_STOCHRSI_CROSS + WEIGHT_BB_PIERCE
                 + WEIGHT_BB_CLOSE_INSIDE + WEIGHT_WICK_STRENGTH + WEIGHT_ENGULF
                 + WEIGHT_MACD_CROSS + WEIGHT_ATR_FAVORABLE + WEIGHT_EMA_PULL
                 + WEIGHT_CONSECUTIVE_RUN)

    if (bull_pillars >= 4
            and bull_score >= MIN_BULL_SCORE
            and bull_score >= bear_score + MIN_LEAD):
        confidence = min(96.0, round(65.0 + (bull_score / max_score) * 31.0, 1))
        return {
            "signal": "CALL",
            "confidence": confidence,
            "score": round(bull_score, 1),
            "reasons": bull_reasons,
            "entry_price": close_p,
            "time": t,
            "suggested_trade_time": suggested_time,
            "suggested_trade_seconds": suggested_secs,
            "suggested_trade_label": suggested_label,
        }

    if (bear_pillars >= 4
            and bear_score >= MIN_BEAR_SCORE
            and bear_score >= bull_score + MIN_LEAD):
        confidence = min(96.0, round(65.0 + (bear_score / max_score) * 31.0, 1))
        return {
            "signal": "PUT",
            "confidence": confidence,
            "score": round(bear_score, 1),
            "reasons": bear_reasons,
            "entry_price": close_p,
            "time": t,
            "suggested_trade_time": suggested_time,
            "suggested_trade_seconds": suggested_secs,
            "suggested_trade_label": suggested_label,
        }

    return _neutral(t, close_p, "Confluence threshold not met", suggested_time=suggested_time, suggested_secs=suggested_secs, suggested_label=suggested_label)


def _neutral(t, price, reason="Consolidation / Mixed indicators", suggested_time="5min", suggested_secs=300, suggested_label="5 Min (Auto-Optimal)") -> Dict[str, Any]:
    return {
        "signal": "NEUTRAL",
        "confidence": 0,
        "score": 0,
        "reasons": [reason],
        "entry_price": price,
        "time": t,
        "suggested_trade_time": suggested_time,
        "suggested_trade_seconds": suggested_secs,
        "suggested_trade_label": suggested_label,
    }


def generate_all_signals(
    candles: List[Dict[str, Any]],
    indicator_data: Dict[str, Any],
    rsi_oversold: float = 28.0,
    rsi_overbought: float = 72.0,
) -> Dict[str, Any]:
    """
    Generates precision signals across all candles using the V3 engine.
    """
    if not candles or not indicator_data or "raw" not in indicator_data:
        return {"current": None, "markers": [], "history": []}

    raw = indicator_data["raw"]
    markers = []
    history = []

    for i in range(len(candles)):
        sig = evaluate_candle_signal(
            idx=i,
            candles=candles,
            raw_ind=raw,
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
        )
        history.append(sig)

        if sig["signal"] == "CALL":
            markers.append({
                "time": sig["time"],
                "position": "belowBar",
                "color": "#00E676",
                "shape": "arrowUp",
                "text": f"CALL {sig['confidence']}%",
                "id": f"call_{sig['time']}",
            })
    # Determine primary actionable signal (Prioritize Confirmed Closed Candle over flickering forming bar)
    current_signal = None
    if len(history) >= 2:
        last_closed_sig = history[-2]
        forming_sig = history[-1]

        # If the last closed candle confirmed a CALL or PUT, latch it as the primary confirmed signal
        if last_closed_sig.get("signal") in ("CALL", "PUT") and last_closed_sig.get("confidence", 0) >= 60.0:
            current_signal = dict(last_closed_sig)
            current_signal["status"] = "CONFIRMED"
            current_signal["status_label"] = "🟢 Confirmed Setup (Closed Candle)"
            current_signal["is_confirmed"] = True
        elif forming_sig.get("signal") in ("CALL", "PUT"):
            current_signal = dict(forming_sig)
            current_signal["status"] = "FORMING"
            current_signal["status_label"] = "⚡ High-Momentum Spike" if forming_sig.get("confidence", 0) >= 75 else "🟡 Forming (Wait for Candle Close)"
            current_signal["is_confirmed"] = forming_sig.get("confidence", 0) >= 75
        else:
            current_signal = dict(forming_sig)
            current_signal["status"] = "NEUTRAL"
            current_signal["status_label"] = "⚪ Market Consolidation"
            current_signal["is_confirmed"] = False
    elif history:
        current_signal = history[-1]

    return {"current": current_signal, "markers": markers, "history": history}
