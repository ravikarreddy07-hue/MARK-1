// Clear legacy cache keys
try {
    localStorage.removeItem("qb_platform");
    localStorage.removeItem("qb_saved_token");
} catch (e) {}

const TRADE_TIME_SECONDS = {
    "30s": 30,
    "1min": 60,
    "2min": 120,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hr": 3600,
};
const EXPIRY_SECONDS = TRADE_TIME_SECONDS; // Backward compatibility alias

// Curated Market Assets (Major & Cross Forex Pairs, Crypto, Indices, Commodities)
const ASSET_CATALOG = [
    {
        group: "💱 Major Forex Pairs",
        symbols: [
            { value: "EURUSD", tvSymbol: "FX:EURUSD", label: "EUR / USD (Euro / US Dollar)" },
            { value: "GBPUSD", tvSymbol: "FX:GBPUSD", label: "GBP / USD (British Pound / USD)" },
            { value: "USDJPY", tvSymbol: "FX:USDJPY", label: "USD / JPY (US Dollar / Yen)" },
            { value: "AUDUSD", tvSymbol: "FX:AUDUSD", label: "AUD / USD (Aussie / USD)" },
            { value: "USDCAD", tvSymbol: "FX:USDCAD", label: "USD / CAD (USD / Canadian Dollar)" },
            { value: "USDCHF", tvSymbol: "FX:USDCHF", label: "USD / CHF (USD / Swiss Franc)" },
            { value: "NZDUSD", tvSymbol: "FX:NZDUSD", label: "NZD / USD (Kiwi / USD)" },
        ]
    },
    {
        group: "🌐 Cross Forex Pairs",
        symbols: [
            { value: "EURGBP", tvSymbol: "FX:EURGBP", label: "EUR / GBP (Euro / Pound)" },
            { value: "EURJPY", tvSymbol: "FX:EURJPY", label: "EUR / JPY (Euro / Yen)" },
            { value: "GBPJPY", tvSymbol: "FX:GBPJPY", label: "GBP / JPY (Pound / Yen)" },
            { value: "AUDJPY", tvSymbol: "FX:AUDJPY", label: "AUD / JPY (Aussie / Yen)" },
            { value: "EURAUD", tvSymbol: "FX:EURAUD", label: "EUR / AUD (Euro / Aussie)" },
            { value: "GBPAUD", tvSymbol: "FX:GBPAUD", label: "GBP / AUD (Pound / Aussie)" },
            { value: "USDINR", tvSymbol: "FX_IDC:USDINR", label: "USD / INR (USD / Rupee)" },
        ]
    },
    {
        group: "🔥 Top Cryptocurrencies",
        symbols: [
            { value: "BTCUSDT", tvSymbol: "BINANCE:BTCUSDT", label: "BTC / USDT (Bitcoin)" },
            { value: "ETHUSDT", tvSymbol: "BINANCE:ETHUSDT", label: "ETH / USDT (Ethereum)" },
            { value: "SOLUSDT", tvSymbol: "BINANCE:SOLUSDT", label: "SOL / USDT (Solana)" },
            { value: "BNBUSDT", tvSymbol: "BINANCE:BNBUSDT", label: "BNB / USDT (Binance Coin)" },
            { value: "XRPUSDT", tvSymbol: "BINANCE:XRPUSDT", label: "XRP / USDT (Ripple)" },
            { value: "DOGEUSDT", tvSymbol: "BINANCE:DOGEUSDT", label: "DOGE / USDT (Dogecoin)" },
            { value: "ADAUSDT", tvSymbol: "BINANCE:ADAUSDT", label: "ADA / USDT (Cardano)" },
            { value: "AVAXUSDT", tvSymbol: "BINANCE:AVAXUSDT", label: "AVAX / USDT (Avalanche)" },
            { value: "LINKUSDT", tvSymbol: "BINANCE:LINKUSDT", label: "LINK / USDT (Chainlink)" },
            { value: "PEPEUSDT", tvSymbol: "BINANCE:PEPEUSDT", label: "PEPE / USDT (Pepe)" },
            { value: "SHIBUSDT", tvSymbol: "BINANCE:SHIBUSDT", label: "SHIB / USDT (Shiba Inu)" },
            { value: "SUIUSDT", tvSymbol: "BINANCE:SUIUSDT", label: "SUI / USDT (Sui)" },
            { value: "NEARUSDT", tvSymbol: "BINANCE:NEARUSDT", label: "NEAR / USDT (NEAR)" },
            { value: "LTCUSDT", tvSymbol: "BINANCE:LTCUSDT", label: "LTC / USDT (Litecoin)" },
        ]
    },
    {
        group: "🥇 Commodities & Metals",
        symbols: [
            { value: "GOLD", tvSymbol: "TVC:GOLD", label: "Gold (XAU / USD)" },
            { value: "SILVER", tvSymbol: "TVC:SILVER", label: "Silver (XAG / USD)" },
            { value: "USOIL", tvSymbol: "TVC:USOIL", label: "Crude Oil (WTI)" },
        ]
    },
    {
        group: "📈 Global Indices & Equities",
        symbols: [
            { value: "SPX", tvSymbol: "SP:SPX", label: "S&P 500 Index (SPX)" },
            { value: "NDX", tvSymbol: "NASDAQ:NDX", label: "NASDAQ 100 Index (NDX)" },
            { value: "DJI", tvSymbol: "DJ:DJI", label: "Dow Jones Industrial (DJI)" },
            { value: "AAPL", tvSymbol: "NASDAQ:AAPL", label: "Apple Inc. (AAPL)" },
            { value: "TSLA", tvSymbol: "NASDAQ:TSLA", label: "Tesla Inc. (TSLA)" },
            { value: "NVDA", tvSymbol: "NASDAQ:NVDA", label: "NVIDIA Corp (NVDA)" },
            { value: "MSFT", tvSymbol: "NASDAQ:MSFT", label: "Microsoft Corp (MSFT)" },
            { value: "AMZN", tvSymbol: "NASDAQ:AMZN", label: "Amazon.com Inc. (AMZN)" },
        ]
    }
];

function escapeHtml(str) {
    if (typeof str !== "string") return str;
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

class BinaryApp {
    constructor() {
        this.tvManager = new TradingViewChartManager("main-chart-wrapper");
        this.symbol = localStorage.getItem("qb_symbol") || "EURUSD";
        this.tvSymbol = this.lookupTvSymbol(this.symbol);
        this.interval = "1m";
        this.expiryDuration = "5min";
        this.lastPrice = null;
        this.pollInterval = null;
        this.activeTradeTimer = null;
        this.activeTrade = null;

        this.settings = this.loadSettings();
        this.streamFilter = "all";
        this.streamData = [];
        this.init();
    }

    lookupTvSymbol(sym) {
        for (const cat of ASSET_CATALOG) {
            for (const item of cat.symbols) {
                if (item.value.toUpperCase() === sym.toUpperCase()) {
                    return item.tvSymbol;
                }
            }
        }
        if (sym.includes(":")) return sym;
        const forexQuotes = ["USD", "JPY", "EUR", "GBP", "CHF", "CAD", "AUD", "NZD", "INR"];
        if (sym.length === 6 && forexQuotes.some(q => sym.endsWith(q))) {
            return `FX:${sym.toUpperCase()}`;
        }
        return `BINANCE:${sym.toUpperCase()}`;
    }

    loadSettings() {
        const saved = localStorage.getItem("qb_indicator_settings");
        if (saved) {
            try { return JSON.parse(saved); } catch (e) {}
        }
        return {
            rsiPeriod: 9,
            rsiOversold: 28,
            rsiOverbought: 72,
            macdFast: 12,
            macdSlow: 26,
            macdSignal: 9,
            bbPeriod: 20,
            bbStd: 2.0,
            smaPeriod: 20,
            emaPeriod: 50,
            stake: 10.0,
            payoutRate: 0.85,
        };
    }

    saveSettings() {
        localStorage.setItem("qb_indicator_settings", JSON.stringify(this.settings));
    }

    async init() {
        this.populateSymbolDropdown();
        this.tvManager.loadChart(this.tvSymbol, this.interval);
        this.bindEvents();
        this.populateSettingsForm();
        await this.loadMarketData();
        await this.loadTradeHistory();
        await this.loadSignalsStream();
        this.initDerivBot();
        this.startPolling();
    }

    populateSymbolDropdown() {
        const select = document.getElementById("symbol-select");
        if (!select) return;
        select.innerHTML = "";

        ASSET_CATALOG.forEach((grp) => {
            const optGroup = document.createElement("optgroup");
            optGroup.label = grp.group;
            grp.symbols.forEach((s) => {
                const opt = document.createElement("option");
                opt.value = s.value;
                opt.dataset.tv = s.tvSymbol;
                opt.textContent = s.label;
                if (s.value === this.symbol) opt.selected = true;
                optGroup.appendChild(opt);
            });
            select.appendChild(optGroup);
        });
    }

    bindEvents() {
        // Symbol selection change
        const symbolSelect = document.getElementById("symbol-select");
        if (symbolSelect) {
            symbolSelect.addEventListener("change", (e) => {
                this.symbol = e.target.value;
                const selectedOpt = e.target.selectedOptions[0];
                this.tvSymbol = selectedOpt?.dataset?.tv || this.lookupTvSymbol(this.symbol);
                localStorage.setItem("qb_symbol", this.symbol);

                this.tvManager.loadChart(this.tvSymbol, this.interval);
                this.loadMarketData();
            });
        }

        // Custom symbol input
        const customSymbolBtn = document.getElementById("custom-symbol-btn");
        const customSymbolInput = document.getElementById("custom-symbol-input");
        if (customSymbolBtn && customSymbolInput) {
            const handleCustomSymbol = () => {
                const rawVal = customSymbolInput.value.trim().toUpperCase();
                if (rawVal) {
                    this.symbol = rawVal;
                    this.tvSymbol = this.lookupTvSymbol(rawVal);
                    localStorage.setItem("qb_symbol", this.symbol);

                    if (symbolSelect) {
                        let exists = false;
                        for (let i = 0; i < symbolSelect.options.length; i++) {
                            if (symbolSelect.options[i].value === rawVal) {
                                symbolSelect.selectedIndex = i;
                                exists = true;
                                break;
                            }
                        }
                        if (!exists) {
                            const newOpt = document.createElement("option");
                            newOpt.value = rawVal;
                            newOpt.dataset.tv = this.tvSymbol;
                            newOpt.textContent = `⭐ ${rawVal} (TradingView)`;
                            newOpt.selected = true;
                            symbolSelect.insertBefore(newOpt, symbolSelect.firstChild);
                        }
                    }

                    this.tvManager.loadChart(this.tvSymbol, this.interval);
                    this.showToast(`Loaded TradingView Chart: ${this.tvSymbol}`, "info");
                    this.loadMarketData();
                }
            };

            customSymbolBtn.addEventListener("click", handleCustomSymbol);
            customSymbolInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") handleCustomSymbol();
            });
        }

        // Timeframe selector buttons
        document.querySelectorAll(".btn-timeframe").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                document.querySelectorAll(".btn-timeframe").forEach((b) => b.classList.remove("active"));
                e.currentTarget.classList.add("active");
                this.interval = e.currentTarget.dataset.tf;
                this.tvManager.setInterval(this.interval);
                this.loadMarketData();
            });
        });

        // Trade execution buttons
        const btnCall = document.getElementById("btn-execute-call");
        const btnPut = document.getElementById("btn-execute-put");
        if (btnCall) btnCall.addEventListener("click", () => this.executeTrade("CALL"));
        if (btnPut) btnPut.addEventListener("click", () => this.executeTrade("PUT"));

        // Multi-Chart Signals Stream filter buttons
        document.querySelectorAll(".btn-stream-filter").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                document.querySelectorAll(".btn-stream-filter").forEach((b) => b.classList.remove("active"));
                e.currentTarget.classList.add("active");
                this.streamFilter = e.currentTarget.dataset.filter;
                this.renderSignalsStream();
            });
        });

        // Modals
        this.bindModals();
    }

    bindModals() {
        // Settings Modal
        const btnSettings = document.getElementById("btn-open-settings");
        const modalSettings = document.getElementById("modal-settings");
        const closeSettings = document.getElementById("close-settings");
        const formSettings = document.getElementById("settings-form");

        if (btnSettings && modalSettings) {
            btnSettings.addEventListener("click", () => {
                this.populateSettingsForm();
                modalSettings.classList.add("open");
            });
        }
        if (closeSettings && modalSettings) {
            closeSettings.addEventListener("click", () => modalSettings.classList.remove("open"));
        }
        if (formSettings) {
            formSettings.addEventListener("submit", (e) => {
                e.preventDefault();
                this.readSettingsForm();
                this.saveSettings();
                modalSettings.classList.remove("open");
                this.showToast("Settings updated!", "info");
                this.loadMarketData();
            });
        }

        // Backtest Modal
        const btnBacktest = document.getElementById("btn-open-backtest");
        const modalBacktest = document.getElementById("modal-backtest");
        const closeBacktest = document.getElementById("close-backtest");
        const btnRunBacktest = document.getElementById("btn-run-backtest");

        if (btnBacktest && modalBacktest) {
            btnBacktest.addEventListener("click", () => {
                modalBacktest.classList.add("open");
                this.runBacktest();
            });
        }
        if (closeBacktest && modalBacktest) {
            closeBacktest.addEventListener("click", () => modalBacktest.classList.remove("open"));
        }
        if (btnRunBacktest) {
            btnRunBacktest.addEventListener("click", () => this.runBacktest());
        }

        // AI Optimizer Modal
        const btnOptimize = document.getElementById("btn-open-optimize");
        const modalOptimize = document.getElementById("modal-optimize");
        const closeOptimize = document.getElementById("close-optimize");
        const btnRunOptimize = document.getElementById("btn-run-optimize");
        const btnApplyOptimal = document.getElementById("btn-apply-optimal-params");

        if (btnOptimize && modalOptimize) {
            btnOptimize.addEventListener("click", () => {
                modalOptimize.classList.add("open");
            });
        }
        if (closeOptimize && modalOptimize) {
            closeOptimize.addEventListener("click", () => modalOptimize.classList.remove("open"));
        }
        if (btnRunOptimize) {
            btnRunOptimize.addEventListener("click", () => this.runAiOptimizer());
        }
        if (btnApplyOptimal) {
            btnApplyOptimal.addEventListener("click", () => this.applyOptimalParameters());
        }

        // Clear Trade History
        const btnClearTrades = document.getElementById("btn-clear-trades");
        if (btnClearTrades) {
            btnClearTrades.addEventListener("click", async () => {
                if (confirm("Are you sure you want to clear all trade logs?")) {
                    await fetch("/api/trades", { method: "DELETE" });
                    await this.loadTradeHistory();
                    this.showToast("Trade history cleared", "info");
                }
            });
        }
    }

    startPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = setInterval(() => {
            this.loadMarketData(false);
            this.loadSignalsStream();
        }, 4500);
    }

    async loadSignalsStream() {
        try {
            const res = await fetch(`/api/scanner/signals?interval=${this.interval}`);
            if (!res.ok) return;
            const data = await res.json();
            this.streamData = data.signals || [];
            this.renderSignalsStream();
        } catch (e) {
            console.error("Signals stream fetch error:", e);
        }
    }

    renderSignalsStream() {
        const grid = document.getElementById("signals-stream-grid");
        const countBadge = document.getElementById("stream-active-count");
        if (!grid) return;

        let filtered = this.streamData;
        if (this.streamFilter === "high_conf") {
            // Show ONLY Forex pairs with actionable confirmed signals
            filtered = this.streamData.filter((s) => s.market === "Forex" && s.signal !== "NEUTRAL" && s.confidence >= 65);
        } else if (this.streamFilter !== "all") {
            filtered = this.streamData.filter((s) => s.market.toLowerCase() === this.streamFilter.toLowerCase());
        }

        const actionable = this.streamData.filter((s) => s.signal === "CALL" || s.signal === "PUT").length;
        if (countBadge) {
            countBadge.textContent = `${actionable} Active Signals (${this.streamData.length} Live Charts)`;
        }

        grid.innerHTML = "";

        if (filtered.length === 0) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 20px; color: var(--text-secondary); font-size: 12px;">No signals matching this filter right now. Monitoring multi-chart market ticks...</div>`;
            return;
        }

        filtered.forEach((item) => {
            const el = document.createElement("div");
            const sigLower = item.signal.toLowerCase();
            el.className = `stream-signal-item ${sigLower}`;

            const badgeClass = item.signal === "CALL" ? "call" : item.signal === "PUT" ? "put" : "neutral";
            const badgeText = item.signal === "CALL" ? `▲ CALL ${item.confidence}%` : item.signal === "PUT" ? `▼ PUT ${item.confidence}%` : `● CONSOLIDATION`;
            const icon = item.market === "Forex" ? "💱" : item.market === "Crypto" ? "🔥" : item.market === "Commodities" ? "🥇" : "📈";

            const reasonText = item.reasons && item.reasons.length > 0 ? item.reasons[0] : "Confluence Scanning";
            const tradeTimeTag = item.suggested_trade_time === "30s" ? "30 Sec" :
                                 item.suggested_trade_time === "1min" ? "1 Min" :
                                 item.suggested_trade_time === "2min" ? "2 Min" :
                                 item.suggested_trade_time === "3min" ? "3 Min" :
                                 item.suggested_trade_time === "5min" ? "5 Min" :
                                 item.suggested_trade_time === "15min" ? "15 Min" :
                                 item.suggested_trade_time === "30min" ? "30 Min" : "1 Hr";

            el.innerHTML = `
                <div class="stream-item-top">
                    <span class="stream-item-asset">${icon} ${escapeHtml(item.name)}</span>
                    <div style="display: flex; gap: 5px; align-items: center;">
                        <span class="stream-item-time-tag" title="Dynamic AI Suggested Trade Duration">⏱ ${tradeTimeTag}</span>
                        <span class="stream-item-market-tag">${escapeHtml(item.market)}</span>
                    </div>
                </div>
                <div class="stream-item-middle">
                    <span class="stream-item-price">$${Number(item.price).toLocaleString()}</span>
                    <span class="stream-item-badge ${badgeClass}">${badgeText}</span>
                </div>
                <div class="stream-item-footer">
                    <span title="${escapeHtml(reasonText)}" style="max-width: 170px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(reasonText)}</span>
                    <button class="btn-stream-switch" data-sym="${item.symbol}" data-tv="${item.tvSymbol}">📈 Load & Trade</button>
                </div>
            `;

            el.addEventListener("click", (e) => {
                this.switchToAsset(item.symbol, item.tvSymbol);
            });

            grid.appendChild(el);
        });
    }

    switchToAsset(sym, tvSym) {
        this.symbol = sym;
        this.tvSymbol = tvSym || this.lookupTvSymbol(sym);
        localStorage.setItem("qb_symbol", this.symbol);

        const symbolSelect = document.getElementById("symbol-select");
        if (symbolSelect) {
            let exists = false;
            for (let i = 0; i < symbolSelect.options.length; i++) {
                if (symbolSelect.options[i].value === sym) {
                    symbolSelect.selectedIndex = i;
                    exists = true;
                    break;
                }
            }
            if (!exists) {
                const opt = document.createElement("option");
                opt.value = sym;
                opt.dataset.tv = this.tvSymbol;
                opt.textContent = `⭐ ${sym}`;
                opt.selected = true;
                symbolSelect.insertBefore(opt, symbolSelect.firstChild);
            }
        }

        this.tvManager.loadChart(this.tvSymbol, this.interval);
        this.loadMarketData();
        this.showToast(`Switched Chart & Signals to: ${sym} (${this.tvSymbol})`, "win");
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async loadMarketData(showLoading = true) {
        try {
            const params = new URLSearchParams({
                symbol: this.symbol,
                interval: this.interval,
                limit: "100",
                rsi_period: this.settings.rsiPeriod,
                rsi_oversold: this.settings.rsiOversold,
                rsi_overbought: this.settings.rsiOverbought,
                macd_fast: this.settings.macdFast,
                macd_slow: this.settings.macdSlow,
                macd_signal: this.settings.macdSignal,
                bb_period: this.settings.bbPeriod,
                bb_std: this.settings.bbStd,
                sma_period: this.settings.smaPeriod,
                ema_period: this.settings.emaPeriod,
            });

            const res = await fetch(`/api/market-data?${params.toString()}`);
            if (!res.ok) return;

            const data = await res.json();

            if (data.candles && data.candles.length > 0) {
                const latest = data.candles[data.candles.length - 1];
                this.lastPrice = latest.close;
                this.updateHeaderPrice(latest.close);
            }

            if (data.signal) {
                this.updateSignalView(data.signal, this.lastPrice);
            }

            // Auto-resolve pending expired trades
            this.checkAndResolveTrades();
        } catch (err) {
            console.error("Market data poll error:", err);
        }
    }

    updateHeaderPrice(price) {
        const el = document.getElementById("current-price-display");
        const pairEl = document.getElementById("current-pair-display");
        if (el) {
            const digits = price < 5 ? 4 : 2;
            el.textContent = `$${Number(price).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
        }
        if (pairEl) {
            pairEl.textContent = this.symbol;
        }
    }

    updateSignalView(signal, currentPrice) {
        const banner = document.getElementById("signal-state-banner");
        const sigType = document.getElementById("signal-direction-text");
        const sigIcon = document.getElementById("signal-direction-icon");
        const sigConf = document.getElementById("signal-confidence-val");
        const sigEntry = document.getElementById("signal-entry-price");
        const reasonsList = document.getElementById("signal-reasons-list");

        const type = signal.signal || "NEUTRAL";
        const conf = signal.confidence || 0;
        const entry = signal.entry_price || currentPrice;

        const modelBadge = document.getElementById("signal-model-badge");
        if (modelBadge) {
            if (signal.status_label) {
                modelBadge.textContent = signal.status_label;
                modelBadge.style.color = signal.status === "CONFIRMED" ? "var(--call-color)" : (signal.status === "FORMING" ? "#ffca28" : "var(--accent-blue)");
            } else {
                modelBadge.textContent = "V3 AI CONFLUENCE";
            }
        }

        if (banner) {
            banner.className = `signal-banner ${type.toLowerCase()}`;
        }
        if (sigType) sigType.textContent = type === "CALL" ? "CALL / HIGHER" : type === "PUT" ? "PUT / LOWER" : "CONSOLIDATION";
        if (sigIcon) {
            sigIcon.innerHTML = type === "CALL" ? "▲" : type === "PUT" ? "▼" : "◆";
        }
        if (sigConf) sigConf.textContent = `${conf}%`;
        if (sigEntry) {
            const digits = entry < 5 ? 4 : 2;
            sigEntry.textContent = Number(entry).toFixed(digits);
        }

        // Dynamically apply Optimal Suggested Trade Time from confluence engine
        if (signal.suggested_trade_time) {
            this.expiryDuration = signal.suggested_trade_time;
        }

        const badgeVal = document.getElementById("suggested-time-val");
        if (badgeVal) {
            const formatted = this.expiryDuration === "30s" ? "30 Sec" :
                              this.expiryDuration === "1min" ? "1 Min" :
                              this.expiryDuration === "2min" ? "2 Min" :
                              this.expiryDuration === "3min" ? "3 Min" :
                              this.expiryDuration === "5min" ? "5 Min" :
                              this.expiryDuration === "15min" ? "15 Min" :
                              this.expiryDuration === "30min" ? "30 Min" : "1 Hour";
            badgeVal.textContent = formatted;
        }

        this.updateSuggestedTradeTime(signal.suggested_trade_label);

        // Render Reasons list safely
        if (reasonsList) {
            reasonsList.innerHTML = "";
            const reasons = signal.reasons || [];
            if (reasons.length === 0) {
                reasonsList.innerHTML = `<div class="reason-item neutral"><i>●</i> <span>Waiting for multi-indicator confluence</span></div>`;
            } else {
                reasons.forEach((r) => {
                    const cls = type === "CALL" ? "bullish" : type === "PUT" ? "bearish" : "neutral";
                    const icon = type === "CALL" ? "✔" : type === "PUT" ? "▼" : "●";
                    const item = document.createElement("div");
                    item.className = `reason-item ${cls}`;
                    item.innerHTML = `<i>${icon}</i> <span>${escapeHtml(r)}</span>`;
                    reasonsList.appendChild(item);
                });
            }
        }
    }

    updateSuggestedTradeTime(customLabel = null) {
        const expEl = document.getElementById("signal-expiry-time");
        if (!expEl) return;
        const durationSec = TRADE_TIME_SECONDS[this.expiryDuration] || 300;
        const targetDate = new Date(Date.now() + durationSec * 1000);
        const timeStr = targetDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const label = customLabel ? ` (${customLabel})` : ` (${this.expiryDuration})`;
        expEl.textContent = `${timeStr}${label}`;
    }

    async executeTrade(signalType) {
        if (!this.lastPrice) {
            this.showToast("Price data not ready yet", "info");
            return;
        }

        const durationSec = TRADE_TIME_SECONDS[this.expiryDuration] || 300;
        const stakeInput = document.getElementById("trade-stake-input");
        const stake = stakeInput ? parseFloat(stakeInput.value) : this.settings.stake;

        const payload = {
            symbol: this.symbol,
            signal: signalType,
            entry_price: this.lastPrice,
            duration_seconds: durationSec,
            stake: stake,
            payout_rate: this.settings.payoutRate,
            timeframe: this.interval,
        };

        try {
            const res = await fetch("/api/trades", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const trade = await res.json();
            this.activeTrade = trade;
            this.startTradeCountdown(trade);
            await this.loadTradeHistory();
            this.showToast(`✨ ${signalType} Trade Opened @ $${this.lastPrice} (${this.expiryDuration})`, signalType === "CALL" ? "win" : "loss");
        } catch (err) {
            console.error("Execute trade error:", err);
        }
    }

    startTradeCountdown(trade) {
        const countdownBox = document.getElementById("active-trade-box");
        const timerText = document.getElementById("countdown-timer-text");
        const bar = document.getElementById("countdown-progress-bar");
        const activeEntryEl = document.getElementById("active-entry-price");
        const activeSigEl = document.getElementById("active-signal-badge");

        if (countdownBox) countdownBox.style.display = "flex";
        if (activeEntryEl) {
            const digits = trade.entry_price < 5 ? 4 : 2;
            activeEntryEl.textContent = Number(trade.entry_price).toFixed(digits);
        }
        if (activeSigEl) {
            activeSigEl.className = `badge-sig ${trade.signal.toLowerCase()}`;
            activeSigEl.textContent = trade.signal;
        }

        if (this.activeTradeTimer) clearInterval(this.activeTradeTimer);

        const totalDuration = trade.duration_seconds;

        this.activeTradeTimer = setInterval(async () => {
            const now = Math.floor(Date.now() / 1000);
            const remaining = trade.expiry_time - now;

            if (remaining <= 0) {
                clearInterval(this.activeTradeTimer);
                if (timerText) timerText.textContent = "00:00 (Resolving...)";
                if (bar) bar.style.width = "0%";

                await fetch("/api/trades/resolve", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ current_price: this.lastPrice, symbol: trade.symbol }),
                });

                setTimeout(async () => {
                    await this.loadTradeHistory();
                    if (countdownBox) countdownBox.style.display = "none";
                    this.showToast("Trade period completed & settled!", "info");
                }, 1000);
                return;
            }

            const mins = Math.floor(remaining / 60);
            const secs = remaining % 60;
            if (timerText) timerText.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;

            const pct = Math.max(0, Math.min(100, (remaining / totalDuration) * 100));
            if (bar) bar.style.width = `${pct}%`;

            const statusEl = document.getElementById("active-trade-status");
            if (statusEl && this.lastPrice) {
                const diff = this.lastPrice - trade.entry_price;
                const isWinning = trade.signal === "CALL" ? diff > 0 : diff < 0;
                statusEl.innerHTML = `Live Spot: <strong>$${this.lastPrice}</strong> (<span style="color:${isWinning ? 'var(--call-color)' : 'var(--put-color)'}">${diff >= 0 ? '+' : ''}${diff.toFixed(2)}</span>)`;
            }
        }, 1000);
    }

    async checkAndResolveTrades() {
        if (!this.lastPrice) return;
        try {
            await fetch("/api/trades/resolve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ current_price: this.lastPrice, symbol: this.symbol }),
            });
            await this.loadTradeHistory();
        } catch (e) {}
    }

    async loadTradeHistory() {
        try {
            const res = await fetch("/api/trades");
            const trades = await res.json();
            this.renderTradeTable(trades);
        } catch (err) {
            console.error("Load trades error:", err);
        }
    }

    renderTradeTable(trades) {
        const tbody = document.getElementById("trade-history-tbody");
        const winRatePill = document.getElementById("win-rate-pill");
        const pnlDisplay = document.getElementById("net-pnl-display");
        if (!tbody) return;

        tbody.innerHTML = "";

        let wins = 0;
        let closedCount = 0;
        let totalPnl = 0.0;

        trades.forEach((t) => {
            if (t.status === "CLOSED") {
                closedCount++;
                if (t.outcome === "WIN") wins++;
                totalPnl += t.pnl;
            }

            const tr = document.createElement("tr");
            const d = new Date(t.entry_time * 1000);
            const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            const outClass = t.outcome === "WIN" ? "win" : t.outcome === "LOSS" ? "loss" : "tie";
            const pnlClass = t.pnl > 0 ? "win" : t.pnl < 0 ? "loss" : "";

            const durLabel = t.duration_seconds >= 60 ? `${Math.round(t.duration_seconds / 60)}m` : `${t.duration_seconds}s`;

            tr.innerHTML = `
                <td>${timeStr}</td>
                <td><strong>${t.symbol}</strong></td>
                <td><span class="badge-tag">${t.timeframe}</span></td>
                <td><span class="badge-sig ${t.signal.toLowerCase()}">${t.signal}</span></td>
                <td>${durLabel}</td>
                <td>$${Number(t.entry_price).toFixed(2)}</td>
                <td>${t.exit_price ? '$' + Number(t.exit_price).toFixed(2) : '<span style="color:var(--accent-blue)">ACTIVE...</span>'}</td>
                <td><span class="badge-sig ${outClass}">${t.outcome}</span></td>
                <td class="${pnlClass}">${t.pnl >= 0 ? '+' : ''}$${Number(t.pnl).toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });

        if (winRatePill) {
            const wr = closedCount > 0 ? ((wins / closedCount) * 100).toFixed(1) : "--";
            winRatePill.textContent = `Win Rate: ${wr}% (${wins}/${closedCount})`;
        }
        if (pnlDisplay) {
            pnlDisplay.textContent = `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`;
            pnlDisplay.style.color = totalPnl >= 0 ? "var(--call-color)" : "var(--put-color)";
        }
    }

    populateSettingsForm() {
        const fields = ["rsiPeriod", "rsiOversold", "rsiOverbought", "macdFast", "macdSlow", "macdSignal", "bbPeriod", "bbStd", "smaPeriod", "emaPeriod", "stake", "payoutRate"];
        fields.forEach((f) => {
            const input = document.getElementById(`setting-${f}`);
            if (input && this.settings[f] !== undefined) {
                input.value = this.settings[f];
            }
        });
    }

    readSettingsForm() {
        const fields = ["rsiPeriod", "rsiOversold", "rsiOverbought", "macdFast", "macdSlow", "macdSignal", "bbPeriod", "bbStd", "smaPeriod", "emaPeriod", "stake", "payoutRate"];
        fields.forEach((f) => {
            const input = document.getElementById(`setting-${f}`);
            if (input) {
                this.settings[f] = parseFloat(input.value);
            }
        });
    }

    async runBacktest() {
        const limit = document.getElementById("bt-candle-limit")?.value || "500";
        const expiry = document.getElementById("bt-expiry-select")?.value || "5min";

        try {
            const res = await fetch(`/api/backtest?symbol=${this.symbol}&timeframe=${this.interval}&expiry_duration=${expiry}&limit=${limit}&payout_rate=${this.settings.payoutRate}&stake=${this.settings.stake}`);
            const data = await res.json();

            document.getElementById("bt-res-winrate").textContent = `${data.win_rate}%`;
            document.getElementById("bt-res-trades").textContent = `${data.total_trades} (W:${data.wins} / L:${data.losses})`;
            document.getElementById("bt-res-profit").textContent = `$${data.total_profit.toFixed(2)}`;
            document.getElementById("bt-res-profit").style.color = data.total_profit >= 0 ? "var(--call-color)" : "var(--put-color)";
            document.getElementById("bt-res-pf").textContent = data.profit_factor;

            this.drawEquityCurve("equity-curve-canvas", data.equity_curve || []);

            const tbody = document.getElementById("bt-trades-tbody");
            if (tbody) {
                tbody.innerHTML = "";
                (data.trades || []).slice(-50).reverse().forEach((t) => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${new Date(t.entry_time * 1000).toLocaleTimeString()}</td>
                        <td><span class="badge-sig ${t.signal.toLowerCase()}">${t.signal}</span></td>
                        <td>$${t.entry_price.toFixed(2)}</td>
                        <td>$${t.exit_price.toFixed(2)}</td>
                        <td><span class="badge-sig ${t.outcome.toLowerCase()}">${t.outcome}</span></td>
                        <td style="color:${t.pnl >= 0 ? 'var(--call-color)' : 'var(--put-color)'}">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch (e) {
            console.error("Backtest error:", e);
        }
    }

    async runAiOptimizer() {
        const statusEl = document.getElementById("optimize-status-text");
        const btnRun = document.getElementById("btn-run-optimize");
        const btnApply = document.getElementById("btn-apply-optimal-params");

        if (statusEl) statusEl.textContent = "⚙ Training AI models over 1,000 live market candles...";
        if (btnRun) btnRun.disabled = true;

        try {
            const res = await fetch(`/api/optimize?symbol=${this.symbol}&timeframe=${this.interval}&expiry_duration=${this.expiryDuration}&limit=1000`);
            const data = await res.json();

            if (data.error) {
                this.showToast(data.error, "loss");
                if (statusEl) statusEl.textContent = "Optimization failed: " + data.error;
                if (btnRun) btnRun.disabled = false;
                return;
            }

            this.optimalParams = data.optimal_parameters;

            document.getElementById("opt-baseline-winrate").textContent = `${data.baseline_win_rate}%`;
            document.getElementById("opt-optimized-winrate").textContent = `${data.optimized_win_rate}%`;
            document.getElementById("opt-winrate-boost").textContent = `${data.win_rate_boost >= 0 ? '+' : ''}${data.win_rate_boost}%`;

            const p = data.optimal_parameters;
            document.getElementById("opt-params-display").innerHTML = `
                <div>• <strong>RSI Period:</strong> ${p.rsi_period} (Oversold: ${p.rsi_oversold} / Overbought: ${p.rsi_overbought})</div>
                <div>• <strong>MACD:</strong> Fast ${p.macd_fast} / Slow ${p.macd_slow} / Signal ${p.macd_signal}</div>
                <div>• <strong>Bollinger Bands:</strong> Period ${p.bb_period} / StdDev ${p.bb_std}σ</div>
                <div>• <strong>Tested Trades:</strong> ${data.total_trades} | <strong>Net Profit:</strong> $${data.total_profit.toFixed(2)}</div>
            `;

            this.drawEquityCurve("opt-equity-canvas", data.equity_curve || []);

            if (btnApply) btnApply.style.display = "inline-flex";
            if (statusEl) statusEl.textContent = "✅ Optimization complete! Found peak accuracy configuration.";
        } catch (err) {
            console.error("Optimizer error:", err);
            if (statusEl) statusEl.textContent = "Error running optimizer.";
        } finally {
            if (btnRun) btnRun.disabled = false;
        }
    }

    applyOptimalParameters() {
        if (!this.optimalParams) return;
        this.settings.rsiPeriod = this.optimalParams.rsi_period;
        this.settings.rsiOversold = this.optimalParams.rsi_oversold;
        this.settings.rsiOverbought = this.optimalParams.rsi_overbought;
        this.settings.macdFast = this.optimalParams.macd_fast;
        this.settings.macdSlow = this.optimalParams.macd_slow;
        this.settings.macdSignal = this.optimalParams.macd_signal;
        this.settings.bbPeriod = this.optimalParams.bb_period;
        this.settings.bbStd = this.optimalParams.bb_std;

        this.saveSettings();
        this.populateSettingsForm();
        this.loadMarketData();
        document.getElementById("modal-optimize")?.classList.remove("open");
        this.showToast("✨ Applied AI-Optimized Parameters to Live Terminal!", "win");
    }

    drawEquityCurve(canvasId, equityCurve) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !equityCurve || equityCurve.length === 0) return;

        const ctx = canvas.getContext("2d");
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * window.devicePixelRatio;
        canvas.height = rect.height * window.devicePixelRatio;
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

        const width = rect.width;
        const height = rect.height;

        ctx.clearRect(0, 0, width, height);

        const minVal = Math.min(0, ...equityCurve);
        const maxVal = Math.max(10, ...equityCurve);
        const range = maxVal - minVal || 1;

        const getY = (val) => height - 15 - ((val - minVal) / range) * (height - 30);
        const getX = (idx) => 10 + (idx / (equityCurve.length - 1 || 1)) * (width - 20);

        // Zero line
        const zeroY = getY(0);
        ctx.strokeStyle = "rgba(139, 155, 180, 0.25)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, zeroY);
        ctx.lineTo(width, zeroY);
        ctx.stroke();

        // Equity line
        ctx.strokeStyle = equityCurve[equityCurve.length - 1] >= 0 ? "#00e676" : "#ff3d57";
        ctx.lineWidth = 2;
        ctx.beginPath();
        equityCurve.forEach((val, idx) => {
            const x = getX(idx);
            const y = getY(val);
            if (idx === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    // ─── DERIV AUTO-TRADING BOT CONTROLLER ──────────────────────────
    initDerivBot() {
        const btnConnect = document.getElementById("btn-deriv-connect");
        const btnDisconnect = document.getElementById("btn-deriv-disconnect");
        const autoSwitch = document.getElementById("deriv-auto-switch");
        const stakeInput = document.getElementById("deriv-stake-input");
        const confInput = document.getElementById("deriv-conf-input");
        const tpInput = document.getElementById("deriv-tp-input");
        const slInput = document.getElementById("deriv-sl-input");

        // Restore saved token
        const savedToken = localStorage.getItem("qb_deriv_token");
        if (savedToken) {
            const tokenField = document.getElementById("deriv-token-input");
            if (tokenField) tokenField.value = savedToken;
            this.connectDeriv(savedToken);
        }

        btnConnect?.addEventListener("click", () => {
            const token = document.getElementById("deriv-token-input")?.value?.trim();
            if (!token) {
                this.showToast("Please enter your Deriv API Token", "loss");
                return;
            }
            this.connectDeriv(token);
        });

        btnDisconnect?.addEventListener("click", () => {
            this.disconnectDeriv();
        });

        autoSwitch?.addEventListener("change", (e) => {
            const enabled = e.target.checked;
            this.updateDerivConfig({ is_auto_trading_enabled: enabled });
            if (enabled) {
                this.showToast("⚡ Deriv Auto-Trading is now ACTIVE! Bot will execute confirmed signals.", "win");
            } else {
                this.showToast("⏸️ Deriv Auto-Trading PAUSED.", "info");
            }
        });

        [stakeInput, confInput, tpInput, slInput].forEach((inp) => {
            inp?.addEventListener("change", () => {
                this.updateDerivConfig({
                    default_stake: parseFloat(stakeInput?.value || 10),
                    min_confidence: parseInt(confInput?.value || 75),
                    take_profit_daily: parseFloat(tpInput?.value || 50),
                    stop_loss_daily: parseFloat(slInput?.value || 25),
                });
            });
        });

        // Periodic bot status polling
        setInterval(() => this.pollDerivStatus(), 3500);
    }

    async connectDeriv(token) {
        const btnConnect = document.getElementById("btn-deriv-connect");
        if (btnConnect) {
            btnConnect.disabled = true;
            btnConnect.textContent = "Connecting...";
        }

        try {
            const res = await fetch("/api/deriv/connect", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: token }),
            });
            const data = await res.json();

            if (!res.ok || !data.success) {
                this.showToast(data.detail || data.error || "Failed to connect to Deriv", "loss");
                if (btnConnect) {
                    btnConnect.disabled = false;
                    btnConnect.textContent = "Connect";
                }
                return;
            }

            localStorage.setItem("qb_deriv_token", token);
            this.showToast(`✅ Connected to Deriv (${data.account?.is_virtual ? "Demo" : "Real"}: ${data.account?.loginid})`, "win");
            this.pollDerivStatus();
        } catch (e) {
            console.error("Deriv connect error:", e);
            this.showToast("Error connecting to Deriv API", "loss");
        } finally {
            if (btnConnect) {
                btnConnect.disabled = false;
                btnConnect.textContent = "Connect";
            }
        }
    }

    async disconnectDeriv() {
        try {
            await fetch("/api/deriv/disconnect", { method: "POST" });
            localStorage.removeItem("qb_deriv_token");
            this.showToast("Disconnected from Deriv", "info");
            this.pollDerivStatus();
        } catch (e) {
            console.error("Deriv disconnect error:", e);
        }
    }

    async updateDerivConfig(updates) {
        try {
            await fetch("/api/deriv/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(updates),
            });
        } catch (e) {
            console.error("Deriv config update error:", e);
        }
    }

    async pollDerivStatus() {
        try {
            const res = await fetch("/api/deriv/status");
            if (!res.ok) return;
            const data = await res.json();
            this.renderDerivStatus(data);
        } catch (e) {
            // Silently ignore background polling glitches
        }
    }

    renderDerivStatus(data) {
        const authSec = document.getElementById("deriv-auth-section");
        const actSec = document.getElementById("deriv-active-section");
        const statusBadge = document.getElementById("deriv-conn-status");
        const loginEl = document.getElementById("deriv-acct-login");
        const typeEl = document.getElementById("deriv-acct-type");
        const balEl = document.getElementById("deriv-acct-balance");
        const switchEl = document.getElementById("deriv-auto-switch");
        const pnlEl = document.getElementById("deriv-daily-pnl");
        const winrateEl = document.getElementById("deriv-bot-winrate");
        const logEl = document.getElementById("deriv-live-log");

        if (data.is_authorized) {
            if (authSec) authSec.style.display = "none";
            if (actSec) actSec.style.display = "flex";
            if (statusBadge) {
                statusBadge.className = "deriv-status-badge connected";
                statusBadge.textContent = "🟢 Connected";
            }
            if (loginEl) loginEl.textContent = data.account?.loginid || "--";
            if (typeEl) {
                typeEl.className = `deriv-type-pill ${data.account?.is_virtual ? "demo" : "real"}`;
                typeEl.textContent = data.account?.is_virtual ? "DEMO" : "REAL";
            }
            if (balEl) {
                balEl.textContent = `$${Number(data.account?.balance || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${data.account?.currency || "USD"}`;
            }
            if (switchEl) {
                switchEl.checked = data.is_auto_trading_enabled;
            }
            if (pnlEl) {
                const pnl = data.stats?.daily_pnl || 0;
                pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
                pnlEl.style.color = pnl >= 0 ? "var(--call-color)" : "var(--put-color)";
            }
            if (winrateEl) {
                winrateEl.textContent = `${data.stats?.win_rate || 0}% (${data.stats?.won_trades || 0}/${data.stats?.total_trades || 0})`;
            }

            // Render live activity feed
            if (logEl && data.recent_activity && data.recent_activity.length > 0) {
                logEl.innerHTML = data.recent_activity.slice(0, 10).map((a) => {
                    const color = a.level === "success" ? "var(--call-color)" : (a.level === "error" || a.level === "warning" ? "var(--put-color)" : "#8b9bb4");
                    return `<div class="deriv-log-line" style="color: ${color};">[${a.time_str}] ${escapeHtml(a.message)}</div>`;
                }).join("");
            }
        } else {
            if (authSec) authSec.style.display = "flex";
            if (actSec) actSec.style.display = "none";
            if (statusBadge) {
                statusBadge.className = "deriv-status-badge disconnected";
                statusBadge.textContent = "⚪ Disconnected";
            }
        }
    }

    showToast(message, type = "info") {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(8px)";
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
}

// Instantiate application on DOM ready
document.addEventListener("DOMContentLoaded", () => {
    window.binaryApp = new BinaryApp();
});
