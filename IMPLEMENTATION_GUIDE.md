# Implementation Guide for Enhanced Features

## Quick Reference: What to Add

### 1. Data Health Function (Add after `fetch_ticker_data`)

```python
def display_data_health(ticker: str, ticker_data: Dict, all_metrics: List[OptionMetrics]):
    """Display data health indicators for a ticker."""
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']
    options = ticker_data['options']

    st.markdown(f"#### Data Health: {ticker}")

    health_col1, health_col2, health_col3, health_col4 = st.columns(4)

    with health_col1:
        if underlying:
            st.success(f"✓ Underlying: ${underlying.current_price:.2f}")
        else:
            st.error("✗ Underlying fetch failed")

    with health_col2:
        if vol_metrics.data_end_date and vol_metrics.data_start_date:
            days = (vol_metrics.data_end_date - vol_metrics.data_start_date).days
            st.success(f"✓ Historical: {days} days")
        else:
            st.warning("⚠ Limited historical data")

    with health_col3:
        if options:
            st.success(f"✓ Options: {len(options)} contracts")
        else:
            st.error("✗ No options loaded")

    with health_col4:
        # Check IV missing percentage
        total = len(all_metrics)
        iv_missing = sum(1 for m in all_metrics if m.contract.implied_volatility is None)
        if total > 0:
            pct = (iv_missing / total) * 100
            if pct > 0:
                st.warning(f"⚠ IV missing: {pct:.1f}%")
            else:
                st.success("✓ IV complete")
```

### 2. Missing-Data Controls (Add to sidebar in `main()`)

```python
st.sidebar.subheader("Missing Data Handling")

iv_missing_mode = st.sidebar.radio(
    "When IV is missing:",
    options=["Drop option", "Use ATM IV proxy", "Interpolate"],
    index=1,
    help="How to handle options with missing implied volatility"
)

delta_missing_mode = st.sidebar.radio(
    "When Delta is missing:",
    options=["Disable delta filter", "Use Black-Scholes approx"],
    index=1,
    help="How to handle options with missing delta values"
)

if delta_missing_mode == "Use Black-Scholes approx":
    st.sidebar.info("ℹ Using BS approximation for delta")
```

### 3. Cross-Ticker Leaderboard (Add new function)

```python
def display_leaderboard(all_ticker_results: Dict, hv_choice: str, use_bid_yield: bool):
    """Display cross-ticker leaderboard view."""
    st.header("Cross-Ticker Leaderboard")

    # Aggregate all options
    all_options = []
    for ticker, data in all_ticker_results.items():
        underlying = data['ticker_data']['underlying']
        for opt in data['filtered_metrics']:
            if use_bid_yield:
                gross_yield = opt.bid_premium_yield
                ann_yield = opt.bid_annualized_premium_yield
            else:
                gross_yield = opt.premium_yield
                ann_yield = opt.annualized_premium_yield

            moneyness_pct = opt.moneyness * 100 if opt.moneyness else None

            all_options.append({
                'Ticker': ticker,
                'Expiration': opt.contract.expiration.strftime('%Y-%m-%d'),
                'DTE': opt.dte,
                'Strike': opt.contract.strike,
                '% OTM': moneyness_pct,
                'IV': opt.contract.implied_volatility,
                'HV': None,  # Fill in later
                'IV/HV': opt.iv_to_hv_ratio,
                'Richness': opt.richness_score,
                'Gross Yield': gross_yield,
                'Ann. Yield': ann_yield,
                'Delta': opt.computed_delta,
                'OI': opt.contract.open_interest,
                'Volume': opt.contract.volume
            })

    if not all_options:
        st.warning("No options to display in leaderboard")
        return

    df_leader = pd.DataFrame(all_options)

    # Filters
    st.subheader("Leaderboard Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        selected_tickers = st.multiselect(
            "Filter tickers:",
            options=sorted(df_leader['Ticker'].unique()),
            default=sorted(df_leader['Ticker'].unique())
        )

    with filter_col2:
        min_richness = st.number_input("Min Richness (IV/HV)", min_value=0.0, value=1.0, step=0.1)

    with filter_col3:
        min_ann_yield = st.number_input("Min Ann. Yield", min_value=0.0, value=0.0, step=0.05)

    # Apply filters
    df_filtered = df_leader[
        (df_leader['Ticker'].isin(selected_tickers)) &
        (df_leader['Richness'] >= min_richness) &
        (df_leader['Ann. Yield'] >= min_ann_yield)
    ]

    # Display
    st.dataframe(df_filtered, use_container_width=True, height=600)

    # CSV Export
    csv = df_filtered.to_csv(index=False)
    st.download_button(
        label="Download Leaderboard as CSV",
        data=csv,
        file_name=f"leaderboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
```

### 4. CSV Export for Existing Tables (Add after each st.dataframe call)

```python
# After displaying any dataframe:
csv = display_df.to_csv(index=False)
st.download_button(
    label="Download as CSV",
    data=csv,
    file_name=f"{ticker}_top_richness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv",
    key=f"csv_{ticker}_richness"  # Unique key for each button
)
```

## Integration Points

### In `main()` function:

1. **After line 661** (before run_scan check): Add missing-data controls
2. **After line 731** (after display_ticker_results): Call `display_data_health()`
3. **After line 735** (after cross-ticker regression): Call `display_leaderboard()`

### In `display_ticker_results()` function:

1. **After line 337**: Add CSV export for top richness table
2. **After line 363**: Add CSV export for top yield table
3. **After line 367**: Already has CSV in expander, keep it

## Testing Checklist

- [ ] Data health shows for each ticker
- [ ] Missing-data controls appear in sidebar
- [ ] Leaderboard displays all tickers combined
- [ ] Leaderboard filters work correctly
- [ ] CSV exports work for all tables
- [ ] Unique button keys prevent conflicts
- [ ] File downloads with timestamps

## Estimated Lines Added: ~300
## Estimated Time: 30-45 minutes to integrate and test
