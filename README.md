# ⚡ Quantum Binary - Binary Options Trading Indicator Web Application

A self-hosted binary options trading indicator terminal with automated multi-factor signal generation, real-time interactive TradingView charts, backtesting engine, and live trade countdown execution.

---

## 🌟 Key Features

1. **Multi-Factor Signal Engine**:
   - **RSI (Relative Strength Index)**: Custom period (default 14), overbought (70) and oversold (30) levels.
   - **MACD (Moving Average Convergence Divergence)**: Customizable fast (12), slow (26), and signal (9) lines with colored histogram.
   - **Moving Averages (SMA & EMA)**: Selectable period overlays for trend direction filter.
   - **Bollinger Bands**: Period (20), Standard Deviation multiplier (2.0) with upper/middle/lower bands and %B rejection detection.
   - **CALL / PUT / NEUTRAL Signals**: Evaluated using multi-indicator confirmation, confidence rating (0-100%), entry price, and rationale checklist.

2. **Timeframe Selection**:
   - Instant switching between **1m, 5m, 15m, 30m, 1h, 4h, 1d**.
   - Indicators and signals automatically recalculate instantly upon timeframe change.

3. **Trade Expiry & Real-Time Countdown Timer**:
   - Select expiry durations: **1min, 5min, 15min, 30min, 1hr**.
   - Execute simulated CALL/PUT trades with locked entry price.
   - Live countdown timer with real-time "In the Money" / "Out of the Money" live tracking.
   - Automatic outcome settlement (WIN / LOSS / TIE) upon expiry.

4. **TradingView Lightweight Charts**:
   - High-performance, zoomable candlestick chart.
   - Toggle overlays for Bollinger Bands, SMA, EMA, and Signal arrows on historical candles.
   - Synchronized sub-panes for RSI and MACD.

5. **Historical Point-in-Time Signal Inspector**:
   - Click any past candle on the chart to inspect the exact indicator values and signal generated at that moment without lookahead bias.

6. **Strategy Backtester**:
   - Test strategy performance across 200, 500, or 1000 historical candles.
   - Win Rate %, Net PnL, Profit Factor, Max Win/Loss streaks, and Cumulative Equity Curve graph.

7. **Trade Journal & History**:
   - Persistent logging of all trades, timestamps, entry/exit prices, outcomes, and profit calculations.

---

## 🚀 Quick Start (Localhost Deployment)

### 1. Installation

Ensure Python 3.10+ is installed on your machine.

```bash
# Navigate to the project folder
cd C:\Users\reddy\.gemini\antigravity\scratch\binary-options-indicator

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Application

```bash
# Run server
python run.py
```

or simply double-click `start.bat` on Windows!

### 3. Open in Browser

Open [http://localhost:5000](http://localhost:5000) in your web browser.

---

## 🛠 API Endpoints

- `GET /api/market-data`: Fetches real-time OHLCV candles, computes all indicators, and returns current + historical signals.
- `GET /api/signal-at-time`: Computes signal strictly at a selected historical timestamp.
- `POST /api/backtest`: Executes backtest simulation over historical candles.
- `GET /api/trades`: Returns recorded trades from the journal.
- `POST /api/trades`: Records a new active trade and initiates countdown.
- `POST /api/trades/resolve`: Resolves expired trades against market price.
- `DELETE /api/trades`: Clears trade history.

---

## ⚙ Customizable Strategy Rules

| Indicator | Bullish (CALL) Edge | Bearish (PUT) Edge |
| :--- | :--- | :--- |
| **RSI** | RSI < 30 (Oversold) or crossing up | RSI > 70 (Overbought) or crossing down |
| **MACD** | MACD line crosses above Signal line | MACD line crosses below Signal line |
| **Bollinger Bands** | Price touches or rebounds off Lower Band | Price touches or rejects Upper Band |
| **Moving Average** | Price > EMA/SMA (Bullish Trend Filter) | Price < EMA/SMA (Bearish Trend Filter) |

---

## 📁 Project Structure

```
binary-options-indicator/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI server & REST API
│   ├── services/
│   │   ├── __init__.py
│   │   ├── data_fetcher.py      # Binance market data fetcher & fallback
│   │   ├── indicators.py        # Vectorized RSI, MACD, BB, SMA, EMA
│   │   ├── signal_engine.py     # Multi-factor CALL/PUT signal generator
│   │   ├── backtester.py        # Binary options backtesting simulator
│   │   └── trade_manager.py     # Trade journal & live expiry resolver
│   └── static/
│       ├── index.html           # Trading terminal dashboard UI
│       ├── css/
│       │   └── styles.css       # Dark theme styles & glassmorphism
│       └── js/
│           ├── chart.js         # TradingView Lightweight Charts integration
│           └── app.js           # App controller, timer, polling, modals
├── requirements.txt             # Python dependencies
├── run.py                       # Launch script
├── start.bat                    # One-click start batch file
└── README.md                    # Documentation
```
