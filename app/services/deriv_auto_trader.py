import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List, Callable
import websockets

logger = logging.getLogger("deriv_auto_trader")

DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# Symbol translation from terminal assets to Deriv contract asset IDs
DERIV_SYMBOL_MAP = {
    # Forex Majors & Crosses
    "EURUSD": "frxEURUSD",
    "GBPUSD": "frxGBPUSD",
    "USDJPY": "frxUSDJPY",
    "AUDUSD": "frxAUDUSD",
    "USDCAD": "frxUSDCAD",
    "USDCHF": "frxUSDCHF",
    "NZDUSD": "frxNZDUSD",
    "EURGBP": "frxEURGBP",
    "EURJPY": "frxEURJPY",
    "GBPJPY": "frxGBPJPY",
    "AUDJPY": "frxAUDJPY",
    "EURAUD": "frxEURAUD",
    "GBPAUD": "frxGBPAUD",
    
    # Cryptocurrencies
    "BTCUSDT": "cryBTCUSD",
    "ETHUSDT": "cryETHUSD",
    "SOLUSDT": "crySOLUSD",
    "XRPUSDT": "cryXRPUSD",
    "DOGEUSDT": "cryDOGEUSD",
    
    # Synthetic Volatility Indices
    "R_100": "R_100",
    "R_75": "R_75",
    "R_50": "R_50",
    "R_25": "R_25",
    "R_10": "R_10",
    "1HZ100V": "1HZ100V",
    "1HZ75V": "1HZ75V",
    "1HZ50V": "1HZ50V",
    "1HZ25V": "1HZ25V",
    "1HZ10V": "1HZ10V",
}


class DerivAutoTrader:
    def __init__(self):
        self.api_token: Optional[str] = None
        self.ws = None
        self.is_connected: bool = False
        self.is_authorized: bool = False
        self.is_auto_trading_enabled: bool = False
        
        # Account details
        self.account_info: Dict[str, Any] = {
            "loginid": None,
            "balance": 0.0,
            "currency": "USD",
            "is_virtual": True,
            "email": None,
            "fullname": None,
        }
        
        # Auto-Trading Configuration & Risk Rules
        self.config: Dict[str, Any] = {
            "default_stake": 10.0,
            "min_confidence": 75,
            "preferred_duration": 5,
            "duration_unit": "m",
            "take_profit_daily": 50.0,
            "stop_loss_daily": 25.0,
            "max_concurrent_trades": 3,
            "cooldown_seconds": 60,
        }
        
        # Runtime State & Performance
        self.daily_pnl: float = 0.0
        self.total_trades_count: int = 0
        self.won_trades_count: int = 0
        self.lost_trades_count: int = 0
        self.active_contracts: Dict[str, Any] = {}
        self.trade_cooldowns: Dict[str, float] = {}
        self.activity_log: List[Dict[str, Any]] = []
        
        self._ws_task = None
        self._running = False
        self._req_id = 1
        self._pending_requests: Dict[int, asyncio.Future] = {}

    def log_activity(self, message: str, level: str = "info", data: Optional[Dict[str, Any]] = None):
        entry = {
            "timestamp": int(time.time()),
            "time_str": time.strftime("%H:%M:%S", time.localtime()),
            "message": message,
            "level": level,
            "data": data or {},
        }
        self.activity_log.insert(0, entry)
        if len(self.activity_log) > 100:
            self.activity_log.pop()
        logger.info(f"[DerivAutoTrader] {message}")

    def map_symbol(self, symbol: str) -> str:
        clean = symbol.upper().replace("/", "").replace("-", "")
        return DERIV_SYMBOL_MAP.get(clean, clean)

    async def connect(self, token: str) -> Dict[str, Any]:
        """Connects and authorizes with Deriv WebSocket API."""
        clean_token = token.strip().replace('"', '').replace("'", "").replace("\n", "").replace("\r", "").replace(" ", "")
        self.api_token = clean_token
        self._running = True
        
        try:
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
            
            self.ws = await websockets.connect(DERIV_WS_URL, ping_interval=30, ping_timeout=10)
            self.is_connected = True
            
            # Start message receiving loop in background
            if self._ws_task and not self._ws_task.done():
                self._ws_task.cancel()
            self._ws_task = asyncio.create_task(self._listen_loop())
            
            # Send authorize request
            auth_res = await self._send_request({"authorize": self.api_token})
            
            if "error" in auth_res:
                err_code = auth_res["error"].get("code", "")
                raw_msg = auth_res["error"].get("message", "Authorization failed")
                if "InvalidToken" in err_code:
                    err_msg = "Deriv rejected the token ('Invalid Token'). Please ensure you created the token in Deriv Account Settings with 'Read' and 'Trade' scopes enabled."
                else:
                    err_msg = f"Deriv Auth Error: {raw_msg}"
                self.is_authorized = False
                self.log_activity(err_msg, "error")
                return {"success": False, "error": err_msg}
                
            auth_data = auth_res.get("authorize", {})
            self.is_authorized = True
            self.account_info = {
                "loginid": auth_data.get("loginid"),
                "balance": float(auth_data.get("balance", 0.0)),
                "currency": auth_data.get("currency", "USD"),
                "is_virtual": bool(auth_data.get("is_virtual", 1)),
                "email": auth_data.get("email"),
                "fullname": auth_data.get("fullname"),
            }
            
            # Subscribe to balance updates
            await self._send_request({"balance": 1, "subscribe": 1})
            
            # Subscribe to open contract updates for real-time tracking
            await self._send_request({"proposal_open_contract": 1, "subscribe": 1})
            
            acct_type = "Virtual / Demo" if self.account_info["is_virtual"] else "Real Real-Money"
            self.log_activity(f"Connected & Authorized ({acct_type}): {self.account_info['loginid']} | Balance: ${self.account_info['balance']:.2f} {self.account_info['currency']}", "success")
            
            return {
                "success": True,
                "account": self.account_info,
                "config": self.config,
                "is_auto_trading": self.is_auto_trading_enabled,
            }
            
        except Exception as e:
            self.is_connected = False
            self.is_authorized = False
            self.log_activity(f"Connection failed: {str(e)}", "error")
            return {"success": False, "error": str(e)}

    async def disconnect(self) -> Dict[str, Any]:
        """Safely disconnects from Deriv and disables auto-trading."""
        self._running = False
        self.is_auto_trading_enabled = False
        self.is_authorized = False
        self.is_connected = False
        
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
                
        self.log_activity("Disconnected from Deriv API. Auto-trading disabled.", "info")
        return {"success": True, "message": "Disconnected successfully"}

    def update_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Updates trading parameters and risk management limits."""
        for k, v in new_config.items():
            if k in self.config:
                self.config[k] = v
        if "is_auto_trading_enabled" in new_config:
            self.is_auto_trading_enabled = bool(new_config["is_auto_trading_enabled"])
            status_str = "ENABLED" if self.is_auto_trading_enabled else "DISABLED"
            self.log_activity(f"Auto-Trading switched to: {status_str}", "info")
            
        return {
            "success": True,
            "config": self.config,
            "is_auto_trading_enabled": self.is_auto_trading_enabled,
        }

    async def execute_trade(
        self,
        symbol: str,
        signal_type: str,
        stake: Optional[float] = None,
        duration: Optional[int] = None,
        duration_unit: Optional[str] = None,
        confidence: Optional[float] = None,
        reasons: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Places a CALL (Rise) or PUT (Fall) binary options contract directly on Deriv."""
        if not self.is_authorized or not self.ws:
            return {"success": False, "error": "Not connected or authorized on Deriv"}
            
        deriv_symbol = self.map_symbol(symbol)
        contract_type = "CALL" if signal_type.upper() == "CALL" else "PUT"
        trade_stake = float(stake or self.config.get("default_stake", 10.0))
        trade_duration = int(duration or self.config.get("preferred_duration", 5))
        trade_unit = str(duration_unit or self.config.get("duration_unit", "m"))
        
        # 1. Request Proposal from Deriv
        proposal_req = {
            "proposal": 1,
            "amount": trade_stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": self.account_info.get("currency", "USD"),
            "duration": trade_duration,
            "duration_unit": trade_unit,
            "symbol": deriv_symbol,
        }
        
        self.log_activity(f"Requesting contract proposal: {contract_type} on {deriv_symbol} (${trade_stake} for {trade_duration}{trade_unit})...", "info")
        
        proposal_res = await self._send_request(proposal_req)
        if "error" in proposal_res:
            err_msg = proposal_res["error"].get("message", "Proposal request rejected by Deriv")
            self.log_activity(f"Trade Proposal failed: {err_msg}", "error")
            return {"success": False, "error": err_msg}
            
        proposal_id = proposal_res.get("proposal", {}).get("id")
        payout = proposal_res.get("proposal", {}).get("payout", 0.0)
        ask_price = proposal_res.get("proposal", {}).get("ask_price", trade_stake)
        
        # 2. Buy Contract
        buy_req = {
            "buy": proposal_id,
            "price": ask_price,
        }
        
        buy_res = await self._send_request(buy_req)
        if "error" in buy_res:
            err_msg = buy_res["error"].get("message", "Buy execution rejected by Deriv")
            self.log_activity(f"Buy execution failed: {err_msg}", "error")
            return {"success": False, "error": err_msg}
            
        buy_info = buy_res.get("buy", {})
        contract_id = buy_info.get("contract_id")
        buy_price = float(buy_info.get("buy_price", trade_stake))
        
        # Record into active tracking
        trade_record = {
            "contract_id": contract_id,
            "symbol": symbol,
            "deriv_symbol": deriv_symbol,
            "signal": contract_type,
            "stake": buy_price,
            "payout": payout,
            "duration": f"{trade_duration}{trade_unit}",
            "confidence": confidence or 0,
            "reasons": reasons or [],
            "start_time": int(time.time()),
            "status": "OPEN",
        }
        self.active_contracts[str(contract_id)] = trade_record
        self.total_trades_count += 1
        self.trade_cooldowns[symbol] = time.time()
        
        self.log_activity(
            f"✅ BOUGHT {contract_type} on {deriv_symbol} | Contract ID: {contract_id} | Stake: ${buy_price:.2f} | Potential Payout: ${payout:.2f}",
            "success",
            trade_record
        )
        
        return {
            "success": True,
            "contract_id": contract_id,
            "details": trade_record,
        }

    async def evaluate_auto_trade_signal(self, signal_data: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming market signal and automatically triggers a Deriv contract
        if all risk management and confluence criteria are satisfied.
        """
        if not self.is_auto_trading_enabled:
            return None
            
        if not self.is_authorized or not self.ws:
            return None
            
        sig_type = signal_data.get("signal")
        if sig_type not in ("CALL", "PUT"):
            return None
            
        confidence = float(signal_data.get("confidence", 0))
        min_conf = float(self.config.get("min_confidence", 75))
        if confidence < min_conf:
            return None
            
        # Risk Check: Daily Profit Target
        if self.daily_pnl >= float(self.config.get("take_profit_daily", 50.0)):
            self.log_activity(f"Daily Take-Profit Target (+${self.daily_pnl:.2f}) reached. Auto-trading paused.", "warning")
            self.is_auto_trading_enabled = False
            return None
            
        # Risk Check: Daily Stop Loss
        if self.daily_pnl <= -float(self.config.get("stop_loss_daily", 25.0)):
            self.log_activity(f"Daily Stop-Loss limit (-${abs(self.daily_pnl):.2f}) hit. Auto-trading stopped for protection.", "warning")
            self.is_auto_trading_enabled = False
            return None
            
        # Cooldown check on this asset
        last_trade_time = self.trade_cooldowns.get(symbol, 0)
        cooldown_period = float(self.config.get("cooldown_seconds", 60))
        if time.time() - last_trade_time < cooldown_period:
            return None
            
        # Max concurrent open trades check
        if len(self.active_contracts) >= int(self.config.get("max_concurrent_trades", 3)):
            return None
            
        # Parse suggested trade duration
        duration_str = str(signal_data.get("suggested_trade_time", "5min")).lower()
        if "30s" in duration_str:
            duration = 30
            duration_unit = "s"
        elif "1min" in duration_str or "1m" in duration_str:
            duration = 1
            duration_unit = "m"
        elif "2min" in duration_str or "2m" in duration_str:
            duration = 2
            duration_unit = "m"
        elif "3min" in duration_str or "3m" in duration_str:
            duration = 3
            duration_unit = "m"
        elif "15min" in duration_str:
            duration = 15
            duration_unit = "m"
        else:
            duration = 5
            duration_unit = "m"
            
        self.log_activity(f"🤖 AUTO-SIGNAL TRIGGERED: {sig_type} on {symbol} with {confidence}% confidence. Executing...", "info")
        
        return await self.execute_trade(
            symbol=symbol,
            signal_type=sig_type,
            stake=self.config.get("default_stake", 10.0),
            duration=duration,
            duration_unit=duration_unit,
            confidence=confidence,
            reasons=signal_data.get("reasons", []),
        )

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status of Deriv auto-trader."""
        return {
            "is_connected": self.is_connected,
            "is_authorized": self.is_authorized,
            "is_auto_trading_enabled": self.is_auto_trading_enabled,
            "account": self.account_info,
            "config": self.config,
            "stats": {
                "daily_pnl": round(self.daily_pnl, 2),
                "total_trades": self.total_trades_count,
                "won_trades": self.won_trades_count,
                "lost_trades": self.lost_trades_count,
                "win_rate": round((self.won_trades_count / self.total_trades_count * 100), 1) if self.total_trades_count > 0 else 0.0,
                "active_contracts_count": len(self.active_contracts),
            },
            "active_contracts": list(self.active_contracts.values()),
            "recent_activity": self.activity_log[:20],
        }

    async def _send_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sends request to Deriv WebSocket and awaits matching response."""
        req_id = self._req_id
        self._req_id += 1
        payload["req_id"] = req_id
        
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_requests[req_id] = fut
        
        await self.ws.send(json.dumps(payload))
        
        try:
            res = await asyncio.wait_for(fut, timeout=15)
            return res
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            return {"error": {"message": "WebSocket request timed out after 15s"}}

    async def _listen_loop(self):
        """Asynchronous message dispatcher for Deriv WebSocket streams."""
        while self._running and self.ws:
            try:
                msg_str = await self.ws.recv()
                msg = json.loads(msg_str)
                
                # Match pending request future
                req_id = msg.get("req_id")
                if req_id and req_id in self._pending_requests:
                    fut = self._pending_requests.pop(req_id)
                    if not fut.done():
                        fut.set_result(msg)
                        
                # Handle continuous subscriptions
                msg_type = msg.get("msg_type")
                if msg_type == "balance":
                    bal = msg.get("balance", {})
                    self.account_info["balance"] = float(bal.get("balance", self.account_info["balance"]))
                    self.account_info["currency"] = bal.get("currency", self.account_info["currency"])
                elif msg_type == "proposal_open_contract":
                    poc = msg.get("proposal_open_contract", {})
                    self._handle_open_contract_update(poc)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket listener loop error: {e}")
                await asyncio.sleep(1)

    def _handle_open_contract_update(self, poc: Dict[str, Any]):
        """Processes real-time contract settlement (Win / Loss / Profit update)."""
        contract_id = str(poc.get("contract_id"))
        if contract_id in self.active_contracts:
            is_sold = bool(poc.get("is_sold", 0))
            is_expired = bool(poc.get("is_expired", 0))
            profit = float(poc.get("profit", 0.0))
            status = poc.get("status", "open")
            
            if is_sold or is_expired or status in ("won", "lost"):
                trade = self.active_contracts.pop(contract_id)
                trade["profit"] = profit
                trade["status"] = "WON" if profit > 0 else "LOST"
                
                self.daily_pnl += profit
                if profit > 0:
                    self.won_trades_count += 1
                    self.log_activity(f"🏆 CONTRACT WON! #{contract_id} on {trade['symbol']} | Profit: +${profit:.2f}", "success", trade)
                else:
                    self.lost_trades_count += 1
                    self.log_activity(f"❌ CONTRACT LOST: #{contract_id} on {trade['symbol']} | Loss: -${abs(profit):.2f}", "warning", trade)


# Singleton instance
deriv_trader = DerivAutoTrader()
