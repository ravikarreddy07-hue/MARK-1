import time
import json
import os
import uuid
import threading
import tempfile
from typing import List, Dict, Any, Optional

TRADES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "trade_history.json")

class TradeManager:
    def __init__(self, data_file: str = TRADES_FILE):
        self.data_file = os.path.abspath(data_file)
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        self._lock = threading.Lock()
        self.trades: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self):
        """Atomic write to prevent corruption from concurrent access or sudden shutdown."""
        try:
            dir_name = os.path.dirname(self.data_file)
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(self.trades, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.data_file)
        except Exception as e:
            print(f"Error saving trades: {e}")

    def create_trade(
        self,
        symbol: str,
        signal: str,
        entry_price: float,
        expiry_duration_seconds: int,
        stake: float = 10.0,
        payout_rate: float = 0.85,
        timeframe: str = "1m",
    ) -> Dict[str, Any]:
        now = int(time.time())
        expiry_time = now + expiry_duration_seconds
        
        trade = {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "signal": signal.upper(),
            "entry_time": now,
            "expiry_time": expiry_time,
            "duration_seconds": expiry_duration_seconds,
            "entry_price": float(entry_price),
            "exit_price": None,
            "stake": float(stake),
            "payout_rate": float(payout_rate),
            "pnl": 0.0,
            "status": "ACTIVE", # ACTIVE or CLOSED
            "outcome": "PENDING", # WIN, LOSS, TIE, PENDING
        }
        with self._lock:
            self.trades.insert(0, trade)
            self._save()
        return trade

    def resolve_active_trades(
        self,
        current_price: float,
        symbol: Optional[str] = None,
        current_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Resolves active trades whose expiry time has elapsed.
        If symbol is provided, only resolves trades matching that symbol to prevent cross-asset price contamination.
        """
        now = current_time or int(time.time())
        updated = False

        with self._lock:
            for trade in self.trades:
                if trade.get("status") == "ACTIVE" and now >= trade.get("expiry_time", 0):
                    # Check symbol filter if provided
                    if symbol and trade.get("symbol", "").upper() != symbol.upper():
                        continue

                    trade["status"] = "CLOSED"
                    trade["exit_price"] = float(current_price)
                    entry_p = trade["entry_price"]
                    sig = trade["signal"]
                    stake = trade["stake"]
                    rate = trade.get("payout_rate", 0.85)

                    if sig == "CALL":
                        if current_price > entry_p:
                            trade["outcome"] = "WIN"
                            trade["pnl"] = round(stake * rate, 2)
                        elif current_price < entry_p:
                            trade["outcome"] = "LOSS"
                            trade["pnl"] = round(-stake, 2)
                        else:
                            trade["outcome"] = "TIE"
                            trade["pnl"] = 0.0
                    elif sig == "PUT":
                        if current_price < entry_p:
                            trade["outcome"] = "WIN"
                            trade["pnl"] = round(stake * rate, 2)
                        elif current_price > entry_p:
                            trade["outcome"] = "LOSS"
                            trade["pnl"] = round(-stake, 2)
                        else:
                            trade["outcome"] = "TIE"
                            trade["pnl"] = 0.0
                    updated = True

            if updated:
                self._save()
            
            return list(self.trades)

    def update_trade_outcome(self, trade_id: str, outcome: str, exit_price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            for trade in self.trades:
                if trade["id"] == trade_id:
                    trade["outcome"] = outcome.upper()
                    trade["status"] = "CLOSED"
                    if exit_price is not None:
                        trade["exit_price"] = float(exit_price)
                    
                    stake = trade.get("stake", 10.0)
                    rate = trade.get("payout_rate", 0.85)
                    if trade["outcome"] == "WIN":
                        trade["pnl"] = round(stake * rate, 2)
                    elif trade["outcome"] == "LOSS":
                        trade["pnl"] = round(-stake, 2)
                    else:
                        trade["pnl"] = 0.0

                    self._save()
                    return trade
            return None

    def clear_history(self):
        with self._lock:
            self.trades = []
            self._save()

    def get_all_trades(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.trades)

trade_manager = TradeManager()
