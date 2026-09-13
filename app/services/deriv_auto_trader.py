import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List, Callable
import requests
import websockets
from app.services.data_fetcher import fetch_ohlcv_with_source
from app.services.indicators import compute_all_indicators
from app.services.signal_engine import generate_all_signals, detect_asset_type

logger = logging.getLogger("deriv_auto_trader")

DERIV_WS_LEGACY_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"
DERIV_REST_BASE_URL = "https://api.derivws.com"
DEFAULT_DERIV_APP_ID = "34nZu00szxPcV0FfERyJF"
DEFAULT_DERIV_TOKEN = "pat_543859a4eafd961283e1449a6efdb8f1a94a407aaed712a0d513261698888f30"
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "deriv_credentials.json")

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
    
    # Commodities / Metals
    "GOLD": "frxXAUUSD",
    "XAUUSD": "frxXAUUSD",
    "SILVER": "frxXAGUSD",
    "XAGUSD": "frxXAGUSD",
    
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

# Watchlist for 24/7 Autonomous Cloud Scanner
AUTONOMOUS_WATCHLIST = [
    # Synthetic Volatility Indices (100% 24/7/365 Active - Always Open!)
    "R_100", "R_75", "R_50", "1HZ100V", "1HZ75V",
    # Cryptocurrencies (24/7/365 active)
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    # Forex Majors & Crosses (active when forex market is open)
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "GBPAUD",
    # Commodities
    "GOLD", "SILVER",
]


class DerivAutoTrader:
    def __init__(self):
        self.api_token: Optional[str] = None
        self.app_id: str = DEFAULT_DERIV_APP_ID
        self.is_pat_api: bool = False
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
            "default_stake": 1.0,
            "min_confidence": 80,
            "preferred_duration": 5,
            "duration_unit": "m",
            "take_profit_daily": 10.0,
            "stop_loss_daily": 2.0,
            "max_daily_trades": 10,       # Take N number of trades per day
            "max_daily_losses": 2,        # Stop if we get 2 losses
            "max_concurrent_trades": 3,
            "cooldown_seconds": 60,
        }
        
        # Runtime State & Performance
        self.daily_pnl: float = 0.0
        self.total_trades_count: int = 0
        self.won_trades_count: int = 0
        self.lost_trades_count: int = 0
        self.consecutive_losses_count: int = 0
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

    def _sync_get_accounts_and_otp(self, token: str, app_id: str):
        """Synchronous helper for 2026 Options REST API calls."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Deriv-App-ID": app_id,
            "Content-Type": "application/json",
        }
        
        # 1. Fetch accounts
        accts_url = f"{DERIV_REST_BASE_URL}/trading/v1/options/accounts"
        resp = requests.get(accts_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message") or err_data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
            return {"success": False, "error": f"Failed to retrieve Deriv accounts: {err_msg}"}
            
        data = resp.json().get("data", [])
        if not data:
            return {"success": False, "error": "No trading accounts found for this Deriv token/App ID."}
            
        # Select active demo or real account
        selected_acct = None
        for a in data:
            if a.get("status") == "active":
                selected_acct = a
                break
        if not selected_acct:
            selected_acct = data[0]
            
        account_id = selected_acct.get("account_id")
        
        # 2. Fetch WebSocket OTP URL
        otp_url = f"{DERIV_REST_BASE_URL}/trading/v1/options/accounts/{account_id}/otp"
        otp_resp = requests.post(otp_url, headers=headers, timeout=10)
        if otp_resp.status_code != 200:
            err_data = otp_resp.json() if otp_resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message") or f"HTTP {otp_resp.status_code}"
            return {"success": False, "error": f"Failed to generate WebSocket OTP: {err_msg}"}
            
        ws_url = otp_resp.json().get("data", {}).get("url")
        if not ws_url:
            return {"success": False, "error": "No WebSocket OTP URL returned by Deriv"}
            
        return {
            "success": True,
            "account": selected_acct,
            "ws_url": ws_url,
        }

    async def connect(self, token: str, app_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Connects and authorizes with Deriv.
        Supports both the new 2026 Options REST/WebSocket protocol (for Personal Access Tokens)
        and legacy WebSocket tokens.
        """
        clean_token = token.strip().replace('"', '').replace("'", "").replace("\n", "").replace("\r", "").replace(" ", "")
        clean_app_id = (app_id or self.app_id or DEFAULT_DERIV_APP_ID).strip().replace('"', '').replace("'", "").replace(" ", "")
        
        self.api_token = clean_token
        self.app_id = clean_app_id
        self._running = True
        
        try:
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
            
            # Detect whether to use 2026 Options API (PAT tokens or non-numeric App ID)
            use_pat_api = clean_token.startswith("pat_") or len(clean_app_id) > 10
            
            if use_pat_api:
                self.is_pat_api = True
                self.log_activity(f"Authenticating with Deriv 2026 Options API (App ID: {clean_app_id})...", "info")
                
                # Fetch accounts and OTP in threadpool
                auth_res = await asyncio.to_thread(self._sync_get_accounts_and_otp, clean_token, clean_app_id)
                if not auth_res.get("success"):
                    self.is_authorized = False
                    self.is_connected = False
                    err_msg = auth_res.get("error", "Deriv REST authentication failed")
                    self.log_activity(err_msg, "error")
                    return {"success": False, "error": err_msg}
                
                acct = auth_res["account"]
                ws_url = auth_res["ws_url"]
                
                self.account_info = {
                    "loginid": acct.get("account_id"),
                    "balance": float(acct.get("balance", 0.0)),
                    "currency": acct.get("currency", "USD"),
                    "is_virtual": acct.get("account_type") == "demo",
                    "email": None,
                    "fullname": None,
                }
                
                # Connect WebSocket using OTP URL
                self.ws = await websockets.connect(ws_url, ping_interval=30, ping_timeout=10)
                self.is_connected = True
                self.is_authorized = True
                
                # Start message receiving loop
                if self._ws_task and not self._ws_task.done():
                    self._ws_task.cancel()
                self._ws_task = asyncio.create_task(self._listen_loop())
                
                # Subscribe to balance updates
                await self._send_request({"balance": 1, "subscribe": 1})
                
                acct_type = "DEMO" if self.account_info["is_virtual"] else "REAL"
                self.log_activity(
                    f"🟢 Connected & Authorized ({acct_type}): {self.account_info['loginid']} | Balance: ${self.account_info['balance']:.2f} {self.account_info['currency']}",
                    "success"
                )

                # Persist credentials for automatic server reboot recovery
                try:
                    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
                    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                        json.dump({"token": clean_token, "app_id": clean_app_id}, f)
                except Exception:
                    pass
                
                return {
                    "success": True,
                    "account": self.account_info,
                    "config": self.config,
                    "is_auto_trading": self.is_auto_trading_enabled,
                }
            
            else:
                # Legacy WebSocket API Fallback
                self.is_pat_api = False
                legacy_url = f"wss://ws.derivws.com/websockets/v3?app_id={clean_app_id if clean_app_id.isdigit() else 1089}"
                self.log_activity(f"Connecting to Deriv WebSocket API ({legacy_url})...", "info")
                self.ws = await websockets.connect(legacy_url, ping_interval=30, ping_timeout=10)
                self.is_connected = True
                
                if self._ws_task and not self._ws_task.done():
                    self._ws_task.cancel()
                self._ws_task = asyncio.create_task(self._listen_loop())
                
                # Authorize
                auth_res = await self._send_request({"authorize": self.api_token})
                if "error" in auth_res:
                    err_code = auth_res["error"].get("code", "")
                    raw_msg = auth_res["error"].get("message", "Authorization failed")
                    if "InvalidToken" in err_code:
                        err_msg = "Deriv rejected the token ('Invalid Token'). If using a Personal Access Token, ensure App ID is set."
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
                
                await self._send_request({"balance": 1, "subscribe": 1})
                await self._send_request({"proposal_open_contract": 1, "subscribe": 1})
                
                acct_type = "DEMO" if self.account_info["is_virtual"] else "REAL"
                self.log_activity(f"🟢 Connected & Authorized ({acct_type}): {self.account_info['loginid']} | Balance: ${self.account_info['balance']:.2f} {self.account_info['currency']}", "success")
                
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
                
        self.log_activity("Disconnected from Deriv API. Auto-trading paused.", "info")
        return {"success": True, "message": "Disconnected successfully"}

    def update_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Updates trading parameters and risk management limits."""
        for k, v in new_config.items():
            if k in self.config:
                self.config[k] = v
        if "is_auto_trading_enabled" in new_config:
            was_enabled = self.is_auto_trading_enabled
            self.is_auto_trading_enabled = bool(new_config["is_auto_trading_enabled"])
            status_str = "ACTIVE ⚡ (Cloud 24/7)" if self.is_auto_trading_enabled else "PAUSED ⏸️"
            self.log_activity(f"Auto-Trading switched to: {status_str}", "info")

            # Automatically refresh/clear trade history and session stats when starting auto bot
            if self.is_auto_trading_enabled and not was_enabled:
                try:
                    from app.services.trade_manager import trade_manager
                    trade_manager.clear_history()
                    self.daily_pnl = 0.0
                    self.total_trades_count = 0
                    self.won_trades_count = 0
                    self.lost_trades_count = 0
                    self.consecutive_losses_count = 0
                    self.log_activity("🧹 Trade history refreshed for new auto-trading session.", "info")
                except Exception as clear_err:
                    logger.error(f"Error resetting trade history: {clear_err}")

        # Persist config and auto-trading state to file
        try:
            os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
            existing = {}
            if os.path.exists(CREDENTIALS_FILE):
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["is_auto_trading_enabled"] = self.is_auto_trading_enabled
            existing["config"] = self.config
            with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f)
        except Exception:
            pass
            
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
        trade_stake = float(stake or self.config.get("default_stake", 1.0))
        trade_duration = int(duration or self.config.get("preferred_duration", 5))
        trade_unit = str(duration_unit or self.config.get("duration_unit", "m"))
        
        # 1. Request Proposal from Deriv
        # In 2026 Options API, the field is 'underlying_symbol', in legacy it is 'symbol'
        proposal_req = {
            "proposal": 1,
            "amount": trade_stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": self.account_info.get("currency", "USD"),
            "duration": trade_duration,
            "duration_unit": trade_unit,
        }
        
        if self.is_pat_api:
            proposal_req["underlying_symbol"] = deriv_symbol
        else:
            proposal_req["symbol"] = deriv_symbol
        
        self.log_activity(f"Requesting contract proposal: {contract_type} on {deriv_symbol} (${trade_stake} for {trade_duration}{trade_unit})...", "info")
        
        proposal_res = await self._send_request(proposal_req)
        if "error" in proposal_res:
            err_msg = proposal_res["error"].get("message", "Proposal request rejected by Deriv")
            # If rejected due to duration, automatically retry with Deriv standard 5m or 60s
            if "duration" in err_msg.lower():
                alt_duration = 5 if deriv_symbol.startswith("frx") else 60
                alt_unit = "m" if deriv_symbol.startswith("frx") else "s"
                self.log_activity(f"Retrying proposal for {deriv_symbol} with standard {alt_duration}{alt_unit} duration...", "info")
                proposal_req["duration"] = alt_duration
                proposal_req["duration_unit"] = alt_unit
                proposal_res = await self._send_request(proposal_req)
                if "error" in proposal_res:
                    err_msg = proposal_res["error"].get("message", "Proposal request rejected by Deriv")
                    self.log_activity(f"Trade Proposal failed ({deriv_symbol}): {err_msg}", "error")
                    return {"success": False, "error": err_msg}
            else:
                self.log_activity(f"Trade Proposal failed ({deriv_symbol}): {err_msg}", "error")
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
            self.log_activity(f"Buy execution failed ({deriv_symbol}): {err_msg}", "error")
            return {"success": False, "error": err_msg}
            
        buy_info = buy_res.get("buy", {})
        contract_id = buy_info.get("contract_id")
        buy_price = float(buy_info.get("buy_price", trade_stake))
        
        # 3. Subscribe to open contract updates for live settlement tracking
        try:
            await self._send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
                "subscribe": 1,
            })
        except Exception:
            pass
        
        # Extract spot price from proposal if available
        spot_price = proposal_res.get("proposal", {}).get("spot", 0.0)

        # Record into active tracking
        trade_record = {
            "contract_id": contract_id,
            "symbol": symbol,
            "deriv_symbol": deriv_symbol,
            "signal": contract_type,
            "stake": buy_price,
            "payout": payout,
            "spot": spot_price,
            "duration": f"{trade_duration}{trade_unit}",
            "confidence": confidence or 0,
            "reasons": reasons or [],
            "start_time": int(time.time()),
            "status": "OPEN",
        }

        # Register in TradeManager for live UI history table
        try:
            from app.services.trade_manager import trade_manager
            duration_sec = trade_duration * (60 if trade_unit == "m" else (1 if trade_unit == "s" else (3600 if trade_unit == "h" else 2)))
            rate = round((payout - buy_price) / buy_price, 2) if buy_price > 0 else 0.85
            t_obj = trade_manager.create_trade(
                symbol=symbol,
                signal=contract_type,
                entry_price=float(spot_price) if spot_price else 1.0,
                expiry_duration_seconds=duration_sec,
                stake=buy_price,
                payout_rate=rate,
                timeframe=f"{trade_duration}{trade_unit}",
            )
            trade_record["tm_id"] = t_obj["id"]
        except Exception:
            pass

        self.active_contracts[str(contract_id)] = trade_record
        self.total_trades_count += 1
        self.trade_cooldowns[symbol] = time.time()
        
        self.log_activity(
            f"✅ BOUGHT {contract_type} on {deriv_symbol} | ID: #{contract_id} | Stake: ${buy_price:.2f} | Est Payout: ${payout:.2f}",
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
        min_conf = float(self.config.get("min_confidence", 80))
        if confidence < min_conf:
            return None
            
        # Risk Check: Daily Profit Target
        if self.daily_pnl >= float(self.config.get("take_profit_daily", 10.0)):
            self.log_activity(f"🎯 Daily Take-Profit Target (+${self.daily_pnl:.2f}) reached. Auto-trading paused.", "warning")
            self.is_auto_trading_enabled = False
            return None
            
        # Risk Check: Max Losses Limit (Stop if we get 2 losses)
        max_losses = int(self.config.get("max_daily_losses", 2))
        if self.lost_trades_count >= max_losses:
            self.log_activity(f"🛑 Max losses limit reached ({self.lost_trades_count}/{max_losses} losses). Auto-trading stopped for protection.", "warning")
            self.is_auto_trading_enabled = False
            return None

        # Risk Check: Daily Stop Loss Dollar Limit ($2.00)
        if self.daily_pnl <= -float(self.config.get("stop_loss_daily", 2.0)):
            self.log_activity(f"🛑 Daily Stop-Loss limit (-${abs(self.daily_pnl):.2f}) reached. Auto-trading stopped to protect capital.", "warning")
            self.is_auto_trading_enabled = False
            return None

        # Risk Check: N Trades Per Day Quota
        max_trades = int(self.config.get("max_daily_trades", 10))
        if max_trades > 0 and self.total_trades_count >= max_trades:
            self.log_activity(f"🎯 Daily trade quota reached ({self.total_trades_count}/{max_trades} trades). Auto-trading completed for today.", "info")
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
            
        # Standardize duration for Deriv API:
        # Forex & Commodities contracts only accept >= 5m (e.g. 5m, 15m)
        # Synthetics accept 60s or 5m
        deriv_sym = self.map_symbol(symbol)
        duration_str = str(signal_data.get("suggested_trade_time", "5min")).lower()
        if deriv_sym.startswith("frx") or "cry" in deriv_sym:
            duration = 15 if ("15m" in duration_str or "15min" in duration_str) else 5
            duration_unit = "m"
        elif deriv_sym in ("R_100", "R_75", "R_50", "R_25", "R_10", "1HZ100V", "1HZ75V", "1HZ50V", "1HZ25V", "1HZ10V"):
            duration = 60
            duration_unit = "s"
        else:
            duration = 5
            duration_unit = "m"
            
        self.log_activity(f"🤖 AUTO-SIGNAL TRIGGERED: {sig_type} on {symbol} with {confidence}% confidence. Executing...", "info")
        
        return await self.execute_trade(
            symbol=symbol,
            signal_type=sig_type,
            stake=self.config.get("default_stake", 1.0),
            duration=duration,
            duration_unit=duration_unit,
            confidence=confidence,
            reasons=signal_data.get("reasons", []),
        )

    async def on_signal_received(self, symbol: str, signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Public alias for evaluate_auto_trade_signal."""
        return await self.evaluate_auto_trade_signal(signal_data=signal_data, symbol=symbol)

    async def auto_connect_on_startup(self):
        """Auto-connects to Deriv on server launch using saved credentials or default token."""
        token = None
        app_id = DEFAULT_DERIV_APP_ID
        auto_trade = False
        
        try:
            if os.path.exists(CREDENTIALS_FILE):
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("token")
                    app_id = data.get("app_id", DEFAULT_DERIV_APP_ID)
                    auto_trade = bool(data.get("is_auto_trading_enabled", False))
                    if "config" in data and isinstance(data["config"], dict):
                        self.config.update(data["config"])
        except Exception:
            pass
            
        if not token:
            token = DEFAULT_DERIV_TOKEN
            
        if token:
            logger.info(f"Auto-connecting to Deriv on server boot (App ID: {app_id})...")
            try:
                res = await self.connect(token=token, app_id=app_id)
                logger.info(f"Startup Deriv Auto-Connect result: {res.get('success')}")
                if res.get("success") and auto_trade:
                    self.is_auto_trading_enabled = True
                    self.log_activity("Restored Auto-Trading state: ACTIVE ⚡ (Cloud 24/7 Mode)", "info")
            except Exception as e:
                logger.error(f"Startup Deriv Auto-Connect failed: {e}")

    async def run_autonomous_scanner(self):
        """
        Autonomous Cloud Trading Engine:
        Continuously scans market assets and executes Grade A+ trades 24/7 on the cloud
        server even if the user's browser is closed or computer is turned off.
        """
        logger.info("Autonomous Cloud Trading Engine initialized.")
        # Brief warmup delay after server startup
        await asyncio.sleep(6)
        
        while True:
            try:
                if self.is_auto_trading_enabled and self.is_connected and self.is_authorized:
                    for sym in AUTONOMOUS_WATCHLIST:
                        if not self.is_auto_trading_enabled:
                            break
                        try:
                            candles, _ = fetch_ohlcv_with_source(symbol=sym, interval="1m", limit=100)
                            if not candles or len(candles) < 30:
                                continue
                            ind = compute_all_indicators(
                                candles, rsi_period=9, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0
                            )
                            sig_data = generate_all_signals(
                                candles,
                                ind,
                                rsi_oversold=28.0,
                                rsi_overbought=72.0,
                                asset_type=detect_asset_type(sym),
                                engine_version="v4.1",
                                symbol=sym,
                                is_elite_mode=True,
                            )
                            curr_sig = sig_data.get("current", {})
                            if curr_sig.get("signal") in ("CALL", "PUT"):
                                await self.evaluate_auto_trade_signal(curr_sig, sym)
                        except Exception as sym_err:
                            logger.debug(f"Error scanning {sym}: {sym_err}")
                        await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in autonomous scanner loop: {e}")
                
            await asyncio.sleep(25)

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status of Deriv auto-trader."""
        return {
            "is_connected": self.is_connected,
            "is_authorized": self.is_authorized,
            "is_auto_trading_enabled": self.is_auto_trading_enabled,
            "is_pat_api": self.is_pat_api,
            "app_id": self.app_id,
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
                # Auto-reconnect if connection dropped unexpectedly
                if self._running and self.api_token:
                    self.is_connected = False
                    self.is_authorized = False
                    self.log_activity("WebSocket connection dropped. Reconnecting in 3s...", "warning")
                    await asyncio.sleep(3)
                    try:
                        await self.connect(self.api_token, self.app_id)
                    except Exception as re_err:
                        logger.error(f"Auto-reconnect failed: {re_err}")
                else:
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
                
                # Update status in TradeManager
                try:
                    from app.services.trade_manager import trade_manager
                    tm_id = trade.get("tm_id")
                    if tm_id:
                        trade_manager.update_trade_outcome(
                            trade_id=tm_id,
                            outcome="WIN" if profit > 0 else "LOSS",
                        )
                except Exception:
                    pass

                self.daily_pnl += profit
                if profit > 0:
                    self.won_trades_count += 1
                    self.consecutive_losses_count = 0
                    self.log_activity(f"🏆 CONTRACT WON! #{contract_id} on {trade['symbol']} | Profit: +${profit:.2f}", "success", trade)
                else:
                    self.lost_trades_count += 1
                    self.consecutive_losses_count += 1
                    self.log_activity(f"❌ CONTRACT LOST: #{contract_id} on {trade['symbol']} | Loss: -${abs(profit):.2f}", "warning", trade)
                    
                    # Immediate shutdown if 2 losses reached
                    max_losses = int(self.config.get("max_daily_losses", 2))
                    if self.lost_trades_count >= max_losses:
                        self.is_auto_trading_enabled = False
                        self.log_activity(f"🛑 2 LOSSES REACHED ({self.lost_trades_count}/{max_losses})! Auto-trading STOPPED immediately to protect your capital.", "warning")

                # Check if daily trade quota reached
                max_trades = int(self.config.get("max_daily_trades", 10))
                if max_trades > 0 and self.total_trades_count >= max_trades:
                    self.is_auto_trading_enabled = False
                    self.log_activity(f"🎯 Daily trade quota reached ({self.total_trades_count}/{max_trades} trades). Auto-trading finished for today.", "info")


# Singleton instance
deriv_trader = DerivAutoTrader()
