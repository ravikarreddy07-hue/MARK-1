import os
import time
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.services.data_fetcher import fetch_ohlcv, fetch_ohlcv_with_source, INTERVAL_SECONDS
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals, evaluate_candle_signal
from app.services.backtester import run_backtest
from app.services.optimizer import optimize_strategy
from app.services.trade_manager import trade_manager

app = FastAPI(title="Quantum Binary - TradingView Terminal API", version="2.0.0")

# Enable standard CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TradeCreateRequest(BaseModel):
    symbol: str = Field("BTCUSDT", min_length=1, max_length=30)
    signal: str = Field(..., pattern="^(CALL|PUT)$")
    entry_price: float = Field(..., gt=0.0)
    duration_seconds: int = Field(300, ge=5, le=86400)
    stake: float = Field(10.0, gt=0.0)
    payout_rate: float = Field(0.85, gt=0.0, le=1.0)
    timeframe: str = Field("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$")

class TradeUpdateRequest(BaseModel):
    outcome: str = Field(..., pattern="^(WIN|LOSS|TIE)$")
    exit_price: Optional[float] = Field(None, gt=0.0)

class ResolveTradeRequest(BaseModel):
    current_price: float = Field(..., gt=0.0)
    symbol: Optional[str] = Field(None, max_length=30)

class BacktestRequest(BaseModel):
    symbol: str = Field("BTCUSDT", min_length=1, max_length=30)
    timeframe: str = Field("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$")
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
    timeframe: str = Field("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$")
    expiry_duration: str = Field("5min", pattern="^(30s|1min|2min|3min|5min|15min|30min|1hr)$")
    limit: int = Field(1000, ge=100, le=1000)
    payout_rate: float = Field(0.85, gt=0.0, le=1.0)
    stake: float = Field(10.0, gt=0.0)


@app.get("/api/market-data")
def get_market_data(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30, description="Trading pair symbol"),
    interval: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$", description="Candle timeframe"),
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
    signal_data = generate_all_signals(
        candles,
        indicators,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
    )

    current_signal = signal_data["current"]
    markers = signal_data["markers"]
    
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "data_source": data_source,
        "candles": candles,
        "indicators": indicators,
        "signal": current_signal,
        "markers": markers,
    }


@app.get("/api/signal-at-time")
def get_signal_at_time(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30),
    interval: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
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
    sig_info = evaluate_candle_signal(candles, indicators, idx, rsi_oversold=rsi_oversold, rsi_overbought=rsi_overbought)

    return {
        "symbol": symbol.upper(),
        "target_time": target_time,
        "candle": candles[-1],
        "signal": sig_info,
    }


@app.get("/api/backtest")
def get_backtest(
    symbol: str = Query("BTCUSDT", min_length=1, max_length=30),
    timeframe: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
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

    signal_data = generate_all_signals(
        candles,
        indicators,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
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
]


@app.get("/api/scanner/signals")
def get_scanner_signals(
    interval: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    market_filter: Optional[str] = Query(None, description="Forex, Crypto, Commodities, Indices, Stocks")
):
    """
    Live Multi-Chart Signal Scanner: Evaluates live signals across all market charts simultaneously.
    """
    items_to_scan = SCANNER_WATCHLIST
    if market_filter and market_filter.lower() != "all":
        items_to_scan = [i for i in SCANNER_WATCHLIST if i["market"].lower() == market_filter.lower()]

    results = []
    for item in items_to_scan:
        sym = item["symbol"]
        try:
            candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=interval, limit=100)
            if not candles or len(candles) < 30:
                continue

            ind = compute_all_indicators(candles, rsi_period=9, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0)
            sig_data = generate_all_signals(candles, ind, rsi_oversold=28.0, rsi_overbought=72.0)
            curr_sig = sig_data["current"]

            price = candles[-1]["close"]
            digits = 5 if price < 5 else (3 if "JPY" in sym else 2)

            results.append({
                "symbol": sym,
                "name": item["name"],
                "market": item["market"],
                "tvSymbol": item["tvSymbol"],
                "price": round(price, digits),
                "signal": curr_sig.get("signal", "NEUTRAL"),
                "confidence": curr_sig.get("confidence", 0),
                "score": curr_sig.get("score", 0),
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
    return {"timestamp": int(time.time()), "interval": interval, "count": len(results), "signals": results}


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
