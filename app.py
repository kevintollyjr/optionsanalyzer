"""
Covered Call Scanner & Volatility Richness Analyzer

A Streamlit application for scanning covered call opportunities and analyzing
implied volatility richness vs historical volatility.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import plotly.graph_objects as go
import plotly.express as px

from data_provider import get_default_provider, UnderlyingData
from volatility import compute_volatility_metrics, VolatilityMetrics, format_volatility_pct
from options_metrics import (
    compute_option_metrics,
    filter_options,
    OptionMetrics,
    format_percentage,
    format_number
)


# Page configuration
st.set_page_config(
    page_title="Covered Call Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


def parse_tickers(ticker_input: str) -> List[str]:
    """
    Parse comma-separated ticker input and normalize.

    Args:
        ticker_input: Comma-separated string of tickers

    Returns:
        List of normalized ticker symbols (uppercase, stripped)
    """
    if not ticker_input:
        return []

    tickers = [t.strip().upper() for t in ticker_input.split(',')]
    return [t for t in tickers if t]  # Remove empty strings


def fetch_ticker_data(
    ticker: str,
    provider,
    min_dte: int,
    max_dte: int,
    progress_callback=None
) -> Optional[Dict]:
    """
    Fetch all data for a single ticker.

    Returns a dictionary with:
    - underlying: UnderlyingData
    - volatility: VolatilityMetrics
    - options: List[OptionContract]
    """
    try:
        if progress_callback:
            progress_callback(f"Fetching {ticker} underlying price...")

        # Fetch underlying data
        underlying = provider.fetch_underlying_price(ticker)

        if progress_callback:
            progress_callback(f"Fetching {ticker} historical prices...")

        # Fetch historical prices (1 year + buffer)
        end_date = date.today()
        start_date = end_date - timedelta(days=400)
        historical_prices = provider.fetch_historical_prices(ticker, start_date, end_date)

        if progress_callback:
            progress_callback(f"Computing {ticker} volatility metrics...")

        # Compute volatility metrics
        vol_metrics = compute_volatility_metrics(ticker, historical_prices, underlying.current_price)

        if progress_callback:
            progress_callback(f"Fetching {ticker} option expirations...")

        # Get available expirations
        all_expirations = provider.get_available_expirations(ticker)

        # Filter expirations by DTE
        today = date.today()
        filtered_expirations = [
            exp for exp in all_expirations
            if min_dte <= (exp - today).days <= max_dte
        ]

        if not filtered_expirations:
            st.warning(f"{ticker}: No expirations in DTE range {min_dte}-{max_dte} days")
            return None

        if progress_callback:
            progress_callback(f"Fetching {ticker} option chains ({len(filtered_expirations)} expirations)...")

        # Fetch option chains
        options = provider.fetch_option_chain(ticker, filtered_expirations)

        if not options:
            st.warning(f"{ticker}: No options data available")
            return None

        return {
            'underlying': underlying,
            'volatility': vol_metrics,
            'options': options
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {str(e)}")
        return None


def process_ticker_options(
    ticker_data: Dict,
    min_delta: Optional[float],
    max_delta: Optional[float],
    min_dte: int,
    max_dte: int,
    otm_only: bool,
    min_open_interest: Optional[int],
    max_spread_pct: Optional[float],
    hv_choice: str
) -> List[OptionMetrics]:
    """
    Process options for a ticker and compute metrics.

    Args:
        ticker_data: Dictionary from fetch_ticker_data
        hv_choice: Which HV to use for comparison ('1y', '3m', or '1m')
    """
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']
    options = ticker_data['options']

    # Select HV reference based on user choice
    if hv_choice == '3m':
        hv_reference = vol_metrics.hv_3m
    elif hv_choice == '1m':
        hv_reference = vol_metrics.hv_1m
    else:  # default to 1y
        hv_reference = vol_metrics.hv_1y

    # Compute metrics for all options
    option_metrics = []
    for contract in options:
        metrics = compute_option_metrics(
            contract=contract,
            underlying_price=underlying.current_price,
            hv_reference=hv_reference
        )
        option_metrics.append(metrics)

    # Apply filters
    filtered_metrics = filter_options(
        option_metrics=option_metrics,
        min_delta=min_delta,
        max_delta=max_delta,
        min_dte=min_dte,
        max_dte=max_dte,
        otm_only=otm_only,
        min_open_interest=min_open_interest,
        max_spread_pct=max_spread_pct,
        underlying_price=underlying.current_price
    )

    return filtered_metrics


def create_options_dataframe(option_metrics: List[OptionMetrics], hv_label: str) -> pd.DataFrame:
    """
    Convert list of OptionMetrics to a DataFrame for display.
    """
    if not option_metrics:
        return pd.DataFrame()

    rows = []
    for opt in option_metrics:
        row = {
            'Expiration': opt.contract.expiration.strftime('%Y-%m-%d'),
            'DTE': opt.dte,
            'Strike': opt.contract.strike,
            'Bid': opt.contract.bid,
            'Ask': opt.contract.ask,
            'Mid': opt.option_price,
            'IV': opt.contract.implied_volatility,
            f'{hv_label}': None,  # Will be filled from vol_metrics
            'IV/HV': opt.iv_to_hv_ratio,
            'IV-HV': opt.iv_minus_hv,
            'Richness': opt.richness_score,
            'Premium Yield': opt.premium_yield,
            'Ann. Yield': opt.annualized_premium_yield,
            'Delta': opt.computed_delta,
            'Moneyness': opt.moneyness,
            'OI': opt.contract.open_interest,
            'Volume': opt.contract.volume,
            'Spread %': opt.bid_ask_spread_pct,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Sort by richness score by default (descending)
    if 'Richness' in df.columns:
        df = df.sort_values('Richness', ascending=False)

    return df


def display_ticker_results(
    ticker: str,
    ticker_data: Dict,
    filtered_metrics: List[OptionMetrics],
    hv_choice: str
):
    """
    Display results for a single ticker.
    """
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']

    st.header(f"📈 {ticker}")

    # Display underlying and volatility info
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Current Price", f"${underlying.current_price:.2f}")

    with col2:
        hv_1y_str = format_volatility_pct(vol_metrics.hv_1y) if vol_metrics.hv_1y else "N/A"
        st.metric("HV (1Y)", hv_1y_str)

    with col3:
        hv_3m_str = format_volatility_pct(vol_metrics.hv_3m) if vol_metrics.hv_3m else "N/A"
        st.metric("HV (3M)", hv_3m_str)

    with col4:
        hv_1m_str = format_volatility_pct(vol_metrics.hv_1m) if vol_metrics.hv_1m else "N/A"
        st.metric("HV (1M)", hv_1m_str)

    with col5:
        st.metric("Options Found", len(filtered_metrics))

    if not filtered_metrics:
        st.warning(f"No options meet the filter criteria for {ticker}")
        return

    # Get HV label based on user choice
    hv_labels = {'1y': 'HV_1Y', '3m': 'HV_3M', '1m': 'HV_1M'}
    hv_label = hv_labels.get(hv_choice, 'HV_1Y')

    # Get reference HV value
    hv_ref = None
    if hv_choice == '3m':
        hv_ref = vol_metrics.hv_3m
    elif hv_choice == '1m':
        hv_ref = vol_metrics.hv_1m
    else:
        hv_ref = vol_metrics.hv_1y

    # Create main dataframe
    df = create_options_dataframe(filtered_metrics, hv_label)

    # Fill in HV column with the reference value
    if hv_ref is not None:
        df[hv_label] = hv_ref

    # Display top opportunities
    st.subheader("🎯 Top Opportunities by IV Richness")
    top_by_richness = df.nlargest(5, 'Richness') if 'Richness' in df.columns and not df['Richness'].isna().all() else df.head(5)

    # Format for display
    display_cols = ['Expiration', 'DTE', 'Strike', 'Mid', 'IV', hv_label, 'IV/HV', 'Richness', 'Ann. Yield', 'Delta']
    display_df = top_by_richness[display_cols].copy()

    # Format numeric columns
    if 'IV' in display_df.columns:
        display_df['IV'] = display_df['IV'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if hv_label in display_df.columns:
        display_df[hv_label] = display_df[hv_label].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'IV/HV' in display_df.columns:
        display_df['IV/HV'] = display_df['IV/HV'].apply(lambda x: format_number(x, 2) if pd.notna(x) else 'N/A')
    if 'Richness' in display_df.columns:
        display_df['Richness'] = display_df['Richness'].apply(lambda x: format_number(x, 2) if pd.notna(x) else 'N/A')
    if 'Ann. Yield' in display_df.columns:
        display_df['Ann. Yield'] = display_df['Ann. Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Delta' in display_df.columns:
        display_df['Delta'] = display_df['Delta'].apply(lambda x: format_number(x, 3) if pd.notna(x) else 'N/A')

    st.dataframe(display_df, use_container_width=True)

    st.subheader("💰 Top Opportunities by Annualized Yield")
    top_by_yield = df.nlargest(5, 'Ann. Yield') if 'Ann. Yield' in df.columns and not df['Ann. Yield'].isna().all() else df.head(5)

    display_df_yield = top_by_yield[display_cols].copy()

    # Format numeric columns
    if 'IV' in display_df_yield.columns:
        display_df_yield['IV'] = display_df_yield['IV'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if hv_label in display_df_yield.columns:
        display_df_yield[hv_label] = display_df_yield[hv_label].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'IV/HV' in display_df_yield.columns:
        display_df_yield['IV/HV'] = display_df_yield['IV/HV'].apply(lambda x: format_number(x, 2) if pd.notna(x) else 'N/A')
    if 'Richness' in display_df_yield.columns:
        display_df_yield['Richness'] = display_df_yield['Richness'].apply(lambda x: format_number(x, 2) if pd.notna(x) else 'N/A')
    if 'Ann. Yield' in display_df_yield.columns:
        display_df_yield['Ann. Yield'] = display_df_yield['Ann. Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Delta' in display_df_yield.columns:
        display_df_yield['Delta'] = display_df_yield['Delta'].apply(lambda x: format_number(x, 3) if pd.notna(x) else 'N/A')

    st.dataframe(display_df_yield, use_container_width=True)

    # Full data table
    with st.expander(f"📋 All {len(df)} Options (Sortable Table)"):
        st.dataframe(df, use_container_width=True, height=400)

    # Charts
    st.subheader("📊 Visualizations")

    col1, col2 = st.columns(2)

    with col1:
        # IV/HV Ratio vs Strike
        if not df.empty and 'Strike' in df.columns and 'IV/HV' in df.columns:
            fig_richness = px.scatter(
                df.dropna(subset=['IV/HV']),
                x='Strike',
                y='IV/HV',
                color='DTE',
                size='Ann. Yield',
                hover_data=['Expiration', 'Mid', 'Ann. Yield'],
                title=f'{ticker}: IV/HV Ratio by Strike',
                labels={'IV/HV': 'IV/HV Ratio', 'Strike': 'Strike Price'}
            )
            fig_richness.add_hline(y=1.0, line_dash="dash", line_color="red",
                                   annotation_text="Fair Value (IV=HV)")
            st.plotly_chart(fig_richness, use_container_width=True)

    with col2:
        # Annualized Yield vs Strike
        if not df.empty and 'Strike' in df.columns and 'Ann. Yield' in df.columns:
            df_yield_chart = df.dropna(subset=['Ann. Yield']).copy()
            df_yield_chart['Ann. Yield %'] = df_yield_chart['Ann. Yield'] * 100

            fig_yield = px.scatter(
                df_yield_chart,
                x='Strike',
                y='Ann. Yield %',
                color='DTE',
                size='IV/HV',
                hover_data=['Expiration', 'Mid', 'IV/HV'],
                title=f'{ticker}: Annualized Yield by Strike',
                labels={'Ann. Yield %': 'Annualized Yield (%)', 'Strike': 'Strike Price'}
            )
            st.plotly_chart(fig_yield, use_container_width=True)

    st.divider()


def main():
    """Main Streamlit application."""

    st.title("📊 Covered Call Scanner & Volatility Richness Analyzer")

    st.markdown("""
    Scan covered call opportunities and analyze implied volatility richness vs historical volatility.
    Find where IV looks rich compared to realized volatility, and identify attractive premium yields.
    """)

    # Sidebar - Input Controls
    st.sidebar.header("⚙️ Configuration")

    # Ticker input
    ticker_input = st.sidebar.text_input(
        "Tickers (comma-separated)",
        value="",
        help="Enter stock tickers separated by commas, e.g., MO, APO, LRCX, JPM"
    )

    st.sidebar.subheader("Delta Range")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_delta = st.number_input("Min Delta", min_value=0.0, max_value=1.0, value=0.15, step=0.05)
    with col2:
        max_delta = st.number_input("Max Delta", min_value=0.0, max_value=1.0, value=0.30, step=0.05)

    st.sidebar.subheader("Expiration Range (DTE)")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        min_dte = st.number_input("Min DTE", min_value=1, max_value=730, value=5, step=1)
    with col4:
        max_dte = st.number_input("Max DTE", min_value=1, max_value=730, value=90, step=1)

    st.sidebar.subheader("Additional Filters")

    otm_only = st.sidebar.checkbox("OTM Only", value=True, help="Only show out-of-the-money options")

    enable_oi_filter = st.sidebar.checkbox("Filter by Open Interest", value=True)
    min_open_interest = None
    if enable_oi_filter:
        min_open_interest = st.sidebar.number_input("Min Open Interest", min_value=0, value=100, step=10)

    enable_spread_filter = st.sidebar.checkbox("Filter by Bid-Ask Spread", value=True)
    max_spread_pct = None
    if enable_spread_filter:
        max_spread_pct = st.sidebar.number_input("Max Spread %", min_value=0.0, max_value=100.0, value=15.0, step=1.0)

    st.sidebar.subheader("Volatility Comparison")
    hv_choice = st.sidebar.selectbox(
        "HV Reference Period",
        options=['1y', '3m', '1m'],
        index=0,
        help="Which historical volatility period to use for IV comparisons"
    )

    # Run button
    run_scan = st.sidebar.button("🔍 Run Scan", type="primary", use_container_width=True)

    # Main content area
    if run_scan:
        tickers = parse_tickers(ticker_input)

        if not tickers:
            st.error("Please enter at least one ticker symbol")
            return

        st.info(f"Scanning {len(tickers)} ticker(s): {', '.join(tickers)}")

        # Initialize data provider
        provider = get_default_provider()

        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Fetch data for all tickers
        results = {}

        for idx, ticker in enumerate(tickers):
            status_text.text(f"Processing {ticker}...")

            ticker_data = fetch_ticker_data(
                ticker=ticker,
                provider=provider,
                min_dte=min_dte,
                max_dte=max_dte,
                progress_callback=lambda msg: status_text.text(msg)
            )

            if ticker_data:
                results[ticker] = ticker_data

            progress_bar.progress((idx + 1) / len(tickers))

        status_text.empty()
        progress_bar.empty()

        if not results:
            st.error("No data could be fetched for any tickers")
            return

        st.success(f"Successfully fetched data for {len(results)} ticker(s)")

        # Process and display results for each ticker
        for ticker, ticker_data in results.items():
            filtered_metrics = process_ticker_options(
                ticker_data=ticker_data,
                min_delta=min_delta,
                max_delta=max_delta,
                min_dte=min_dte,
                max_dte=max_dte,
                otm_only=otm_only,
                min_open_interest=min_open_interest,
                max_spread_pct=max_spread_pct,
                hv_choice=hv_choice
            )

            display_ticker_results(ticker, ticker_data, filtered_metrics, hv_choice)

    else:
        # Show instructions when not running
        st.info("👈 Enter tickers and configure filters in the sidebar, then click 'Run Scan'")

        st.subheader("📖 How to Use")

        st.markdown("""
        ### Input Configuration
        1. **Tickers**: Enter comma-separated stock symbols (e.g., `MO, APO, LRCX`)
        2. **Delta Range**: Filter options by delta (e.g., 0.15 to 0.30 for slightly OTM)
        3. **DTE Range**: Days to expiration range (e.g., 5 to 90 days)
        4. **Additional Filters**:
           - OTM Only: Only show out-of-the-money options
           - Min Open Interest: Ensure liquidity
           - Max Bid-Ask Spread: Avoid wide markets

        ### Understanding the Results

        **Volatility Metrics:**
        - **IV (Implied Volatility)**: Market's expectation of future volatility
        - **HV (Historical Volatility)**: Realized volatility from past price movements
        - **IV/HV Ratio**: Shows relative richness
          - > 1.0: IV is higher than HV (potentially rich/expensive)
          - = 1.0: IV equals HV (fair value)
          - < 1.0: IV is lower than HV (potentially cheap)
        - **Richness Score**: Same as IV/HV ratio - higher means richer IV

        **Yield Metrics:**
        - **Premium Yield**: Option premium / stock price (non-annualized)
        - **Annualized Yield**: Premium yield scaled to annual rate
          - Formula: Premium Yield × (365 / DTE)
          - Represents potential annualized return if option expires worthless

        **What to Look For:**
        - High IV/HV ratios (>1.2) suggest rich option premiums
        - High annualized yields with acceptable delta
        - Combination of both: rich IV + attractive yield = potential covered call opportunity
        """)


if __name__ == "__main__":
    main()
