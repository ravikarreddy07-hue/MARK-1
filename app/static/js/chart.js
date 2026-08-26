/**
 * Quantum Binary - Official TradingView Advanced Real-Time Chart Integration
 */

class TradingViewChartManager {
    constructor(containerId = "main-chart-wrapper") {
        this.containerId = containerId;
        this.widget = null;
        this.currentSymbol = "BINANCE:BTCUSDT";
        this.currentInterval = "1";
    }

    init() {
        this.loadChart(this.currentSymbol, this.currentInterval);
    }

    mapIntervalToTv(interval) {
        const map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "4h": "240",
            "1d": "D",
        };
        return map[interval] || interval || "1";
    }

    loadChart(tvSymbol, interval = "1m") {
        this.currentSymbol = tvSymbol || this.currentSymbol;
        this.currentInterval = this.mapIntervalToTv(interval);

        const container = document.getElementById(this.containerId);
        if (!container) return;

        container.innerHTML = ""; // Clear existing instance

        // Create internal container
        const innerId = "tv_chart_inner";
        const innerDiv = document.createElement("div");
        innerDiv.id = innerId;
        innerDiv.style.width = "100%";
        innerDiv.style.height = "100%";
        container.appendChild(innerDiv);

        if (typeof TradingView !== "undefined") {
            try {
                this.widget = new TradingView.widget({
                    autosize: true,
                    symbol: this.currentSymbol,
                    interval: this.currentInterval,
                    timezone: "Etc/UTC",
                    theme: "dark",
                    style: "1",
                    locale: "en",
                    toolbar_bg: "#0f131f",
                    enable_publishing: false,
                    allow_symbol_change: true,
                    container_id: innerId,
                    hide_side_toolbar: false,
                    studies: [
                        "RSI@tv-basicstudies",
                        "MASimple@tv-basicstudies",
                        "BB@tv-basicstudies",
                        "MACD@tv-basicstudies"
                    ],
                    overrides: {
                        "paneProperties.background": "#0e1320",
                        "paneProperties.vertGridProperties.color": "rgba(38, 51, 77, 0.4)",
                        "paneProperties.horzGridProperties.color": "rgba(38, 51, 77, 0.4)",
                        "symbolWatermarkProperties.transparency": 90,
                        "scalesProperties.textColor": "#8b9bb4",
                    }
                });
            } catch (e) {
                console.error("TradingView widget init error:", e);
            }
        } else {
            console.warn("TradingView library (tv.js) not loaded yet, retrying in 500ms...");
            setTimeout(() => this.loadChart(this.currentSymbol, this.currentInterval), 500);
        }
    }

    setSymbol(tvSymbol) {
        if (tvSymbol && tvSymbol !== this.currentSymbol) {
            this.currentSymbol = tvSymbol;
            this.loadChart(this.currentSymbol, this.currentInterval);
        }
    }

    setInterval(interval) {
        const tvInt = this.mapIntervalToTv(interval);
        if (tvInt !== this.currentInterval) {
            this.currentInterval = tvInt;
            this.loadChart(this.currentSymbol, this.currentInterval);
        }
    }
}
