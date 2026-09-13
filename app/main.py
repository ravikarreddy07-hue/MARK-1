import os
import time
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.services.data_fetcher import fetch_ohlcv, fetch_ohlcv_with_source, INTERVAL_SECONDS
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import (
    generate_all_signals,
    evaluate_candle_signal,
    detect_asset_type,
    ENGINE_PRESETS,
    ELITE_70_SYMBOLS,
)
from app.services.backtester import run_backtest
from app.services.optimizer import optimize_strategy
from app.services.trade_manager import trade_manager
from app.services.deriv_auto_trader import deriv_trader

app = FastAPI(title="Quantum Binary - TradingView Terminal API", version="2.0.0")

# Enable standard CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Auto-connects to Deriv on server startup and starts 24/7 autonomous cloud scanner and keepalive."""
    asyncio.create_task(deriv_trader.auto_connect_on_startup())
    asyncio.create_task(deriv_trader.run_autonomous_scanner())
    asyncio.create_task(deriv_trader.run_cloud_keepalive())

@app.get("/ping")
@app.get("/api/health")
def health_check():
    """Lightweight keep-alive endpoint for UptimeRobot monitoring and cloud health status."""
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "bot_connected": deriv_trader.is_connected,
        "bot_authorized": deriv_trader.is_authorized,
        "auto_trading": deriv_trader.is_auto_trading_enabled,
        "account": deriv_trader.account_info.get("loginid"),
        "balance": deriv_trader.account_info.get("balance"),
        "active_contracts": len(deriv_trader.active_contracts),
    }

class TradeCreateRequest(BaseModel):
    symbol: str = Field("BTCUSDT", min_length=1, max_length=30)
    signal: str = Field(..., pattern="^(CALL|PUT)$")
    entry_price: float = Field(..., gt=0.0)
    duration_seconds: int = Field(300, ge=5, le=86400)
    stake: float = Field(10.0, gt=0.0)
    payout_rate: float = Field(0.85, gt=0.0, le=1.0)
    timeframe: str = Field("1m", pattern="^(1m|2m|3m|5m|15m|30m|1h|4h|1d)$")

class TradeUpdateRequest(BaseModel):
    outcome: str = Field(..., pattern="^(WIN|LOSS|TIE)$")
    exit_price: Optional[float] = Field(None, gt=0.0)

class ResolveTradeRequest(BaseModel):
    current_price: float = Field(..., gt=0.0)
    symbol: Optional[str] = Field(None, max_length=30)

class BacktestRequest(BaseModel):
    symbol: str = Field("BTCUSDT", min_length=1, max_length=30)
    timeframe: str = Field("1m", pattern="^(1m|2m|3m|5m|15m|30m|1h|4h|1d)$")
    expiry_duration: str = Field("5min", pattern="^(30s|1min|2min|3min|5min|15min|30min|1hr)$")
    limit: int = Field(500, ge=50, le=1000)
    payout_rate: float = Field(0.85, gt=0.0, le=1.0)
    stake: float = Field(10.0, gt=0.0)
    rsi_period: int = Field(9, ge=2, le=200)
    rsi_oversold: float = Field(28.0, ge=5.0, le=45.0)
    rsi_overbought: float = Field(72.0, ge=55.0, le=95.0)
    macd_fast: int = Field(12, ge=2, le=100)
    macd_slow: int = Field(26, ge=5, le=200)
    macd_signal: int = Field(9, ge=2, le=100)
    sma_period: int = Field(20, ge=2, le=200)
    ema_period: int = Field(50, ge=2, le=200)
    bb_period: int = Field(20, ge=2, le=200)
    bb_std: float = Field(2.0, gt=0.1, le=10.0)

class OptimizeRequest(BaseModel):
    symbol: str = Field("BTCUSDT", min_length=1, max_length=30)
    timeframe: str = Field("1m", pattern="^(1m|2m|3m|5m|15m|30m|1h|4h|1d)$")
    expiry_duration: str = Field("5min", pattern="^(30s|1min|2min|3min|5min|15min|30min|1hr)$")
    limit: int = Field(1000, ge=100, le=1000)
    payout_rate: float = Field(0.85, gt=0.0, le=1.0)
    stake: float = Field(10.0, gt=0.0)

class DerivConnectRequest(BaseModel):
    token: str = Field(..., min_length=5, max_length=150)
    app_id: Optional[str] = Field(None, max_length=50)

class DerivConfigRequest(BaseModel):
    default_stake: Optional[float] = Field(None, gt=0.0)
    min_confidence: Optional[int] = Field(None, ge=50, le=100)
    preferred_duration: Optional[int] = Field(None, ge=1, le=1440)
    duration_unit: Optional[str] = Field(None, pattern="^(s|m|h|d)$")
    take_profit_daily: Optional[float] = Field(None, ge=0.0)
    stop_loss_daily: Optional[float] = Field(None, ge=0.0)
    max_daily_trades: Optional[int] = Field(None, ge=1, le=50000)
    max_daily_losses: Optional[int] = Field(None, ge=1, le=10000)
    max_concurrent_trades: Optional[int] = Field(None, ge=1, le=20)
    cooldown_seconds: Optional[int] = Field(None, ge=5, le=600)
    is_auto_trading_enabled: Optional[bool] = None

class DerivManualTradeRequest(BaseModel):
    symbol: str = Field("EURUSD", min_length=1, max_length=30)
    signal: str = Field(..., pattern="^(CALL|PUT)$")
    stake: Optional[float] = Field(10.0, gt=0.0)
    duration: Optional[int] = Field(5, ge=1, le=1440)
    duration_unit: Optional[str] = Field("m", pattern="^(s|m|h|d)$")


@app.get("/api/market-data")
def get_market_data(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30, description="Trading pair symbol"),
    interval: str = Query("1m", pattern="^(1m|2m|3m|5m|15m|30m|1h|4h|1d)$", description="Candle timeframe"),
    limit: int = Query(500, ge=50, le=1000, description="Number of candles"),
    end_time: Optional[int] = Query(None, description="End timestamp for historical inspection"),
    rsi_period: int = Query(9, ge=2, le=200),
    rsi_oversold: float = Query(28.0, ge=5.0, le=45.0),
    rsi_overbought: float = Query(72.0, ge=55.0, le=95.0),
    macd_fast: int = Query(12, ge=2, le=100),
    macd_slow: int = Query(26, ge=5, le=200),
    macd_signal: int = Query(9, ge=2, le=100),
    bb_period: int = Query(20, ge=2, le=200),
    bb_std: float = Query(2.0, gt=0.1, le=10.0),
    sma_period: int = Query(20, ge=2, le=200),
    ema_period: int = Query(50, ge=2, le=200),
    engine: str = Query("v4.1", pattern="^(v4|v4.1)$", description="Engine preset (v4 or v4.1)"),
    elite_mode: bool = Query(False, description="Enable Elite 70% Sniper Mode"),
):
    """
    Returns OHLCV candlestick data, calculated technical indicators, and real-time confluence signals.
    """
    candles, data_source = fetch_ohlcv_with_source(symbol=symbol, interval=interval, limit=limit, end_time=end_time)
    
    if not candles:
        raise HTTPException(status_code=502, detail="Failed to retrieve candlestick data.")

    # 1. Compute Indicators
    indicators = compute_all_indicators(
        candles,
        rsi_period=rsi_period,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        bb_period=bb_period,
        bb_std=bb_std,
        sma_period=sma_period,
        ema_period=ema_period,
    )

    # 2. Evaluate Signals
    asset_type = detect_asset_type(symbol)
    signal_data = generate_all_signals(
        candles,
        indicators,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        asset_type=asset_type,
        engine_version=engine,
        symbol=symbol,
        is_elite_mode=elite_mode,
    )

    current_signal = signal_data["current"]
    markers = signal_data["markers"]
    
    # Auto-execute trade on Deriv if enabled
    if current_signal and current_signal.get("signal") in ("CALL", "PUT") and deriv_trader.is_auto_trading_enabled:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    deriv_trader.on_signal_received(
                        symbol=symbol,
                        signal_data=current_signal,
                    )
                )
        except Exception:
            pass

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "data_source": data_source,
        "candles": candles,
        "indicators": indicators,
        "signal": current_signal,
        "markers": markers,
        "engine_version": signal_data.get("engine_version", engine),
        "preset_label": signal_data.get("preset_label", engine),
        "is_elite_mode": signal_data.get("is_elite_mode", elite_mode),
    }


@app.get("/api/signal-at-time")
def get_signal_at_time(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30),
    interval: str = Query("1m", pattern="^(1m|2m|3m|5m|15m|30m|1h|4h|1d)$"),
    target_time: int = Query(..., description="UNIX timestamp in seconds of candle to inspect"),
    limit: int = Query(200, ge=50, le=500),
    rsi_period: int = Query(9, ge=2, le=200),
    rsi_oversold: float = Query(28.0, ge=5.0, le=45.0),
    rsi_overbought: float = Query(72.0, ge=55.0, le=95.0),
    macd_fast: int = Query(12, ge=2, le=100),
    macd_slow: int = Query(26, ge=5, le=200),
    macd_signal: int = Query(9, ge=2, le=100),
    bb_period: int = Query(20, ge=2, le=200),
    bb_std: float = Query(2.0, gt=0.1, le=10.0),
    sma_period: int = Query(20, ge=2, le=200),
    ema_period: int = Query(50, ge=2, le=200),
    engine: str = Query("v4.1", pattern="^(v4|v4.1)$"),
    elite_mode: bool = Query(False, description="Enable Elite 70% Sniper Mode"),
):
    """
    Evaluates indicators and returns signal details for a specific historical point in time.
    """
    candles, _ = fetch_ohlcv_with_source(symbol=symbol, interval=interval, limit=limit, end_time=target_time)
    if not candles:
        raise HTTPException(status_code=404, detail="No historical candle found at target time")

    indicators = compute_all_indicators(
        candles,
        rsi_period=rsi_period,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        bb_period=bb_period,
        bb_std=bb_std,
        sma_period=sma_period,
        ema_period=ema_period,
    )

    idx = len(candles) - 1
    asset_type = detect_asset_type(symbol)
    preset = ENGINE_PRESETS.get(engine.lower(), ENGINE_PRESETS["v4.1"])
    sig_info = evaluate_candle_signal(
        idx=idx,
        candles=candles,
        raw_ind=indicators.get("raw", {}),
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        asset_type=asset_type,
        preset=preset,
        symbol=symbol,
        is_elite_mode=elite_mode,
    )

    return {
        "symbol": symbol.upper(),
        "target_time": target_time,
        "candle": candles[-1],
        "signal": sig_info,
        "engine_version": engine,
        "is_elite_mode": elite_mode,
    }


@app.get("/api/backtest")
def get_backtest(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30),
    timeframe: str = Query("1m", pattern="^(1m|2m|3m|5m|15m|30m|1h|4h|1d)$"),
    expiry_duration: str = Query("5min", pattern="^(30s|1min|2min|3min|5min|15min|30min|1hr)$"),
    limit: int = Query(500, ge=50, le=1000),
    payout_rate: float = Query(0.85, gt=0.0, le=1.0),
    stake: float = Query(10.0, gt=0.0),
    rsi_period: int = Query(9, ge=2, le=200),
    rsi_oversold: float = Query(28.0, ge=5.0, le=45.0),
    rsi_overbought: float = Query(72.0, ge=55.0, le=95.0),
    macd_fast: int = Query(12, ge=2, le=100),
    macd_slow: int = Query(26, ge=5, le=200),
    macd_signal: int = Query(9, ge=2, le=100),
    sma_period: int = Query(20, ge=2, le=200),
    ema_period: int = Query(50, ge=2, le=200),
    bb_period: int = Query(20, ge=2, le=200),
    bb_std: float = Query(2.0, gt=0.1, le=10.0),
    engine: str = Query("v4.1", pattern="^(v4|v4.1)$"),
    elite_mode: bool = Query(False, description="Enable Elite 70% Sniper Mode"),
):
    """
    Executes historical backtest over live market data.
    """
    candles, _ = fetch_ohlcv_with_source(symbol=symbol, interval=timeframe, limit=limit)
    if not candles or len(candles) < 30:
        raise HTTPException(status_code=400, detail="Insufficient candle data to run backtest.")

    indicators = compute_all_indicators(
        candles,
        rsi_period=rsi_period,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        bb_period=bb_period,
        bb_std=bb_std,
        sma_period=sma_period,
        ema_period=ema_period,
    )

    asset_type = detect_asset_type(symbol)
    signal_data = generate_all_signals(
        candles,
        indicators,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        asset_type=asset_type,
        engine_version=engine,
        symbol=symbol,
        is_elite_mode=elite_mode,
    )

    signals_history = signal_data.get("history", [])

    results = run_backtest(
        candles=candles,
        signals=signals_history,
        timeframe=timeframe,
        expiry_duration=expiry_duration,
        payout_rate=payout_rate,
        stake_amount=stake,
    )

    return results



# Scanner Asset Watchlist
SCANNER_WATCHLIST = [
    # Forex Majors
    {"symbol": "EURUSD", "market": "Forex", "name": "EUR / USD", "tvSymbol": "FX:EURUSD"},
    {"symbol": "GBPUSD", "market": "Forex", "name": "GBP / USD", "tvSymbol": "FX:GBPUSD"},
    {"symbol": "USDJPY", "market": "Forex", "name": "USD / JPY", "tvSymbol": "FX:USDJPY"},
    {"symbol": "AUDUSD", "market": "Forex", "name": "AUD / USD", "tvSymbol": "FX:AUDUSD"},
    {"symbol": "USDCAD", "market": "Forex", "name": "USD / CAD", "tvSymbol": "FX:USDCAD"},
    {"symbol": "USDCHF", "market": "Forex", "name": "USD / CHF", "tvSymbol": "FX:USDCHF"},
    {"symbol": "NZDUSD", "market": "Forex", "name": "NZD / USD", "tvSymbol": "FX:NZDUSD"},
    # Forex Crosses
    {"symbol": "EURGBP", "market": "Forex", "name": "EUR / GBP", "tvSymbol": "FX:EURGBP"},
    {"symbol": "EURJPY", "market": "Forex", "name": "EUR / JPY", "tvSymbol": "FX:EURJPY"},
    {"symbol": "GBPJPY", "market": "Forex", "name": "GBP / JPY", "tvSymbol": "FX:GBPJPY"},
    {"symbol": "AUDJPY", "market": "Forex", "name": "AUD / JPY", "tvSymbol": "FX:AUDJPY"},
    {"symbol": "USDINR", "market": "Forex", "name": "USD / INR", "tvSymbol": "FX_IDC:USDINR"},
    # Commodities & Metals
    {"symbol": "GOLD",   "market": "Commodities", "name": "Gold (XAU/USD)", "tvSymbol": "TVC:GOLD"},
    {"symbol": "SILVER", "market": "Commodities", "name": "Silver (XAG/USD)", "tvSymbol": "TVC:SILVER"},
    {"symbol": "USOIL",  "market": "Commodities", "name": "Crude Oil (WTI)", "tvSymbol": "TVC:USOIL"},
    # Global Indices & Stocks
    {"symbol": "SPX",    "market": "Indices", "name": "S&P 500", "tvSymbol": "SP:SPX"},
    {"symbol": "NDX",    "market": "Indices", "name": "NASDAQ 100", "tvSymbol": "NASDAQ:NDX"},
    {"symbol": "DJI",    "market": "Indices", "name": "Dow Jones", "tvSymbol": "DJ:DJI"},
    {"symbol": "AAPL",   "market": "Stocks",  "name": "Apple (AAPL)", "tvSymbol": "NASDAQ:AAPL"},
    {"symbol": "TSLA",   "market": "Stocks",  "name": "Tesla (TSLA)", "tvSymbol": "NASDAQ:TSLA"},
    {"symbol": "NVDA",   "market": "Stocks",  "name": "NVIDIA (NVDA)", "tvSymbol": "NASDAQ:NVDA"},
    # Cryptocurrencies
    {"symbol": "BTCUSDT", "market": "Crypto", "name": "BTC / USDT", "tvSymbol": "BINANCE:BTCUSDT"},
    {"symbol": "ETHUSDT", "market": "Crypto", "name": "ETH / USDT", "tvSymbol": "BINANCE:ETHUSDT"},
    {"symbol": "SOLUSDT", "market": "Crypto", "name": "SOL / USDT", "tvSymbol": "BINANCE:SOLUSDT"},
    {"symbol": "BNBUSDT", "market": "Crypto", "name": "BNB / USDT", "tvSymbol": "BINANCE:BNBUSDT"},
    {"symbol": "XRPUSDT", "market": "Crypto", "name": "XRP / USDT", "tvSymbol": "BINANCE:XRPUSDT"},
    {"symbol": "DOGEUSDT", "market": "Crypto", "name": "DOGE / USDT", "tvSymbol": "BINANCE:DOGEUSDT"},
    {"symbol": "PEPEUSDT", "market": "Crypto", "name": "PEPE / USDT", "tvSymbol": "BINANCE:PEPEUSDT"},
    {"symbol": "SUIUSDT",  "market": "Crypto", "name": "SUI / USDT", "tvSymbol": "BINANCE:SUIUSDT"},
    # Synthetic Volatility Indices (24/7/365 Always Active on Deriv)
    {"symbol": "R_100",   "market": "Synthetics", "name": "Volatility 100 Index", "tvSymbol": "DERIV:R_100"},
    {"symbol": "R_75",    "market": "Synthetics", "name": "Volatility 75 Index", "tvSymbol": "DERIV:R_75"},
    {"symbol": "R_50",    "market": "Synthetics", "name": "Volatility 50 Index", "tvSymbol": "DERIV:R_50"},
    {"symbol": "1HZ100V", "market": "Synthetics", "name": "Vol 100 (1s) Index", "tvSymbol": "DERIV:1HZ100V"},
]


@app.get("/api/scanner/signals")
def get_scanner_signals(
    interval: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    market_filter: Optional[str] = Query(None, description="Forex, Crypto, Commodities, Indices, Stocks, high_conf, elite_forex"),
    engine: str = Query("v4.1", pattern="^(v4|v4.1)$"),
    elite_mode: bool = Query(False, description="Filter to Elite 70% Whitelist and Grade A+ Setups (>=80% conf)"),
):
    """
    Live Multi-Chart Signal Scanner: Evaluates live signals across all market charts simultaneously.
    Supports High-Conf Forex and Elite 70% Sniper Mode filtering.
    """
    is_elite = elite_mode or (bool(market_filter) and market_filter.lower() in ("high_conf", "elite_forex"))
    
    items_to_scan = SCANNER_WATCHLIST
    if market_filter:
        mf = market_filter.lower()
        if mf in ("high_conf", "elite_forex"):
            # High-Conf Forex: Whitelisted Forex pairs only
            items_to_scan = [i for i in SCANNER_WATCHLIST if i["market"].lower() == "forex" and i["symbol"] in ELITE_70_SYMBOLS]
        elif mf != "all":
            items_to_scan = [i for i in SCANNER_WATCHLIST if i["market"].lower() == mf]
    elif elite_mode:
        items_to_scan = [i for i in SCANNER_WATCHLIST if i["symbol"] in ELITE_70_SYMBOLS]

    results = []
    for item in items_to_scan:
        sym = item["symbol"]
        try:
            candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=interval, limit=100)
            if not candles or len(candles) < 30:
                continue

            ind = compute_all_indicators(candles, rsi_period=9, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0)
            sig_data = generate_all_signals(
                candles,
                ind,
                rsi_oversold=28.0,
                rsi_overbought=72.0,
                asset_type=detect_asset_type(sym),
                engine_version=engine,
                symbol=sym,
                is_elite_mode=is_elite,
            )
            curr_sig = sig_data["current"]
            conf = curr_sig.get("confidence", 0)

            # In high_conf or elite mode, only show actionable signals with confidence >= 80% (Grade A+)
            if is_elite and (curr_sig.get("signal") not in ("CALL", "PUT") or conf < 80):
                continue

            # Auto-execute trade on Deriv if enabled and signal meets confidence criteria
            if deriv_trader.is_auto_trading_enabled and curr_sig.get("signal") in ("CALL", "PUT"):
                min_conf = float(deriv_trader.config.get("min_confidence", 80))
                if conf >= min_conf:
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(
                                deriv_trader.on_signal_received(
                                    symbol=sym,
                                    signal_data=curr_sig,
                                )
                            )
                    except Exception:
                        pass

            price = candles[-1]["close"]
            digits = 5 if price < 5 else (3 if "JPY" in sym else 2)

            results.append({
                "symbol": sym,
                "name": item["name"],
                "market": item["market"],
                "tvSymbol": item["tvSymbol"],
                "price": round(price, digits),
                "signal": curr_sig.get("signal", "NEUTRAL"),
                "confidence": conf,
                "score": curr_sig.get("score", 0),
                "is_elite": curr_sig.get("is_elite", False) or conf >= 80,
                "suggested_trade_time": curr_sig.get("suggested_trade_time", "5min"),
                "suggested_trade_label": curr_sig.get("suggested_trade_label", "5 Min"),
                "suggested_trade_seconds": curr_sig.get("suggested_trade_seconds", 300),
                "reasons": curr_sig.get("reasons", []),
                "time": curr_sig.get("time", int(time.time())),
            })
        except Exception:
            continue

    # Sort so high-confidence actionable setups appear first
    results.sort(key=lambda x: (x["signal"] in ("CALL", "PUT"), x["confidence"]), reverse=True)
    return {
        "timestamp": int(time.time()),
        "interval": interval,
        "count": len(results),
        "signals": results,
        "is_elite_mode": is_elite,
    }


@app.get("/api/optimize")
def get_optimize(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30),
    timeframe: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    expiry_duration: str = Query("5min", pattern="^(30s|1min|2min|3min|5min|15min|30min|1hr)$"),
    limit: int = Query(1000, ge=100, le=1000),
    payout_rate: float = Query(0.85, gt=0.0, le=1.0),
    stake: float = Query(10.0, gt=0.0),
):
    """
    AI Parameter Optimizer: Scans market data to discover optimal indicator parameters maximizing win rate.
    """
    res = optimize_strategy(
        symbol=symbol,
        timeframe=timeframe,
        expiry_duration=expiry_duration,
        limit=limit,
        payout_rate=payout_rate,
        stake=stake,
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# ─── TRADES & LOCAL JOURNAL ENDPOINTS ─────────────────────────────────────────

@app.get("/api/trades")
def get_trades():
    """Returns all recorded trades."""
    return trade_manager.get_all_trades()


@app.post("/api/trades")
def create_trade(req: TradeCreateRequest):
    """Records a new active trade with trade time countdown."""
    trade = trade_manager.create_trade(
        symbol=req.symbol,
        signal=req.signal,
        entry_price=req.entry_price,
        expiry_duration_seconds=req.duration_seconds,
        stake=req.stake,
        payout_rate=req.payout_rate,
        timeframe=req.timeframe,
    )
    return trade


@app.post("/api/trades/resolve")
def resolve_trades(req: ResolveTradeRequest):
    """Resolves any active trades whose trade time has passed."""
    updated_trades = trade_manager.resolve_active_trades(
        current_price=req.current_price,
        symbol=req.symbol,
    )
    return updated_trades


@app.put("/api/trades/{trade_id}")
def update_trade(trade_id: str, req: TradeUpdateRequest):
    """Manually update or override a trade outcome (WIN/LOSS/TIE)."""
    trade = trade_manager.update_trade_outcome(trade_id, req.outcome, req.exit_price)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@app.delete("/api/trades")
def clear_trades():
    """Clears trade journal."""
    trade_manager.clear_history()
    return {"message": "Trade history cleared"}


# ─── DERIV AUTOMATED TRADING BOT ENDPOINTS ────────────────────────────────────

@app.post("/api/deriv/connect")
async def deriv_connect(req: DerivConnectRequest):
    """Connects and authorizes with Deriv API (supports 2026 Options REST/WS and Legacy API)."""
    res = await deriv_trader.connect(token=req.token, app_id=req.app_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Connection failed"))
    return res


@app.get("/api/deriv/status")
def get_deriv_status():
    """Returns real-time status of Deriv auto-trader, active contracts, and daily PnL."""
    return deriv_trader.get_status()


@app.post("/api/deriv/config")
def update_deriv_config(req: DerivConfigRequest):
    """Updates auto-trading parameters and risk rules."""
    config_updates = req.model_dump(exclude_unset=True)
    return deriv_trader.update_config(config_updates)


@app.post("/api/deriv/trade")
async def execute_deriv_trade(req: DerivManualTradeRequest):
    """Executes a manual or automated trade contract directly on Deriv."""
    res = await deriv_trader.execute_trade(
        symbol=req.symbol,
        signal_type=req.signal,
        stake=req.stake,
        duration=req.duration,
        duration_unit=req.duration_unit,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Trade execution failed"))
    return res


@app.post("/api/deriv/disconnect")
async def deriv_disconnect():
    """Disconnects from Deriv and halts auto-trading."""
    return await deriv_trader.disconnect()


# Mount static directory for frontend assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"status": "running", "message": "Quantum Binary TradingView Terminal Active"})
