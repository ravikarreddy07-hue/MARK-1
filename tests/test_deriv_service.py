import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.services.deriv_auto_trader import deriv_trader, DERIV_SYMBOL_MAP

client = TestClient(app)

def test_deriv_symbol_mapping():
    assert deriv_trader.map_symbol("EURUSD") == "frxEURUSD"
    assert deriv_trader.map_symbol("GOLD") == "frxXAUUSD"
    assert deriv_trader.map_symbol("XAUUSD") == "frxXAUUSD"
    assert deriv_trader.map_symbol("SILVER") == "frxXAGUSD"
    assert deriv_trader.map_symbol("BTCUSDT") == "cryBTCUSD"
    assert deriv_trader.map_symbol("R_100") == "R_100"
    assert deriv_trader.map_symbol("1HZ100V") == "1HZ100V"

def test_deriv_status_and_config_endpoints():
    # Test GET /api/deriv/status
    res = client.get("/api/deriv/status")
    assert res.status_code == 200
    data = res.json()
    assert "is_connected" in data
    assert "account" in data
    assert "config" in data
    assert "stats" in data

    # Test POST /api/deriv/config
    res_cfg = client.post("/api/deriv/config", json={
        "default_stake": 1.0,
        "min_confidence": 80,
        "take_profit_daily": 10.0,
        "stop_loss_daily": 2.0,
        "is_auto_trading_enabled": False,
    })
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert cfg_data["config"]["default_stake"] == 1.0
    assert cfg_data["config"]["min_confidence"] == 80
    assert cfg_data["config"]["stop_loss_daily"] == 2.0
    assert cfg_data["is_auto_trading_enabled"] is False

def test_deriv_disconnect_endpoint():
    res = client.post("/api/deriv/disconnect")
    assert res.status_code == 200
    assert res.json().get("success") is True
