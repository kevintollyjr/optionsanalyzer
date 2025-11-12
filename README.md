# Covered Call Scanner & Volatility Richness Analyzer

A production-quality Python application for scanning covered call opportunities and analyzing implied volatility (IV) richness versus historical volatility (HV).

## Features

- **Interactive Streamlit UI** for easy configuration and visualization
- **Live Option Chain Data** fetched via yfinance
- **Volatility Analysis**:
  - Realized (historical) volatility: 1-year, 3-month, and 1-month
  - Implied volatility from option prices
  - IV vs HV comparison metrics (ratio and difference)
  - Richness scoring to identify expensive options
- **Premium Yield Calculations**:
  - Non-annualized premium yield (option premium / stock price)
  - Annualized premium yield for apples-to-apples comparison
- **Flexible Filtering**:
  - Delta range (with Black-Scholes fallback if not provided)
  - Days to expiration (DTE) range
  - OTM-only options
  - Minimum open interest
  - Maximum bid-ask spread percentage
- **Visual Analysis**:
  - Sortable tables highlighting top opportunities
  - Interactive Plotly charts for IV/HV ratios and yields by strike
  - Top N by richness and top N by annualized yield

## Installation

### Requirements

- Python 3.10 or higher
- pip (Python package manager)

### Setup

1. Clone or download this repository:
   ```bash
   cd optionsanalyzer
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

Start the Streamlit app:

```bash
streamlit run app.py
```

The application will open in your default web browser, typically at `http://localhost:8501`.

## Usage Guide

### 1. Input Configuration

#### Tickers
- Enter stock symbols as a comma-separated list in the sidebar
- Example: `MO, APO, LRCX, JPM`
- Tickers are automatically normalized (uppercase, spaces stripped)

#### Delta Range
- **Min Delta** and **Max Delta**: Filter options by their delta values
- Example: 0.15 to 0.30 targets slightly out-of-the-money calls
- Delta represents the probability of the option expiring in-the-money and the rate of change of option price with respect to stock price
- If delta is not provided by the data source, it's computed using Black-Scholes approximation

#### Expiration Range (DTE)
- **Min DTE** and **Max DTE**: Days To Expiration range
- Example: 5 to 90 days focuses on near-term to 3-month options
- Longer DTE typically means more premium but also more time risk

#### Additional Filters

**OTM Only**
- When enabled, only shows out-of-the-money options (strike >= current price for calls)
- Covered call writers typically sell OTM calls to retain upside potential

**Filter by Open Interest**
- Set a minimum open interest threshold (e.g., 100 contracts)
- Higher open interest usually means better liquidity and tighter spreads

**Filter by Bid-Ask Spread**
- Set maximum acceptable spread as a percentage of mid price (e.g., 15%)
- Helps avoid illiquid options with poor pricing

**HV Reference Period**
- Choose which historical volatility to use for IV comparisons:
  - **1y**: 252 trading days (default, most stable)
  - **3m**: ~63 trading days (captures recent trends)
  - **1m**: ~21 trading days (most recent, but can be noisy)

### 2. Running a Scan

1. Configure all inputs in the sidebar
2. Click the **"Run Scan"** button
3. The app will:
   - Fetch current prices for each ticker
   - Download historical price data (1+ year)
   - Compute realized volatility metrics
   - Fetch option chains for relevant expirations
   - Filter and score all options
   - Display results with charts

### 3. Understanding the Results

For each ticker, you'll see:

#### Summary Metrics
- **Current Price**: Latest stock price
- **HV (1Y, 3M, 1M)**: Annualized historical volatility for different periods
- **Options Found**: Number of options matching your filters

#### Top Opportunities by IV Richness
Shows the 5 options with the highest IV/HV ratio (richest implied volatility)

#### Top Opportunities by Annualized Yield
Shows the 5 options with the highest annualized premium yield

#### All Options Table
Expandable table with all matching options, sortable by any column

#### Visualizations

**IV/HV Ratio by Strike**
- Scatter plot showing how rich/cheap each option is
- Color coded by DTE, sized by annualized yield
- Red dashed line at 1.0 represents "fair value" (IV = HV)
- Points above the line are "rich" (IV > HV)

**Annualized Yield by Strike**
- Shows potential return for each option
- Color coded by DTE, sized by IV/HV ratio
- Higher yields at lower strikes (more ITM) but with more downside risk

### 4. Interpreting Key Metrics

#### Volatility Metrics

**IV (Implied Volatility)**
- Market's forward-looking expectation of volatility
- Derived from option prices via the Black-Scholes model
- Higher IV means higher option premiums

**HV (Historical/Realized Volatility)**
- Backward-looking measure of actual price movement
- Computed from log returns of historical prices
- Formula: σ = std(log returns) × √252

**IV/HV Ratio (Richness Score)**
- Primary metric for identifying rich vs cheap options
- **> 1.2**: IV is materially higher than HV (potentially rich)
- **0.8 - 1.2**: IV roughly in line with HV (fair value range)
- **< 0.8**: IV is lower than HV (potentially cheap)

**IV - HV (Difference)**
- Absolute difference in percentage points
- Example: IV = 35%, HV = 25%, difference = +10 percentage points
- Useful for seeing the magnitude of richness, not just the ratio

#### Yield Metrics

**Premium Yield**
- Non-annualized return = option_price / stock_price
- Example: $2.50 option on $100 stock = 2.5% yield

**Annualized Premium Yield**
- Scaled to annual basis for comparison across different DTEs
- Formula: premium_yield × (365 / DTE)
- Example: 2.5% yield for 30 days = 30.4% annualized
- **Important**: This is a theoretical maximum assuming you could repeat the trade continuously
- Does not account for compounding or assignment risk

**Delta**
- Ranges from 0 to 1 for calls
- 0.20 delta ≈ 20% probability of expiring ITM
- Lower delta = farther OTM = less premium but more upside retention

**Moneyness**
- (Strike - Spot) / Spot
- Positive = OTM, Negative = ITM, ~0 = ATM
- Example: $105 strike on $100 stock = +5% moneyness

### 5. Strategy Considerations

**Finding Rich Covered Calls**
Look for options with:
- High IV/HV ratio (> 1.1 or 1.2) indicating rich premiums
- Acceptable annualized yield (e.g., > 20%)
- Delta in your comfort range (0.15-0.30 is common)
- Good liquidity (open interest > 100, spread < 10-15%)

**Trade-offs**
- **Higher IV/HV ratio**: More premium income but may signal upcoming volatility event
- **Higher annualized yield**: Often comes with higher delta (closer to ITM) and more assignment risk
- **Lower delta**: More upside retention but less premium income
- **Shorter DTE**: Higher annualized yields but more frequent rolling/management

**Risk Factors**
- **Assignment risk**: If stock rises above strike, shares will be called away
- **Downside risk**: Premium only provides limited downside protection
- **Opportunity cost**: Capping upside if stock rallies strongly
- **Volatility events**: Earnings, dividends, or news can cause rapid IV changes

## Data Source

The application uses **yfinance** as the default data provider. The data provider is abstracted, so you can easily plug in other sources (e.g., Interactive Brokers, TD Ameritrade) by implementing the `DataProvider` interface in `data_provider.py`.

### Limitations of yfinance
- Real-time data may be delayed 15-20 minutes
- No direct access to Greeks (delta is computed via Black-Scholes)
- Option chains may be incomplete for some tickers
- Historical IV data is not available (only current IV)

For production trading, consider integrating a broker API for real-time, complete data.

## Architecture

### Project Structure

```
optionsanalyzer/
├── app.py                  # Streamlit UI entry point
├── data_provider.py        # Data fetching abstraction layer
├── volatility.py           # Realized volatility calculations
├── options_metrics.py      # Option-specific metrics (yields, delta, filtering)
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

### Module Descriptions

**`data_provider.py`**
- Abstract `DataProvider` base class
- `YFinanceProvider` implementation
- `UnderlyingData` and `OptionContract` data classes
- Handles all external data fetching

**`volatility.py`**
- `compute_realized_volatility()`: Calculate HV from price history
- `compute_volatility_metrics()`: Generate 1Y/3M/1M HV for a ticker
- `compare_iv_to_hv()`: Ratio and difference calculations
- `compute_richness_score()`: Heuristic scoring for IV richness

**`options_metrics.py`**
- `compute_option_metrics()`: Calculate all metrics for one option
- `filter_options()`: Apply delta, DTE, liquidity filters
- `black_scholes_delta()`: Fallback delta calculation
- Yield calculations and formatting utilities

**`app.py`**
- Streamlit UI components
- User input handling
- Data fetching orchestration
- Results display (tables and charts)

## Extending the Application

### Adding a New Data Provider

1. Create a new class that inherits from `DataProvider` in `data_provider.py`
2. Implement all abstract methods:
   - `fetch_underlying_price()`
   - `fetch_historical_prices()`
   - `fetch_option_chain()`
   - `get_available_expirations()`
3. Update `get_default_provider()` or add a configuration option

### Adding New Metrics

1. Add calculation functions to `volatility.py` or `options_metrics.py`
2. Update the `OptionMetrics` dataclass to include new fields
3. Modify `compute_option_metrics()` to calculate the new metrics
4. Update the UI in `app.py` to display them

### Adding Historical IV Analysis

To track IV over time (not just current IV):
1. Store historical option chain snapshots
2. Compute IV percentile rankings
3. Add z-score calculations
4. Enhance richness scoring with percentile-based heuristics

## Troubleshooting

### No options found for a ticker
- Check that the ticker has listed options
- Verify the DTE range includes available expirations
- Try widening the delta range or disabling strict filters

### "Failed to fetch data" errors
- Ensure you have a stable internet connection
- yfinance may experience rate limiting; wait a moment and retry
- Some tickers may not be supported by yfinance
- Try using a different data provider for reliability

### Delta filtering not working
- If delta is not provided by the data source and IV is missing, delta cannot be computed
- Try disabling delta filtering or using a data source that provides Greeks
- Verify the risk-free rate assumption (default 4.5%) is reasonable

### Slow performance
- Fetching option chains for many tickers and expirations is I/O intensive
- Consider reducing the number of tickers per scan
- Consider narrowing the DTE range to fetch fewer expirations
- Use caching if running repeated scans

## License

This project is provided as-is for educational and research purposes.

## Disclaimer

This software is for informational and educational purposes only. It is not financial advice or a recommendation to buy or sell securities. Options trading involves substantial risk and is not suitable for all investors. Past performance does not guarantee future results. Always conduct your own research and consult with a qualified financial advisor before making investment decisions.

## Contributing

Contributions are welcome! Some ideas for enhancements:
- Add support for additional data providers (IBKR, Schwab, etc.)
- Implement historical IV tracking and percentile rankings
- Add earnings date filtering
- Include dividend and ex-dividend date considerations
- Add portfolio-level analysis (aggregate premium, margin requirements)
- Export results to CSV/Excel
- Implement watchlist persistence
- Add backtesting capabilities

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the code comments and docstrings
3. File an issue on the project repository (if applicable)
