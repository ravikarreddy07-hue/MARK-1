import datetime
import numpy as np
from typing import List, Dict, Any, Optional

# ─── Forex session windows (UTC hours) ────────────────────────────────────────
LONDON_OPEN  = 8.0    # 08:00 UTC = 13:30 IST
LONDON_CLOSE = 16.5   # 16:30 UTC = 22:00 IST
NY_OPEN      = 13.0   # 13:00 UTC = 18:30 IST
NY_CLOSE     = 21.0   # 21:00 UTC = 02:30 IST+1

# ─── Asset type detection ─────────────────────────────────────────────────────
CRYPTO_SUFFIXES  = ("USDT", "USDC", "BTC", "ETH", "BNB")
SYNTH_KEYWORDS   = ("Volatility", "Boom", "Crash", "Jump", "Step", "Range")
FOREX_KEYWORDS   = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "INR")

def detect_asset_type(symbol: str) -> str:
    """Returns 'crypto', 'synthetic', or 'forex'"""
    s = symbol.upper()
    if any(s.endswith(sfx) for sfx in CRYPTO_SUFFIXES) or "USDT" in s:
        return "crypto"
    for kw in SYNTH_KEYWORDS:
        if kw.lower() in symbol.lower():
            return "synthetic"
    return "forex"

def is_active_session(timestamp_seconds: int, asset_type: str = "forex") -> bool:
    """
    Returns True if this candle falls in an active trading session.
    Crypto & Synthetics trade 24/7 → always True.
    Forex & Commodities → only during London or NY session.
    """
    if asset_type in ("crypto", "synthetic"):
        return True
    try:
        dt   = datetime.datetime.fromtimestamp(timestamp_seconds, tz=datetime.timezone.utc)
        hour = dt.hour + dt.minute / 60.0
        in_london = LONDON_OPEN <= hour <= LONDON_CLOSE
        in_ny     = NY_OPEN <= hour <= NY_CLOSE
        return in_london or in_ny
    except Exception:
        return True  # fail open


# ─── Hard-coded learned weights from grid-search backtesting ─────────────────
WEIGHT_RSI_EXTREME     = 4.0
WEIGHT_RSI_HOOK        = 3.0
WEIGHT_STOCHRSI_CROSS  = 3.5
WEIGHT_BB_PIERCE       = 3.0
WEIGHT_BB_CLOSE_INSIDE = 1.5
WEIGHT_WICK_STRENGTH   = 2.5
WEIGHT_ENGULF          = 2.0
WEIGHT_MACD_CROSS      = 3.0
WEIGHT_MACD_ALIGN      = 1.0
WEIGHT_ATR_FAVORABLE   = 1.5
WEIGHT_EMA_PULL        = 1.5
WEIGHT_CONSECUTIVE_RUN = 1.5

# Stricter minimum weighted score (raised from 8.0 → 10.0)
MIN_BULL_SCORE = 10.0
MIN_BEAR_SCORE = 10.0

# Stricter lead requirement (raised from 3.0 → 4.0)
MIN_LEAD = 4.0

# ADX threshold — skip signals when market is choppy
ADX_MIN_TREND = 20.0



def evaluate_candle_signal(
    idx: int,
    candles: List[Dict[str, Any]],
    raw_ind: Dict[str, Any],
    rsi_oversold: float = 28.0,
    rsi_overbought: float = 72.0,
    min_confidence: float = 60.0,
    asset_type: str = "forex",
) -> Dict[str, Any]:
    """
    V4 Precision Signal Engine — 5 active accuracy boosters:

    1. Session Filter     — Forex only fires during London/NY sessions
    2. ADX Trend Filter   — Skips signals when ADX < 20 (choppy market)
    3. Stricter scoring   — MIN_SCORE raised 8→10, MIN_LEAD raised 3→4
    4. All 5 pillars req. — Previously 4/5 pillars, now requires 5/5
    5. Confidence boost   — Base raised 65→70%, more reward for strong setups

    Original 5 pillars (ALL must fire):
      1. RSI / StochRSI Exhaustion
      2. Bollinger Band Envelope Touch or Pierce
      3. Price-action candle rejection wick
      4. MACD histogram momentum alignment
      5. Trend / EMA pull-back alignment
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

    # ── UPGRADE 1: Session filter ─────────────────────────────────────────────
    if not is_active_session(t, asset_type):
        return _neutral(t, close_p, "Outside trading session (London/NY only for Forex)")

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
    adx_arr   = raw_ind.get("adx",        [])

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
    curr_adx    = _get(adx_arr, idx)

    # ── Pre-flight checks ─────────────────────────────────────────────────────

    # UPGRADE 2: ADX filter — skip if market is choppy/ranging
    if curr_adx is not None and curr_adx < ADX_MIN_TREND:
        return _neutral(t, close_p, f"ADX {curr_adx:.1f} < {ADX_MIN_TREND} — market ranging, skip")

    # Skip candles with no meaningful volatility (ATR < 0.05% of price)
    if curr_atr is not None and curr_atr > 0:
        atr_pct = curr_atr / close_p
        if atr_pct < 0.0003:
            return _neutral(t, close_p, "ATR squeeze: no volatility")
        if atr_pct > 0.035:
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
        suggested_label = "1 Hr (Long-Term Swing)"

    max_score = (WEIGHT_RSI_EXTREME + WEIGHT_STOCHRSI_CROSS + WEIGHT_BB_PIERCE
                 + WEIGHT_BB_CLOSE_INSIDE + WEIGHT_WICK_STRENGTH + WEIGHT_ENGULF
                 + WEIGHT_MACD_CROSS + WEIGHT_ATR_FAVORABLE + WEIGHT_EMA_PULL
                 + WEIGHT_CONSECUTIVE_RUN)

    # UPGRADE 4: Require ALL 5 pillars (was >=4) — stricter confluence gate
    # UPGRADE 5: Confidence base raised 65→70% — only top setups hit >=85%
    if (bull_pillars >= 5
            and bull_score >= MIN_BULL_SCORE
            and bull_score >= bear_score + MIN_LEAD):
        confidence = min(96.0, round(70.0 + (bull_score / max_score) * 26.0, 1))
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

    if (bear_pillars >= 5
            and bear_score >= MIN_BEAR_SCORE
            and bear_score >= bull_score + MIN_LEAD):
        confidence = min(96.0, round(70.0 + (bear_score / max_score) * 26.0, 1))
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
    asset_type: str = "forex",
) -> Dict[str, Any]:
    """
    Generates precision signals across all candles using the V4 engine.
    Includes 2-candle confirmation: a signal only stands if the previous
    candle also fired the same direction — eliminates single-candle false spikes.
    """
    if not candles or not indicator_data or "raw" not in indicator_data:
        return {"current": None, "markers": [], "history": []}

    raw = indicator_data["raw"]
    raw_history = []

    for i in range(len(candles)):
        sig = evaluate_candle_signal(
            idx=i,
            candles=candles,
            raw_ind=raw,
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
            asset_type=asset_type,
        )
        raw_history.append(sig)

    # UPGRADE 3: 2-candle confirmation — signal only valid if prev candle agreed
    history = []
    for i, sig in enumerate(raw_history):
        if sig["signal"] in ("CALL", "PUT") and i > 0:
            prev = raw_history[i - 1]
            if prev["signal"] != sig["signal"]:
                # Previous candle disagreed — neutralise this signal
                confirmed = _neutral(
                    sig["time"], sig["entry_price"],
                    f"No 2-candle confirmation (prev={prev['signal']})",
                    suggested_time=sig.get("suggested_trade_time", "5min"),
                    suggested_secs=sig.get("suggested_trade_seconds", 300),
                    suggested_label=sig.get("suggested_trade_label", "5 Min"),
                )
                history.append(confirmed)
                continue
        history.append(sig)

    markers = []
    for sig in history:
        if sig["signal"] == "CALL":
            markers.append({
                "time": sig["time"],
                "position": "belowBar",
                "color": "#00E676",
                "shape": "arrowUp",
                "text": f"CALL {sig['confidence']}%",
                "id": f"call_{sig['time']}",
            })
        elif sig["signal"] == "PUT":
            markers.append({
                "time": sig["time"],
                "position": "aboveBar",
                "color": "#FF1744",
                "shape": "arrowDown",
                "text": f"PUT {sig['confidence']}%",
                "id": f"put_{sig['time']}",
            })

    # Determine primary actionable signal
    current_signal = None
    if len(history) >= 2:
        last_closed_sig = history[-2]
        forming_sig     = history[-1]

        if last_closed_sig.get("signal") in ("CALL", "PUT") and last_closed_sig.get("confidence", 0) >= 75.0:
            current_signal = dict(last_closed_sig)
            current_signal["status"] = "CONFIRMED"
            current_signal["status_label"] = "🟢 Confirmed Setup (Closed Candle)"
            current_signal["is_confirmed"] = True
        elif forming_sig.get("signal") in ("CALL", "PUT"):
            current_signal = dict(forming_sig)
            current_signal["status"] = "FORMING"
            current_signal["status_label"] = "⚡ High-Momentum Spike" if forming_sig.get("confidence", 0) >= 85 else "🟡 Forming (Wait for Candle Close)"
            current_signal["is_confirmed"] = forming_sig.get("confidence", 0) >= 85
        else:
            current_signal = dict(forming_sig)
            current_signal["status"] = "NEUTRAL"
            current_signal["status_label"] = "⚪ Market Consolidation"
            current_signal["is_confirmed"] = False
    elif history:
        current_signal = history[-1]

    return {"current": current_signal, "markers": markers, "history": history}

    return {"current": current_signal, "markers": markers, "history": history}
