import datetime
import logging
import os
import time
from typing import Dict, Any, List, Optional, Tuple
import requests

logger = logging.getLogger("news_filter")

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

SYMBOL_CURRENCIES: Dict[str, List[str]] = {
    "EURUSD": ["EUR", "USD"],
    "GBPJPY": ["GBP", "JPY"],
    "GOLD": ["USD"],
    "XAUUSD": ["USD"],
    "EURGBP": ["EUR", "GBP"],
    "SILVER": ["USD"],
    "XAGUSD": ["USD"],
    "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["USD", "JPY"],
    "AUDUSD": ["AUD", "USD"],
    "USDCAD": ["USD", "CAD"],
    "USDCHF": ["USD", "CHF"],
    "NZDUSD": ["NZD", "USD"],
    "EURJPY": ["EUR", "JPY"],
    "AUDJPY": ["AUD", "JPY"],
    "EURAUD": ["EUR", "AUD"],
    "GBPAUD": ["GBP", "AUD"],
}


class EconomicNewsFilter:
    """
    Institutional Red-Folder Economic News Filter:
    Enforces a strict 30-minute blackout before and 30-minute blackout after
    high-impact economic news releases (CPI, NFP, Central Bank Rate Decisions).
    """

    def __init__(self, blackout_window_minutes: int = 30):
        self.blackout_window_seconds: int = blackout_window_minutes * 60
        self.cached_events: List[Dict[str, Any]] = []
        self.last_fetch_time: float = 0.0
        self.cache_ttl: float = 3600.0  # Refresh every hour
        self._is_enabled: bool = True

    def get_currencies_for_symbol(self, symbol: str) -> List[str]:
        clean = symbol.upper().replace("/", "").replace("-", "")
        return SYMBOL_CURRENCIES.get(clean, ["USD"])

    def fetch_calendar_events(self) -> List[Dict[str, Any]]:
        """Fetches and parses high-impact economic news from ForexFactory public JSON."""
        now = time.time()
        if self.cached_events and (now - self.last_fetch_time < self.cache_ttl):
            return self.cached_events

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutonomousTrader/3.0"}
            resp = requests.get(FF_CALENDAR_URL, headers=headers, timeout=8)
            if resp.status_code == 200:
                raw_events = resp.json()
                parsed = []
                for ev in raw_events:
                    impact = ev.get("impact", "")
                    if impact == "High":
                        date_str = ev.get("date", "")
                        try:
                            dt = datetime.datetime.fromisoformat(date_str)
                            ts = dt.timestamp()
                            parsed.append({
                                "title": ev.get("title", ""),
                                "country": ev.get("country", "").upper(),
                                "impact": impact,
                                "timestamp": ts,
                                "iso_date": date_str,
                            })
                        except Exception:
                            continue
                self.cached_events = parsed
                self.last_fetch_time = now
                logger.info(f"Updated economic calendar: loaded {len(parsed)} High-Impact events.")
                return parsed
        except Exception as e:
            logger.warning(f"Could not fetch ForexFactory calendar: {e}. Using cached events if available.")

        return self.cached_events

    def is_in_news_blackout(
        self,
        symbol: str,
        target_time: Optional[float] = None,
        custom_window_seconds: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Checks if symbol is within 30 minutes before or after high-impact news.
        Returns: (is_blackout: bool, reason: str, event_data: dict)
        """
        if not self._is_enabled:
            return False, None, None

        check_time = target_time if target_time is not None else time.time()
        window = custom_window_seconds if custom_window_seconds is not None else self.blackout_window_seconds
        currencies = set(self.get_currencies_for_symbol(symbol))

        events = self.fetch_calendar_events()
        for ev in events:
            ev_country = ev.get("country")
            if ev_country in currencies:
                ev_time = ev.get("timestamp", 0)
                time_diff = check_time - ev_time
                # Window check: within window seconds before or after
                if -window <= time_diff <= window:
                    mins_diff = abs(int(time_diff // 60))
                    position = "after" if time_diff >= 0 else "before"
                    title = ev.get("title", "High-Impact Event")
                    reason = f"News Blackout Active: {mins_diff}m {position} {ev_country} High-Impact News ('{title}')"
                    return True, reason, ev

        return False, None, None

    def get_upcoming_blackouts(self, hours_ahead: int = 12) -> List[Dict[str, Any]]:
        """Returns list of high-impact events occurring in next N hours."""
        events = self.fetch_calendar_events()
        now = time.time()
        max_time = now + (hours_ahead * 3600)
        upcoming = []
        for ev in events:
            ev_time = ev.get("timestamp", 0)
            if now - 1800 <= ev_time <= max_time:
                mins_left = int((ev_time - now) // 60)
                upcoming.append({
                    **ev,
                    "minutes_until": mins_left,
                    "status": "ACTIVE_BLACKOUT" if abs(mins_left) <= 30 else "UPCOMING",
                })
        return upcoming


# Singleton instance
news_filter = EconomicNewsFilter(blackout_window_minutes=30)
