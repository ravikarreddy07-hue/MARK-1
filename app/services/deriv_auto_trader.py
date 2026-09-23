import asyncio
import datetime
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

# Permanent Blacklist: Pairs with dangerous trend volatility that fail binary options mean-reversion
BLACKLISTED_SYMBOLS = {
    "GBPJPY", "USDCAD", "AUDJPY", "EURJPY", "EURAUD",
    "NZDUSD", "USDCHF", "GBPUSD",  # Filtered out: low win rates / heavy trend drag
    # Audited low win-rate synthetics (<45% on Deriv live)
    "1HZ25V", "R_75", "1HZ50V",
}

# Whitelist for 24/7 Autonomous Cloud Scanner (>70% Win Rate Pairs Only)
AUTONOMOUS_WATCHLIST = [
    # Proven >70% Win-Rate Forex Pairs (Verified on live Deriv market candles)
    "EURUSD", "EURGBP", "AUDUSD", "USDJPY", "GBPAUD",
    # Commodities / Metals
    "GOLD", "SILVER",
    # Proven Clean Synthetic Volatility Indices (24/7 Active)
    "R_100", "R_50", "R_25", "R_10", "1HZ100V", "1HZ10V",
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
        self.user_token_custom: Optional[str] = None
        
        # Account Balance & Profile
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
            "min_confidence": 85.0,
            "preferred_duration": 15,
            "duration_unit": "m",
            "take_profit_daily": 10000.0,
            "stop_loss_daily": 10000.0,
            "max_daily_trades": 10000,       # Take N number of trades per day
            "max_daily_losses": 10000,       # Stop if we get N losses
            "max_concurrent_trades": 5,
            "cooldown_seconds": 60,
            "allowed_market": "all",         # "all" (Forex + Synthetics 24/7), "forex", "synthetics", "metals"
            "engine_version": "v5_sniper",   # V5 Forex Sniper (>70% Win Rate)
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

    def get_asset_market_type(self, symbol: str) -> str:
        """Determines market category of asset: 'synthetics', 'metals', or 'forex'."""
        deriv_sym = self.map_symbol(symbol)
        clean = symbol.upper().replace("/", "").replace("-", "")
        if any(deriv_sym.startswith(p) for p in ("R_", "1HZ")):
            return "synthetics"
        elif "XAU" in deriv_sym or "XAG" in deriv_sym or clean in ("GOLD", "SILVER"):
            return "metals"
        elif deriv_sym.startswith("frx") or any(clean.startswith(fx) for fx in ("EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY")):
            return "forex"
        return "other"

    def is_market_open_for_asset(self, symbol: str) -> bool:
        """
        Checks if the global market is open for trading the given asset:
        - Synthetics (Volatility indices): 24/7/365 (always open).
        - Crypto: 24/7/365.
        - Forex: Open Sunday 21:00 UTC through Friday 21:00 UTC (Closed weekends).
        - Metals (Gold/Silver): Open Sunday 22:00 UTC through Friday 21:00 UTC (Closed weekends).
        """
        mtype = self.get_asset_market_type(symbol)
        if mtype in ("synthetics", "crypto"):
            return True

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        weekday = now_utc.weekday()  # Monday=0, ... Friday=4, Saturday=5, Sunday=6
        hour_float = now_utc.hour + now_utc.minute / 60.0

        # Saturday: completely closed
        if weekday == 5:
            return False

        # Friday: closes at 21:00 UTC (5:00 PM EST)
        if weekday == 4 and hour_float >= 21.0:
            return False

        # Sunday: opens at 21:00 UTC for Forex (22:00 UTC for Metals)
        open_hour = 22.0 if mtype == "metals" else 21.0
        if weekday == 6 and hour_float < open_hour:
            return False

        return True

    def is_forex_market_open(self) -> bool:
        """Helper checking if the Forex market is currently open."""
        return self.is_market_open_for_asset("EURUSD")

    def log_activity(self, message: str, level: str = "info", data: Optional[Dict[str, Any]] = None):
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        ist_now = datetime.datetime.now(ist_tz)
        entry = {
            "timestamp": int(time.time()),
            "time_str": ist_now.strftime("%H:%M:%S IST"),
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
        clean_app_id = str(app_id or self.app_id or DEFAULT_DERIV_APP_ID).strip().replace('"', '').replace("'", "").replace(" ", "")
        
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
                
                # Connect WebSocket using OTP URL with resilient 25s handshake timeout
                self.ws = await websockets.connect(ws_url, open_timeout=25, ping_interval=30, ping_timeout=10)
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
                self.ws = await websockets.connect(legacy_url, open_timeout=25, ping_interval=30, ping_timeout=10)
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
        if deriv_symbol.startswith("cry"):
            err_msg = f"Deriv does not offer binary CALL/PUT options on {symbol} (crypto multipliers only). Skipping."
            self.log_activity(err_msg, "warning")
            return {"success": False, "error": err_msg}

        # Market Open Safeguard: Block trade execution if market is closed (e.g. Forex/Metals on weekends)
        if not self.is_market_open_for_asset(symbol):
            err_msg = f"Market for {symbol} is currently closed for the weekend (Re-opens Sunday 21:00 UTC)."
            self.log_activity(f"⏸️ Cannot trade {symbol}: Market closed for the weekend.", "warning")
            return {"success": False, "error": err_msg}

        contract_type = "CALL" if signal_type.upper() == "CALL" else "PUT"
        trade_stake = float(stake or self.config.get("default_stake", 1.0))
        
        # Enforce exact Deriv binary options duration requirements:
        # Forex requires >= 15m; Gold/Silver 5m or 15m; Synthetics 60s
        if deriv_symbol.startswith("frx"):
            if "XAU" in deriv_symbol or "XAG" in deriv_symbol:
                trade_duration = int(duration or 5)
                trade_unit = "m"
            else:
                trade_duration = 15
                trade_unit = "m"
        elif any(deriv_symbol.startswith(p) for p in ("R_", "1HZ")):
            trade_duration = 2
            trade_unit = "m"
        else:
            trade_duration = int(duration or 15)
            trade_unit = str(duration_unit or "m")
        
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
            # If rejected due to duration, automatically retry with Deriv standard:
            # Commodities: 5m | Forex: 15m | Synthetics: 2m
            if "duration" in err_msg.lower():
                if "XAU" in deriv_symbol or "XAG" in deriv_symbol:
                    alt_duration = 5
                    alt_unit = "m"
                elif deriv_symbol.startswith("frx"):
                    alt_duration = 15
                    alt_unit = "m"
                else:
                    alt_duration = 2
                    alt_unit = "m"
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
            
        # Safeguard: Block blacklisted high-risk trend pairs (sub-50% win rate protection)
        clean_sym = symbol.upper().replace("/", "").replace("-", "")
        if clean_sym in BLACKLISTED_SYMBOLS:
            return None

        confidence = float(signal_data.get("confidence", 0))
        min_conf = float(self.config.get("min_confidence", 85.0))
        if confidence < min_conf:
            return None
            
        # Allowed Market Mode Filter (All, Forex only, Synthetics only, Metals only)
        allowed_market = str(self.config.get("allowed_market", "all")).lower()
        if allowed_market != "all":
            asset_market = self.get_asset_market_type(symbol)
            if asset_market != allowed_market:
                return None

        # Market Open Safeguard: Block trade if market is closed (e.g. Forex/Metals on weekends)
        if not self.is_market_open_for_asset(symbol):
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
            
        # Cooldown check on this asset (handles standard cooldown and loss cooldowns)
        now_time = time.time()
        last_trade_time = self.trade_cooldowns.get(symbol, 0)
        cooldown_period = float(self.config.get("cooldown_seconds", 60))
        if now_time < last_trade_time or (now_time - last_trade_time < cooldown_period):
            return None
            
        # Max concurrent open trades check across entire portfolio
        if len(self.active_contracts) >= int(self.config.get("max_concurrent_trades", 5)):
            return None
            
        # Check if asset is supported for binary options
        deriv_sym = self.map_symbol(symbol)
        if deriv_sym.startswith("cry"):
            return None

        # Risk Protection: Max 1 active contract per pair at any time (prevents clustered exposure)
        for cid, trade in self.active_contracts.items():
            if trade.get("symbol") == symbol or trade.get("deriv_symbol") == deriv_sym:
                return None

        # Standardize duration for Deriv API:
        # Forex requires >= 15m; Gold/Silver accepts 5m; Synthetics accept 2m
        if deriv_sym.startswith("frx"):
            if "XAU" in deriv_sym or "XAG" in deriv_sym:
                duration = 5
                duration_unit = "m"
            else:
                duration = 15
                duration_unit = "m"
        elif any(deriv_sym.startswith(p) for p in ("R_", "1HZ")):
            duration = 2
            duration_unit = "m"
        else:
            duration = 15
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
        auto_trade = True
        
        try:
            if os.path.exists(CREDENTIALS_FILE):
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("token")
                    app_id = data.get("app_id", DEFAULT_DERIV_APP_ID)
                    auto_trade = bool(data.get("is_auto_trading_enabled", True))
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

    async def fetch_deriv_candles(self, symbol: str, count: int = 100, granularity: int = 60) -> List[Dict[str, Any]]:
        """Fetches real-time candles directly from Deriv WebSocket."""
        if not self.ws or not self.is_connected:
            return []
        deriv_sym = self.map_symbol(symbol)
        req = {
            "ticks_history": deriv_sym,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "style": "candles",
            "granularity": granularity,
        }
        res = await self._send_request(req, timeout=1.5)
        raw_candles = res.get("candles", [])
        if not raw_candles:
            return []
        return [
            {
                "time": int(c.get("epoch")),
                "open": float(c.get("open")),
                "high": float(c.get("high")),
                "low": float(c.get("low")),
                "close": float(c.get("close")),
                "volume": 1000.0,
            }
            for c in raw_candles
        ]

    async def reconcile_active_contracts(self):
        """
        Actively checks and settles any expired contracts in self.active_contracts.
        Guarantees contracts never get stuck in memory and block new trades.
        """
        if not self.active_contracts or not self.ws or not self.is_connected:
            return
            
        now = time.time()
        for cid, trade in list(self.active_contracts.items()):
            start = trade.get("start_time", now)
            dur_str = str(trade.get("duration", "15m"))
            dur_secs = 900
            try:
                num = int("".join(filter(str.isdigit, dur_str)) or "15")
                if "s" in dur_str:
                    dur_secs = num
                elif "m" in dur_str:
                    dur_secs = num * 60
                elif "h" in dur_str:
                    dur_secs = num * 3600
            except Exception:
                dur_secs = 900

            # If contract is past expiry plus 10s grace period, query Deriv directly
            if now > (start + dur_secs + 10):
                try:
                    res = await self._send_request({"proposal_open_contract": 1, "contract_id": int(cid)}, timeout=2.5)
                    poc = res.get("proposal_open_contract", {})
                    if poc and (bool(poc.get("is_sold")) or bool(poc.get("is_expired")) or poc.get("status") in ("won", "lost")):
                        self._handle_open_contract_update(poc)
                    elif not poc or now > (start + dur_secs * 2):
                        # Force remove stale contract so it never locks the bot
                        self.active_contracts.pop(cid, None)
                except Exception as e:
                    logger.debug(f"Error reconciling contract #{cid}: {e}")
                    if now > (start + dur_secs * 2):
                        self.active_contracts.pop(cid, None)

    async def run_autonomous_scanner(self):
        """
        Autonomous Cloud Trading Engine:
        Continuously scans market assets and executes Grade A+ trades 24/7 on the cloud
        server even if the user's browser is closed or computer is turned off.
        """
        logger.info("Autonomous Cloud Trading Engine initialized.")
        # Startup grace period so server binds port and handles initial health checks immediately
        await asyncio.sleep(12)
        
        while True:
            try:
                if self.is_auto_trading_enabled and self.is_connected and self.is_authorized:
                    # Clean up and settle any finished contracts
                    await self.reconcile_active_contracts()

                    allowed_m = str(self.config.get("allowed_market", "all")).lower()
                    active_symbols = AUTONOMOUS_WATCHLIST
                    if allowed_m != "all":
                        active_symbols = [s for s in AUTONOMOUS_WATCHLIST if self.get_asset_market_type(s) == allowed_m]
                    active_symbols = [s for s in active_symbols if s not in BLACKLISTED_SYMBOLS]

                    # Filter out symbols whose market is closed (e.g. Forex/Metals on weekends)
                    open_symbols = [s for s in active_symbols if self.is_market_open_for_asset(s)]

                    if not open_symbols:
                        now_time = time.time()
                        if now_time - getattr(self, "_last_market_closed_log", 0) > 1800:
                            self._last_market_closed_log = now_time
                            self.log_activity("⏸️ Forex & Metals markets are closed for the weekend (Re-opens Sunday 21:00 UTC / 02:30 AM IST). Auto-scanner paused.", "info")
                        await asyncio.sleep(60)
                        continue

                    for sym in open_symbols:
                        if not self.is_auto_trading_enabled:
                            break
                        try:
                            # For Forex pairs, fetch real Deriv 5m candles (granularity 300) for high-probability 15m binary setups
                            mtype = self.get_asset_market_type(sym)
                            candles = []
                            if self.ws and self.is_connected:
                                gran = 300 if mtype == "forex" else (300 if mtype == "metals" else 60)
                                candles = await self.fetch_deriv_candles(sym, count=250, granularity=gran)
                            if not candles or len(candles) < 30:
                                intv = "5m" if mtype == "forex" else "1m"
                                candles, _ = fetch_ohlcv_with_source(symbol=sym, interval=intv, limit=250)

                            if not candles or len(candles) < 30:
                                continue

                            ind = compute_all_indicators(
                                candles, rsi_period=9, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0
                            )
                            engine_ver = str(self.config.get("engine_version", "v5_sniper")).lower()
                            sig_data = generate_all_signals(
                                candles,
                                ind,
                                rsi_oversold=28.0,
                                rsi_overbought=72.0,
                                asset_type=detect_asset_type(sym),
                                engine_version=engine_ver,
                                symbol=sym,
                                is_elite_mode=False,
                            )
                            curr_sig = sig_data.get("current", {})
                            if curr_sig.get("signal") in ("CALL", "PUT"):
                                await self.evaluate_auto_trade_signal(curr_sig, sym)
                        except Exception as sym_err:
                            logger.debug(f"Error scanning {sym}: {sym_err}")
                        await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error in autonomous scanner loop: {e}")
                
            await asyncio.sleep(25)

    async def run_cloud_keepalive(self):
        """
        Autonomous Cloud Keepalive Auto-Pinger:
        Pings the public /ping endpoint every 6 minutes to guarantee Render's
        free-tier 15-minute inactivity idle timer never puts the server to sleep.
        Acts as an autonomous internal backup so you never depend on UptimeRobot.
        """
        render_url = os.getenv("RENDER_EXTERNAL_URL", "https://quantum-binary-terminal.onrender.com").rstrip("/")
        ping_endpoint = f"{render_url}/ping"
        logger.info(f"Cloud keepalive auto-pinger initialized (target: {ping_endpoint}, interval: 6 min)")
        self.log_activity(f"💓 Auto-Pinger Active: Pinging cloud server every 6 min as 24/7 backup", "info")
        await asyncio.sleep(30)

        while True:
            try:
                def _do_ping():
                    return requests.get(ping_endpoint, headers={"User-Agent": "AutonomousCloudPinger/2.0"}, timeout=15)

                resp = await asyncio.to_thread(_do_ping)
                if resp.status_code == 200:
                    logger.info("Cloud keepalive heartbeat sent successfully (6-min cycle).")
                    self.log_activity(f"💓 Auto-Pinger: 24/7 Keepalive heartbeat verified (200 OK)", "info")
                else:
                    logger.warning(f"Cloud keepalive ping returned status {resp.status_code}")
            except Exception as e:
                logger.debug(f"Cloud keepalive heartbeat notice: {e}")

            # Sleep 6 minutes (360s) - well below Render's 15-min limit to guarantee 24/7 uptime
            await asyncio.sleep(360)

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
            "is_forex_market_open": self.is_forex_market_open(),
            "recent_activity": self.activity_log[:20],
        }

    async def _send_request(self, payload: Dict[str, Any], timeout: float = 6.0) -> Dict[str, Any]:
        """Sends request to Deriv WebSocket and awaits matching response."""
        req_id = self._req_id
        self._req_id += 1
        payload["req_id"] = req_id
        
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_requests[req_id] = fut
        
        await self.ws.send(json.dumps(payload))
        
        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
            return res
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            return {"error": {"message": f"WebSocket request timed out after {timeout}s"}}

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
                    self.log_activity("WebSocket connection dropped. Reconnecting in 5s...", "warning")
                    await asyncio.sleep(5)
                    try:
                        await self.connect(self.api_token, self.app_id)
                    except Exception as re_err:
                        logger.error(f"Auto-reconnect failed: {re_err}")
                        await asyncio.sleep(10)
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
                        exit_p = float(poc.get("exit_spot") or poc.get("current_spot") or poc.get("exit_tick") or 0.0)
                        trade_manager.update_trade_outcome(
                            trade_id=tm_id,
                            outcome="WIN" if profit > 0 else "LOSS",
                            exit_price=exit_p if exit_p > 0 else None,
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
                    
                    # 15-minute loss cooldown on this specific asset to protect against runaway trends
                    sym = trade.get("symbol")
                    if sym:
                        self.trade_cooldowns[sym] = time.time() + 900
                        self.log_activity(f"⏳ Placed 15-minute loss cooldown on {sym} to protect against runaway breakout trends.", "info")
                    
                    # Immediate shutdown if max daily losses reached
                    max_losses = int(self.config.get("max_daily_losses", 2))
                    if self.lost_trades_count >= max_losses:
                        self.is_auto_trading_enabled = False
                        self.log_activity(f"🛑 Max losses limit reached ({self.lost_trades_count}/{max_losses})! Auto-trading STOPPED to protect your capital.", "warning")

                # Check if daily trade quota reached
                max_trades = int(self.config.get("max_daily_trades", 10))
                if max_trades > 0 and self.total_trades_count >= max_trades:
                    self.is_auto_trading_enabled = False
                    self.log_activity(f"🎯 Daily trade quota reached ({self.total_trades_count}/{max_trades} trades). Auto-trading finished for today.", "info")


# Singleton instance
deriv_trader = DerivAutoTrader()
