import pytest
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.data_fetcher import fetch_ohlcv, generate_synthetic_data, fetch_ohlcv_with_source
from app.services.indicators import (
    calculate_rsi,
    calculate_ema,
    calculate_sma,
    calculate_macd,
    calculate_bollinger_bands,
    compute_all_indicators,
)
from app.services.signal_engine import generate_all_signals, evaluate_candle_signal
from app.services.backtester import run_backtest
from app.services.trade_manager import TradeManager

client = TestClient(app)

def test_synthetic_data_generation():
    candles = generate_synthetic_data("EURUSD", "1m", limit=100)
    assert len(candles) == 100
    for c in candles:
        assert "time" in c
        assert "open" in c
        assert "high" in c
        assert "low" in c
        assert "close" in c
        assert "volume" in c
        assert c["high"] >= c["low"]

def test_indicator_calculations_and_edge_cases():
    prices = np.array([10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], dtype=float)
    
    # 1. RSI
    rsi = calculate_rsi(prices, period=14)
    assert len(rsi) == len(prices)
    assert not np.isnan(rsi[-1])
    assert 0 <= rsi[-1] <= 100

    # Flatline RSI edge case (zero deltas)
    flat_prices = np.array([100.0] * 30, dtype=float)
    flat_rsi = calculate_rsi(flat_prices, period=14)
    assert flat_rsi[-1] == 50.0

    # 2. SMA & EMA
    sma = calculate_sma(prices, period=5)
    ema = calculate_ema(prices, period=5)
    assert len(sma) == len(prices)
    assert len(ema) == len(prices)
    assert not np.isnan(sma[-1])
    assert not np.isnan(ema[-1])

    # 3. MACD
    m, s, h = calculate_macd(prices, fast_period=5, slow_period=10, signal_period=3)
    assert len(m) == len(prices)
    assert len(s) == len(prices)
    assert len(h) == len(prices)

    # 4. Bollinger Bands
    upper, middle, lower, width, pct_b = calculate_bollinger_bands(prices, period=10, std_dev_multiplier=2.0)
    assert len(upper) == len(prices)
    assert upper[-1] >= middle[-1] >= lower[-1]

def test_signal_engine_and_backtest():
    candles = generate_synthetic_data("EURUSD", "1m", limit=300)
    ind_data = compute_all_indicators(candles)
    
    signals = generate_all_signals(candles, ind_data)
    assert "current" in signals
    assert "markers" in signals
    assert "history" in signals
    assert len(signals["history"]) == len(candles)

    # Backtest
    bt_res = run_backtest(candles, signals["history"], timeframe="1m", expiry_duration="5min")
    assert "summary" in bt_res
    assert "win_rate" in bt_res["summary"]
    assert "total_trades" in bt_res["summary"]
    assert "equity_curve" in bt_res

def test_trade_manager_symbol_scoping(tmp_path):
    tm = TradeManager(data_file=str(tmp_path / "trades_test.json"))
    eur_trade = tm.create_trade("EURUSD", "CALL", 1.0850, 300, stake=10.0)
    gbp_trade = tm.create_trade("GBPUSD", "PUT", 1.2950, 300, stake=10.0)

    # Resolve only EURUSD with price 1.0880 (WIN)
    tm.resolve_active_trades(current_price=1.0880, symbol="EURUSD", current_time=eur_trade["expiry_time"] + 1)
    
    all_trades = tm.get_all_trades()
    eur = [t for t in all_trades if t["symbol"] == "EURUSD"][0]
    gbp = [t for t in all_trades if t["symbol"] == "GBPUSD"][0]

    assert eur["outcome"] == "WIN"
    assert eur["status"] == "CLOSED"
    assert gbp["outcome"] == "PENDING"
    assert gbp["status"] == "ACTIVE"

def test_fastapi_endpoints_and_validation():
    # 1. Market data
    res = client.get("/api/market-data?symbol=EURUSD&interval=1m&limit=100")
    assert res.status_code == 200
    data = res.json()
    assert "candles" in data
    assert "indicators" in data
    assert "signal" in data
    assert "data_source" in data

    # 2. Validation error on invalid interval or invalid periods
    res_bad = client.get("/api/market-data?symbol=EURUSD&interval=invalid&rsi_period=0")
    assert res_bad.status_code == 422

    # 3. Backtest endpoint
    res_bt = client.get("/api/backtest?symbol=EURUSD&timeframe=1m&expiry_duration=5min&limit=100")
    assert res_bt.status_code == 200
    bt_data = res_bt.json()
    assert "summary" in bt_data

    # 4. Create and resolve trades
    res = client.post("/api/trades", json={
        "symbol": "EURUSD",
        "signal": "CALL",
        "entry_price": 1.0850,
        "duration_seconds": 60,
        "stake": 25.0,
        "payout_rate": 0.85,
        "timeframe": "1m"
    })
    assert res.status_code == 200

    res_resolve = client.post("/api/trades/resolve", json={
        "current_price": 1.0870,
        "symbol": "EURUSD"
    })
    assert res_resolve.status_code == 200

    res_trades = client.get("/api/trades")
    assert res_trades.status_code == 200
    assert len(res_trades.json()) >= 1

def test_forex_and_commodities_market_data():
    # Test Major Forex Pairs
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "GOLD", "SPX"]:
        res = client.get(f"/api/market-data?symbol={sym}&interval=1m&limit=50")
        assert res.status_code == 200
        data = res.json()
        assert len(data["candles"]) == 50
        assert data["signal"] is not None


def test_deriv_auto_trader_module():
    from app.services.deriv_auto_trader import DerivAutoTrader, DERIV_SYMBOL_MAP

    trader = DerivAutoTrader()
    # 1. Test symbol mapping
    assert trader.map_symbol("EURUSD") == "frxEURUSD"
    assert trader.map_symbol("BTCUSDT") == "cryBTCUSD"
    assert trader.map_symbol("R_100") == "R_100"

    # 2. Test configuration updates
    res = trader.update_config({
        "default_stake": 20.0,
        "min_confidence": 80,
        "is_auto_trading_enabled": True,
        "take_profit_daily": 100.0,
        "stop_loss_daily": 30.0,
    })
    assert res["success"] is True
    assert trader.config["default_stake"] == 20.0
    assert trader.config["min_confidence"] == 80
    assert trader.is_auto_trading_enabled is True

    # 3. Test status retrieval
    status = trader.get_status()
    assert "is_connected" in status
    assert "is_auto_trading_enabled" in status
    assert status["is_auto_trading_enabled"] is True
    assert "stats" in status

    # 4. Test endpoints via TestClient
    res_status = client.get("/api/deriv/status")
    assert res_status.status_code == 200
    assert "is_auto_trading_enabled" in res_status.json()

    res_cfg = client.post("/api/deriv/config", json={"default_stake": 15.0, "min_confidence": 75})
    assert res_cfg.status_code == 200
    assert res_cfg.json()["config"]["default_stake"] == 15.0

