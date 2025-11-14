"""
Covered Call Scanner & Volatility Richness Analyzer

A professional-grade Streamlit application for scanning covered call opportunities
and analyzing implied volatility richness vs historical volatility.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
import plotly.graph_objects as go
import plotly.express as px
from sklearn.linear_model import LinearRegression
import json
from pathlib import Path

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
    page_title="Options Analytics Platform",
    page_icon="▪",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Settings management functions
SETTINGS_DIR = Path.home() / ".optionsanalyzer"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def save_settings(settings: Dict) -> None:
    """Save settings to a JSON file."""
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        st.error(f"Failed to save settings: {str(e)}")


def load_settings() -> Optional[Dict]:
    """Load settings from JSON file."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        return None
    except Exception as e:
        st.error(f"Failed to load settings: {str(e)}")
        return None


def get_default_settings() -> Dict:
    """Return default settings."""
    return {
        'min_delta': 0.15,
        'max_delta': 0.30,
        'min_dte': 5,
        'max_dte': 90,
        'otm_only': True,
        'enable_oi_filter': True,
        'min_open_interest': 100,
        'enable_volume_filter': False,
        'min_volume': 10,
        'enable_spread_filter': True,
        'max_spread_pct': 15.0,
        'hv_choice': '3m',
        'use_bid_yield': True,
        'delta_missing_mode': 'Use Black-Scholes approx',
        'enable_scoring': False,
        'weight_yield': 1.0,
        'weight_richness': 1.0,
        'weight_upside': 1.0,
        'top_n_scores': 20,
        'enable_strike_filter': False,
        'min_strike': 0.0,
        'max_strike': 1000.0
    }

# Clean, professional styling
st.markdown("""
<style>
    /* Subtle professional styling */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    h1 {
        color: #1f77b4;
        font-weight: 600;
    }

    h2 {
        color: #ff7f0e;
        margin-top: 2rem;
    }

    h3 {
        color: #2ca02c;
    }

    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


def parse_tickers(ticker_input: str) -> List[str]:
    """Parse comma-separated ticker input and normalize."""
    if not ticker_input:
        return []
    tickers = [t.strip().upper() for t in ticker_input.split(',')]
    return [t for t in tickers if t]


def fetch_ticker_data(
    ticker: str,
    provider,
    min_dte: int,
    max_dte: int,
    progress_callback=None
) -> Optional[Dict]:
    """Fetch all data for a single ticker."""
    try:
        if progress_callback:
            progress_callback(f"[{ticker}] Fetching underlying price...")

        underlying = provider.fetch_underlying_price(ticker)

        if progress_callback:
            progress_callback(f"[{ticker}] Fetching historical prices...")

        end_date = date.today()
        start_date = end_date - timedelta(days=400)
        historical_prices = provider.fetch_historical_prices(ticker, start_date, end_date)

        if progress_callback:
            progress_callback(f"[{ticker}] Computing volatility metrics...")

        vol_metrics = compute_volatility_metrics(ticker, historical_prices, underlying.current_price)

        if progress_callback:
            progress_callback(f"[{ticker}] Fetching option expirations...")

        all_expirations = provider.get_available_expirations(ticker)
        today = date.today()
        filtered_expirations = [
            exp for exp in all_expirations
            if min_dte <= (exp - today).days <= max_dte
        ]

        if not filtered_expirations:
            st.warning(f"[{ticker}] No expirations in DTE range {min_dte}-{max_dte} days")
            return None

        if progress_callback:
            progress_callback(f"[{ticker}] Fetching option chains ({len(filtered_expirations)} expirations)...")

        options = provider.fetch_option_chain(ticker, filtered_expirations)

        if not options:
            st.warning(f"[{ticker}] No options data available")
            return None

        return {
            'underlying': underlying,
            'volatility': vol_metrics,
            'options': options
        }

    except Exception as e:
        st.error(f"[{ticker}] Error: {str(e)}")
        return None


def display_data_health(ticker: str, ticker_data: Dict, all_metrics: List[OptionMetrics]):
    """Display data health indicators for a ticker."""
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']
    options = ticker_data['options']

    st.markdown(f"#### Data Health: {ticker}")

    health_col1, health_col2, health_col3, health_col4 = st.columns(4)

    with health_col1:
        if underlying:
            st.success(f"Underlying: ${underlying.current_price:.2f}")
        else:
            st.error("Underlying fetch failed")

    with health_col2:
        if vol_metrics.data_end_date and vol_metrics.data_start_date:
            days = (vol_metrics.data_end_date - vol_metrics.data_start_date).days
            st.success(f"Historical: {days} days")
        else:
            st.warning("Limited historical data")

    with health_col3:
        if options:
            # Calculate DTE range
            min_dte_found = min((opt.contract.expiration.date() - date.today()).days for opt in all_metrics)
            max_dte_found = max((opt.contract.expiration.date() - date.today()).days for opt in all_metrics)
            st.success(f"Options: {len(options)} contracts ({min_dte_found}-{max_dte_found} DTE)")
        else:
            st.error("No options loaded")

    with health_col4:
        # Check IV missing percentage
        total = len(all_metrics)
        iv_missing = sum(1 for m in all_metrics if m.contract.implied_volatility is None)
        if total > 0:
            pct = (iv_missing / total) * 100
            if pct > 0:
                st.warning(f"IV missing: {pct:.1f}%")
            else:
                st.success("IV complete")


def process_ticker_options(
    ticker_data: Dict,
    min_delta: Optional[float],
    max_delta: Optional[float],
    min_dte: int,
    max_dte: int,
    otm_only: bool,
    min_open_interest: Optional[int],
    max_spread_pct: Optional[float],
    min_volume: Optional[int],
    min_strike: Optional[float],
    max_strike: Optional[float],
    hv_choice: str
) -> List[OptionMetrics]:
    """Process options for a ticker and compute metrics."""
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']
    options = ticker_data['options']

    if hv_choice == '3m':
        hv_reference = vol_metrics.hv_3m
    elif hv_choice == '1m':
        hv_reference = vol_metrics.hv_1m
    else:
        hv_reference = vol_metrics.hv_1y

    option_metrics = []
    for contract in options:
        # Apply strike filters
        if min_strike is not None and contract.strike < min_strike:
            continue
        if max_strike is not None and contract.strike > max_strike:
            continue

        # Apply volume filter
        if min_volume is not None and (contract.volume is None or contract.volume < min_volume):
            continue

        metrics = compute_option_metrics(
            contract=contract,
            underlying_price=underlying.current_price,
            hv_reference=hv_reference,
            week_52_high=underlying.week_52_high
        )
        option_metrics.append(metrics)

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


def compute_option_score(
    opt: OptionMetrics,
    underlying_price: float,
    hv_reference: Optional[float],
    weight_yield: float,
    weight_richness: float,
    weight_upside: float
) -> Optional[float]:
    """
    Compute a composite score for a covered call option.

    Components:
    A) Vol-adjusted yield: Premium yield adjusted for expected movement
    B) IV richness: How expensive IV is vs HV
    C) Upside sacrifice: How little valuable upside we're giving up

    Returns score from 0-100 (higher is better).
    """
    if not all([opt.bid_premium_yield, hv_reference, opt.contract.implied_volatility]):
        return None

    # Component A: Vol-Adjusted Yield
    # Premium yield adjusted for expected price movement over DTE
    # Higher yield relative to expected movement = better
    premium_yield_pct = opt.bid_premium_yield * 100  # Convert to percentage

    # Expected price movement (1 std dev) over DTE period
    # σ * sqrt(T) where T is in years
    time_fraction = opt.dte / 365.0
    expected_move_pct = hv_reference * 100 * (time_fraction ** 0.5)  # Convert to percentage

    # Vol-adjusted yield: how much premium vs expected movement
    # If we get 3% premium and expect 5% move, ratio is 0.6
    # If we get 4% premium and expect 2% move, ratio is 2.0
    if expected_move_pct > 0:
        vol_adjusted_yield = premium_yield_pct / expected_move_pct
        # Normalize to 0-100 scale (cap at 2.0 ratio = 100 points)
        score_a = min(vol_adjusted_yield / 2.0, 1.0) * 100
    else:
        score_a = 0

    # Component B: IV Richness
    # Higher IV/HV ratio = better (selling expensive options)
    iv_hv_ratio = opt.iv_to_hv_ratio if opt.iv_to_hv_ratio else 1.0
    # Normalize: ratio of 1.5 = 100 points, ratio of 1.0 = 50 points, < 1.0 = lower
    score_b = min(max((iv_hv_ratio - 0.8) / 0.7, 0.0), 1.0) * 100

    # Component C: Upside Sacrifice
    # How little upside we're giving away (strike vs current price)
    # Higher % OTM = less sacrifice = better
    if opt.moneyness and opt.moneyness > 0:
        pct_otm = opt.moneyness * 100
        # Normalize: 10% OTM = 100 points, 0% = 0 points
        score_c = min(pct_otm / 10.0, 1.0) * 100
    else:
        score_c = 0

    # Weighted composite score
    total_weight = weight_yield + weight_richness + weight_upside
    if total_weight == 0:
        return None

    composite_score = (
        (score_a * weight_yield) +
        (score_b * weight_richness) +
        (score_c * weight_upside)
    ) / total_weight

    return composite_score


def create_options_dataframe(
    option_metrics: List[OptionMetrics],
    hv_label: str,
    use_bid_yield: bool = False,
    underlying_price: Optional[float] = None,
    hv_reference: Optional[float] = None,
    weight_yield: float = 1.0,
    weight_richness: float = 1.0,
    weight_upside: float = 1.0,
    enable_scoring: bool = False
) -> pd.DataFrame:
    """Convert list of OptionMetrics to a DataFrame for display."""
    if not option_metrics:
        return pd.DataFrame()

    rows = []
    for opt in option_metrics:
        if use_bid_yield:
            gross_yield = opt.bid_premium_yield
            ann_yield = opt.bid_annualized_premium_yield
        else:
            gross_yield = opt.premium_yield
            ann_yield = opt.annualized_premium_yield

        # Compute score if enabled
        score = None
        if enable_scoring and underlying_price and hv_reference:
            score = compute_option_score(
                opt=opt,
                underlying_price=underlying_price,
                hv_reference=hv_reference,
                weight_yield=weight_yield,
                weight_richness=weight_richness,
                weight_upside=weight_upside
            )

        row = {
            'Expiration': opt.contract.expiration.strftime('%Y-%m-%d'),
            'DTE': opt.dte,
            'Strike': opt.contract.strike,
            'Bid': opt.contract.bid,
            'Bid Size': opt.contract.bid_size,
            'Ask': opt.contract.ask,
            'Ask Size': opt.contract.ask_size,
            'Mid': opt.option_price,
            'IV': opt.contract.implied_volatility,
            f'{hv_label}': None,
            'IV/HV': opt.iv_to_hv_ratio,
            'IV-HV': opt.iv_minus_hv,
            'Richness': opt.richness_score,
            'Score': score,
            'Gross Yield': gross_yield,
            'Ann. Yield': ann_yield,
            'Delta': opt.computed_delta,
            'Moneyness': opt.moneyness,
            '% OTM': opt.moneyness * 100 if opt.moneyness is not None else None,
            'Strike vs 52W High': opt.strike_vs_52wk_high,
            'OI': opt.contract.open_interest,
            'Volume': opt.contract.volume,
            'Spread %': opt.bid_ask_spread_pct,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Sort by Score if enabled and available, otherwise by Richness
    if enable_scoring and 'Score' in df.columns and df['Score'].notna().any():
        df = df.sort_values('Score', ascending=False)
    elif 'Richness' in df.columns:
        df = df.sort_values('Richness', ascending=False)

    return df


def display_ticker_results(
    ticker: str,
    ticker_data: Dict,
    filtered_metrics: List[OptionMetrics],
    hv_choice: str,
    use_bid_yield: bool = False,
    enable_scoring: bool = False,
    weight_yield: float = 1.0,
    weight_richness: float = 1.0,
    weight_upside: float = 1.0
):
    """Display results for a single ticker."""
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']

    st.header(f"{ticker} Analysis")

    # Display metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)

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
        week_52_high_str = f"${underlying.week_52_high:.2f}" if underlying.week_52_high else "N/A"
        st.metric("52W High", week_52_high_str)

    with col6:
        st.metric("Options Found", len(filtered_metrics))

    # Fundamental info
    col7, col8 = st.columns(2)
    with col7:
        earnings_str = underlying.earnings_date.strftime('%Y-%m-%d') if underlying.earnings_date else "N/A"
        st.info(f"**Next Earnings:** {earnings_str}")
    with col8:
        ex_div_str = underlying.ex_dividend_date.strftime('%Y-%m-%d') if underlying.ex_dividend_date else "N/A"
        st.info(f"**Ex-Dividend Date:** {ex_div_str}")

    if not filtered_metrics:
        st.warning(f"[{ticker}] No options meet the filter criteria")
        return

    # Get HV label and reference
    hv_labels = {'1y': 'HV_1Y', '3m': 'HV_3M', '1m': 'HV_1M'}
    hv_label = hv_labels.get(hv_choice, 'HV_1Y')

    hv_ref = None
    if hv_choice == '3m':
        hv_ref = vol_metrics.hv_3m
    elif hv_choice == '1m':
        hv_ref = vol_metrics.hv_1m
    else:
        hv_ref = vol_metrics.hv_1y

    df = create_options_dataframe(
        filtered_metrics,
        hv_label,
        use_bid_yield=use_bid_yield,
        underlying_price=underlying.current_price,
        hv_reference=hv_ref,
        weight_yield=weight_yield,
        weight_richness=weight_richness,
        weight_upside=weight_upside,
        enable_scoring=enable_scoring
    )

    if hv_ref is not None:
        df[hv_label] = hv_ref

    # Top opportunities - by Score if enabled, otherwise by IV Richness
    if enable_scoring and 'Score' in df.columns and df['Score'].notna().any():
        st.subheader("Top Opportunities by Score")
        top_opps = df.nlargest(5, 'Score')
        sort_col = 'Score'
    else:
        st.subheader("Top Opportunities by IV Richness")
        top_opps = df.nlargest(5, 'Richness') if 'Richness' in df.columns and not df['Richness'].isna().all() else df.head(5)
        sort_col = 'Richness'

    # Build display columns dynamically
    base_display_cols = ['Expiration', 'DTE', 'Strike', '% OTM', 'Bid', 'Ask', 'Mid', 'IV', hv_label, 'IV/HV', 'Richness']
    if enable_scoring:
        base_display_cols.append('Score')
    base_display_cols.extend(['Gross Yield', 'Ann. Yield', 'Delta', 'Strike vs 52W High'])
    display_cols = base_display_cols
    display_df = top_opps[display_cols].copy()

    # Format numeric columns
    if 'IV' in display_df.columns:
        display_df['IV'] = display_df['IV'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if hv_label in display_df.columns:
        display_df[hv_label] = display_df[hv_label].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'IV/HV' in display_df.columns:
        display_df['IV/HV'] = display_df['IV/HV'].apply(lambda x: format_number(x, 2) if pd.notna(x) else 'N/A')
    if 'Richness' in display_df.columns:
        display_df['Richness'] = display_df['Richness'].apply(lambda x: format_number(x, 2) if pd.notna(x) else 'N/A')
    if 'Score' in display_df.columns:
        display_df['Score'] = display_df['Score'].apply(lambda x: format_number(x, 1) if pd.notna(x) else 'N/A')
    if 'Gross Yield' in display_df.columns:
        display_df['Gross Yield'] = display_df['Gross Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Ann. Yield' in display_df.columns:
        display_df['Ann. Yield'] = display_df['Ann. Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Delta' in display_df.columns:
        display_df['Delta'] = display_df['Delta'].apply(lambda x: format_number(x, 3) if pd.notna(x) else 'N/A')
    if '% OTM' in display_df.columns:
        display_df['% OTM'] = display_df['% OTM'].apply(lambda x: format_percentage(x / 100) if pd.notna(x) else 'N/A')
    if 'Strike vs 52W High' in display_df.columns:
        display_df['Strike vs 52W High'] = display_df['Strike vs 52W High'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')

    st.dataframe(display_df, use_container_width=True)

    # CSV Export for top richness table
    csv_richness = display_df.to_csv(index=False)
    st.download_button(
        label="Download Top Richness as CSV",
        data=csv_richness,
        file_name=f"{ticker}_top_richness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key=f"csv_{ticker}_richness"
    )

    # Top opportunities by Annualized Yield
    st.subheader("Top Opportunities by Annualized Yield")
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
    if 'Score' in display_df_yield.columns:
        display_df_yield['Score'] = display_df_yield['Score'].apply(lambda x: format_number(x, 1) if pd.notna(x) else 'N/A')
    if 'Gross Yield' in display_df_yield.columns:
        display_df_yield['Gross Yield'] = display_df_yield['Gross Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Ann. Yield' in display_df_yield.columns:
        display_df_yield['Ann. Yield'] = display_df_yield['Ann. Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Delta' in display_df_yield.columns:
        display_df_yield['Delta'] = display_df_yield['Delta'].apply(lambda x: format_number(x, 3) if pd.notna(x) else 'N/A')
    if '% OTM' in display_df_yield.columns:
        display_df_yield['% OTM'] = display_df_yield['% OTM'].apply(lambda x: format_percentage(x / 100) if pd.notna(x) else 'N/A')
    if 'Strike vs 52W High' in display_df_yield.columns:
        display_df_yield['Strike vs 52W High'] = display_df_yield['Strike vs 52W High'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')

    st.dataframe(display_df_yield, use_container_width=True)

    # CSV Export for top yield table
    csv_yield = display_df_yield.to_csv(index=False)
    st.download_button(
        label="Download Top Yield as CSV",
        data=csv_yield,
        file_name=f"{ticker}_top_yield_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key=f"csv_{ticker}_yield"
    )

    # Full data table
    with st.expander(f"View All {len(df)} Options (Sortable Table)"):
        st.dataframe(df, use_container_width=True, height=400)

        # CSV Export for full table
        csv_full = df.to_csv(index=False)
        st.download_button(
            label="Download Full Table as CSV",
            data=csv_full,
            file_name=f"{ticker}_full_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key=f"csv_{ticker}_full"
        )

    # Charts
    st.subheader("Visual Analytics")

    col1, col2 = st.columns(2)

    with col1:
        if not df.empty and 'Strike' in df.columns and 'IV/HV' in df.columns:
            # Drop rows with NaN in columns used for plotting
            df_richness_chart = df.dropna(subset=['IV/HV', 'Ann. Yield'])
            if not df_richness_chart.empty:
                fig_richness = px.scatter(
                    df_richness_chart,
                    x='Strike',
                    y='IV/HV',
                    color='DTE',
                    size='Ann. Yield',
                    hover_data=['Expiration', 'Mid', 'Ann. Yield'],
                    title=f'{ticker}: IV/HV Ratio by Strike'
                )
                fig_richness.add_hline(y=1.0, line_dash="dash", line_color="red",
                                       annotation_text="Fair Value (IV=HV)")
                st.plotly_chart(fig_richness, use_container_width=True)
            else:
                st.info("Insufficient data for IV/HV chart")

    with col2:
        if not df.empty and 'Strike' in df.columns and 'Ann. Yield' in df.columns:
            # Drop rows with NaN in columns used for plotting
            df_yield_chart = df.dropna(subset=['Ann. Yield', 'IV/HV']).copy()
            if not df_yield_chart.empty:
                df_yield_chart['Ann. Yield %'] = df_yield_chart['Ann. Yield'] * 100

                fig_yield = px.scatter(
                    df_yield_chart,
                    x='Strike',
                    y='Ann. Yield %',
                    color='DTE',
                    size='IV/HV',
                    hover_data=['Expiration', 'Mid', 'IV/HV'],
                    title=f'{ticker}: Annualized Yield by Strike'
                )
                st.plotly_chart(fig_yield, use_container_width=True)
            else:
                st.info("Insufficient data for yield chart")

    # Single-ticker regression
    st.subheader("Regression Analysis: Delta vs Gross Yield")

    regression_df = df[['Delta', 'Gross Yield']].dropna()

    if len(regression_df) >= 3:
        X = regression_df[['Delta']].values
        y = regression_df['Gross Yield'].values * 100

        model = LinearRegression()
        model.fit(X, y)

        r_squared = model.score(X, y)
        slope = model.coef_[0]
        intercept = model.intercept_

        fig_regression = go.Figure()

        fig_regression.add_trace(go.Scatter(
            x=regression_df['Delta'],
            y=regression_df['Gross Yield'] * 100,
            mode='markers',
            name='Data Points',
            marker=dict(size=8, opacity=0.6)
        ))

        x_line = np.linspace(regression_df['Delta'].min(), regression_df['Delta'].max(), 100)
        y_line = slope * x_line + intercept
        fig_regression.add_trace(go.Scatter(
            x=x_line,
            y=y_line,
            mode='lines',
            name=f'Regression Line (R²={r_squared:.3f})',
            line=dict(width=2)
        ))

        fig_regression.update_layout(
            title=f'{ticker}: Delta vs Gross Yield Regression',
            xaxis_title='Delta',
            yaxis_title='Gross Yield (%)',
            hovermode='closest'
        )

        st.plotly_chart(fig_regression, use_container_width=True)

        col_reg1, col_reg2, col_reg3 = st.columns(3)
        with col_reg1:
            st.metric("R² (Goodness of Fit)", f"{r_squared:.4f}")
        with col_reg2:
            st.metric("Slope", f"{slope:.4f}")
        with col_reg3:
            st.metric("Intercept", f"{intercept:.4f}%")

        st.info(f"**Regression Equation:** Gross Yield (%) = {slope:.4f} × Delta + {intercept:.4f}")

    else:
        st.warning("Not enough data points for regression analysis (need at least 3 options with valid delta and gross yield)")

    st.divider()


def display_cross_ticker_regression(all_ticker_results: Dict):
    """Display cross-ticker regression analysis for all tickers combined."""
    st.header("Cross-Ticker Regression Analysis")
    st.subheader("Delta vs Gross Yield: All Tickers Combined")

    # Aggregate data from all tickers
    all_data = []

    for ticker, data in all_ticker_results.items():
        filtered_metrics = data['filtered_metrics']
        for opt in filtered_metrics:
            if opt.computed_delta is not None and opt.bid_premium_yield is not None:
                # Create label: TICKER Mon DD, YY $STRIKE
                exp_date = opt.contract.expiration
                label = f"{ticker} {exp_date.strftime('%b %d, %y')} ${opt.contract.strike:.2f}"

                all_data.append({
                    'Ticker': ticker,
                    'Label': label,
                    'Delta': opt.computed_delta,
                    'Gross Yield': opt.bid_premium_yield * 100,  # Convert to percentage
                    'Strike': opt.contract.strike,
                    'Expiration': exp_date.strftime('%Y-%m-%d'),
                    'DTE': opt.dte
                })

    if len(all_data) < 3:
        st.warning("Not enough data points across all tickers for cross-ticker regression analysis")
        return

    df_all = pd.DataFrame(all_data)

    # Perform regression
    X = df_all[['Delta']].values
    y = df_all['Gross Yield'].values

    model = LinearRegression()
    model.fit(X, y)

    r_squared = model.score(X, y)
    slope = model.coef_[0]
    intercept = model.intercept_

    # Create scatter plot with proper labels
    fig_cross = go.Figure()

    # Add scatter points with labels
    fig_cross.add_trace(go.Scatter(
        x=df_all['Delta'],
        y=df_all['Gross Yield'],
        mode='markers+text',
        name='Options',
        text=df_all['Label'],
        textposition='top center',
        textfont=dict(size=8),
        marker=dict(
            size=10,
            color=df_all['DTE'],
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="DTE"),
            opacity=0.7,
            line=dict(width=1)
        ),
        hovertemplate='<b>%{text}</b><br>Delta: %{x:.3f}<br>Gross Yield: %{y:.2f}%<br><extra></extra>'
    ))

    # Add regression line
    x_line = np.linspace(df_all['Delta'].min(), df_all['Delta'].max(), 100)
    y_line = slope * x_line + intercept
    fig_cross.add_trace(go.Scatter(
        x=x_line,
        y=y_line,
        mode='lines',
        name=f'Regression Line (R²={r_squared:.3f})',
        line=dict(width=3, dash='dash')
    ))

    fig_cross.update_layout(
        title='Cross-Ticker Analysis: Delta vs Gross Yield',
        xaxis_title='Delta',
        yaxis_title='Gross Yield (%)',
        hovermode='closest',
        showlegend=True,
        height=700
    )

    st.plotly_chart(fig_cross, use_container_width=True)

    # Display statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Options", len(df_all))
    with col2:
        st.metric("R² (Goodness of Fit)", f"{r_squared:.4f}")
    with col3:
        st.metric("Slope", f"{slope:.4f}")
    with col4:
        st.metric("Intercept", f"{intercept:.4f}%")

    st.info(f"**Regression Equation:** Gross Yield (%) = {slope:.4f} × Delta + {intercept:.4f}")

    # Show data table
    with st.expander("View All Data Points"):
        display_df = df_all[['Label', 'Ticker', 'Expiration', 'Strike', 'Delta', 'Gross Yield', 'DTE']].copy()
        display_df = display_df.sort_values('Gross Yield', ascending=False)
        st.dataframe(display_df, use_container_width=True, height=400)

        # Download button
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="Download Data as CSV",
            data=csv,
            file_name=f"cross_ticker_regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

    st.divider()


def display_leaderboard(all_ticker_results: Dict, hv_choice: str, use_bid_yield: bool):
    """Display cross-ticker leaderboard view."""
    st.header("Cross-Ticker Leaderboard")

    # Aggregate all options
    all_options = []
    for ticker, data in all_ticker_results.items():
        underlying = data['ticker_data']['underlying']
        vol_metrics = data['ticker_data']['volatility']

        # Get HV reference based on choice
        if hv_choice == '3m':
            hv_ref = vol_metrics.hv_3m
        elif hv_choice == '1m':
            hv_ref = vol_metrics.hv_1m
        else:
            hv_ref = vol_metrics.hv_1y

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
                'HV': hv_ref,
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

    # Sort by richness descending
    df_filtered = df_filtered.sort_values('Richness', ascending=False)

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


def display_top_scores_cross_ticker(
    all_ticker_results: Dict,
    hv_choice: str,
    use_bid_yield: bool,
    weight_yield: float,
    weight_richness: float,
    weight_upside: float,
    top_n: int = 20
):
    """Display top N options by composite score across all tickers."""
    st.header("Top Options by Score (Cross-Ticker)")

    # Aggregate all options with scores
    all_scored_options = []

    for ticker, data in all_ticker_results.items():
        underlying = data['ticker_data']['underlying']
        vol_metrics = data['ticker_data']['volatility']

        # Get HV reference based on choice
        if hv_choice == '3m':
            hv_ref = vol_metrics.hv_3m
        elif hv_choice == '1m':
            hv_ref = vol_metrics.hv_1m
        else:
            hv_ref = vol_metrics.hv_1y

        for opt in data['filtered_metrics']:
            # Compute score
            score = compute_option_score(
                opt=opt,
                underlying_price=underlying.current_price,
                hv_reference=hv_ref,
                weight_yield=weight_yield,
                weight_richness=weight_richness,
                weight_upside=weight_upside
            )

            if score is not None:
                if use_bid_yield:
                    gross_yield = opt.bid_premium_yield
                    ann_yield = opt.bid_annualized_premium_yield
                else:
                    gross_yield = opt.premium_yield
                    ann_yield = opt.annualized_premium_yield

                moneyness_pct = opt.moneyness * 100 if opt.moneyness else None

                all_scored_options.append({
                    'Score': score,
                    'Ticker': ticker,
                    'Expiration': opt.contract.expiration.strftime('%Y-%m-%d'),
                    'DTE': opt.dte,
                    'Strike': opt.contract.strike,
                    '% OTM': moneyness_pct,
                    'IV/HV': opt.iv_to_hv_ratio,
                    'Richness': opt.richness_score,
                    'Gross Yield': gross_yield,
                    'Ann. Yield': ann_yield,
                    'Delta': opt.computed_delta,
                    'OI': opt.contract.open_interest
                })

    if not all_scored_options:
        st.warning("No options with valid scores to display")
        return

    df_scores = pd.DataFrame(all_scored_options)
    df_scores = df_scores.sort_values('Score', ascending=False).head(top_n)

    # Display top N
    st.subheader(f"Top {top_n} Highest Scoring Options")
    st.dataframe(df_scores, use_container_width=True, height=600)

    # CSV Export
    csv = df_scores.to_csv(index=False)
    st.download_button(
        label=f"Download Top {top_n} by Score as CSV",
        data=csv,
        file_name=f"top_scores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

    # Score distribution chart
    if len(df_scores) > 0:
        st.subheader("Score Distribution")
        fig_dist = px.histogram(
            df_scores,
            x='Score',
            nbins=20,
            title='Distribution of Composite Scores',
            labels={'Score': 'Composite Score', 'count': 'Number of Options'}
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    st.divider()


def display_single_stock_deepdive(ticker: str, ticker_data: Dict, filtered_metrics: List[OptionMetrics]):
    """Display detailed single-stock analysis showing top option opportunities."""
    st.header(f"Single Stock Deep Dive: {ticker}")

    underlying = ticker_data['underlying']
    volatility = ticker_data['volatility']

    # Display underlying metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Current Price", f"${underlying.current_price:.2f}")
    with col2:
        if underlying.week_52_high:
            pct_from_high = ((underlying.current_price / underlying.week_52_high) - 1) * 100
            st.metric("52W High", f"${underlying.week_52_high:.2f}", f"{pct_from_high:+.1f}%")
    with col3:
        st.metric("HV (1Y)", f"{volatility.hv_1y * 100:.1f}%")
    with col4:
        st.metric("HV (3M)", f"{volatility.hv_3m * 100:.1f}%")

    st.divider()

    # Option details table
    st.subheader("Top Option Opportunities")
    if filtered_metrics:
        option_summary = []
        for opt in filtered_metrics[:20]:  # Show top 20
            option_summary.append({
                'Expiration': opt.contract.expiration.strftime('%Y-%m-%d'),
                'DTE': opt.dte,
                'Strike': f"${opt.contract.strike:.2f}",
                '% OTM': f"{opt.moneyness * 100:.2f}%" if opt.moneyness else "N/A",
                'Bid': f"${opt.contract.bid:.2f}" if opt.contract.bid else "N/A",
                'Ask': f"${opt.contract.ask:.2f}" if opt.contract.ask else "N/A",
                'IV': f"{opt.contract.implied_volatility * 100:.1f}%" if opt.contract.implied_volatility else "N/A",
                'IV/HV': f"{opt.iv_to_hv_ratio:.2f}" if opt.iv_to_hv_ratio else "N/A",
                'Richness': f"{opt.richness_score:.2f}" if opt.richness_score else "N/A",
                'Ann. Yield': f"{opt.bid_annualized_premium_yield * 100:.2f}%" if opt.bid_annualized_premium_yield else "N/A",
                'Delta': f"{opt.approx_delta:.3f}" if opt.approx_delta else "N/A",
                'OI': opt.contract.open_interest if opt.contract.open_interest else 0,
                'Volume': opt.contract.volume if opt.contract.volume else 0
            })

        df_opt_summary = pd.DataFrame(option_summary)
        st.dataframe(df_opt_summary, use_container_width=True, height=600)

        # Export to CSV
        csv = df_opt_summary.to_csv(index=False)
        st.download_button(
            label=f"Download {ticker} Options as CSV",
            data=csv,
            file_name=f"{ticker}_options_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No options match the current filter criteria")

    st.divider()


def main():
    """Main Streamlit application."""

    # Initialize session state for storing scan results
    if 'scan_results' not in st.session_state:
        st.session_state.scan_results = None
    if 'scan_timestamp' not in st.session_state:
        st.session_state.scan_timestamp = None
    if 'settings_loaded' not in st.session_state:
        st.session_state.settings_loaded = False
        st.session_state.current_settings = get_default_settings()

    st.title("Options Analytics Platform")
    st.caption("Covered Call Scanner & Volatility Richness Analyzer")

    # Data source indicator
    st.info("📊 **Data Source:** Yahoo Finance (yfinance) | Real-time market data with 15-minute delay")

    # Sidebar configuration
    st.sidebar.header("Configuration")

    # Settings Management Section
    with st.sidebar.expander("⚙️ Settings Management", expanded=False):
        st.markdown("**Save/Load Templates**")

        col_set1, col_set2 = st.columns(2)
        with col_set1:
            if st.button("💾 Save Current", use_container_width=True):
                current_settings = {
                    'min_delta': st.session_state.get('min_delta', 0.15),
                    'max_delta': st.session_state.get('max_delta', 0.30),
                    'min_dte': st.session_state.get('min_dte', 5),
                    'max_dte': st.session_state.get('max_dte', 90),
                    'otm_only': st.session_state.get('otm_only', True),
                    'enable_oi_filter': st.session_state.get('enable_oi_filter', True),
                    'min_open_interest': st.session_state.get('min_open_interest', 100),
                    'enable_volume_filter': st.session_state.get('enable_volume_filter', False),
                    'min_volume': st.session_state.get('min_volume', 10),
                    'enable_spread_filter': st.session_state.get('enable_spread_filter', True),
                    'max_spread_pct': st.session_state.get('max_spread_pct', 15.0),
                    'hv_choice': st.session_state.get('hv_choice', '3m'),
                    'use_bid_yield': st.session_state.get('use_bid_yield', True),
                    'delta_missing_mode': st.session_state.get('delta_missing_mode', 'Use Black-Scholes approx'),
                    'enable_scoring': st.session_state.get('enable_scoring', False),
                    'weight_yield': st.session_state.get('weight_yield', 1.0),
                    'weight_richness': st.session_state.get('weight_richness', 1.0),
                    'weight_upside': st.session_state.get('weight_upside', 1.0),
                    'top_n_scores': st.session_state.get('top_n_scores', 20)
                }
                save_settings(current_settings)
                st.success("Settings saved!")

        with col_set2:
            if st.button("📂 Load Saved", use_container_width=True):
                loaded = load_settings()
                if loaded:
                    st.session_state.current_settings = loaded
                    st.session_state.settings_loaded = True
                    st.success("Settings loaded!")
                    st.rerun()
                else:
                    st.warning("No saved settings found")

        if st.button("🔄 Reset to Defaults", use_container_width=True):
            st.session_state.current_settings = get_default_settings()
            st.session_state.settings_loaded = True
            st.success("Reset to defaults!")
            st.rerun()

        # Show settings file location
        st.caption(f"Settings file: `{SETTINGS_FILE}`")

    st.sidebar.divider()

    # Load settings if available
    if st.session_state.settings_loaded:
        saved_settings = st.session_state.current_settings
    else:
        saved_settings = get_default_settings()

    ticker_input = st.sidebar.text_input(
        "Tickers (comma-separated)",
        value="",
        help="Enter stock tickers separated by commas, e.g., MO, APO, LRCX, JPM"
    )

    st.sidebar.subheader("Delta Range")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_delta = st.number_input("Min Delta", min_value=0.0, max_value=1.0, value=saved_settings.get('min_delta', 0.15), step=0.05, key='min_delta')
    with col2:
        max_delta = st.number_input("Max Delta", min_value=0.0, max_value=1.0, value=saved_settings.get('max_delta', 0.30), step=0.05, key='max_delta')

    st.sidebar.subheader("Expiration Range (DTE)")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        min_dte = st.number_input("Min DTE", min_value=1, max_value=730, value=saved_settings.get('min_dte', 5), step=1, key='min_dte')
    with col4:
        max_dte = st.number_input("Max DTE", min_value=1, max_value=730, value=saved_settings.get('max_dte', 90), step=1, key='max_dte')

    st.sidebar.subheader("Strike Price Range")
    enable_strike_filter = st.sidebar.checkbox("Enable Strike Price Filter", value=saved_settings.get('enable_strike_filter', False), key='enable_strike_filter')
    min_strike = None
    max_strike = None
    if enable_strike_filter:
        col5, col6 = st.sidebar.columns(2)
        with col5:
            min_strike = st.number_input("Min Strike", min_value=0.0, value=saved_settings.get('min_strike', 0.0), step=1.0)
        with col6:
            max_strike = st.number_input("Max Strike", min_value=0.0, value=saved_settings.get('max_strike', 1000.0), step=1.0)

    st.sidebar.subheader("Liquidity Filters")

    otm_only = st.sidebar.checkbox("OTM Only", value=saved_settings.get('otm_only', True), key='otm_only', help="Only show out-of-the-money options")

    enable_oi_filter = st.sidebar.checkbox("Filter by Open Interest", value=saved_settings.get('enable_oi_filter', True), key='enable_oi_filter')
    min_open_interest = None
    if enable_oi_filter:
        min_open_interest = st.sidebar.number_input("Min Open Interest", min_value=0, value=saved_settings.get('min_open_interest', 100), step=10, key='min_open_interest')

    enable_volume_filter = st.sidebar.checkbox("Filter by Volume", value=saved_settings.get('enable_volume_filter', False), key='enable_volume_filter')
    min_volume = None
    if enable_volume_filter:
        min_volume = st.sidebar.number_input("Min Volume", min_value=0, value=saved_settings.get('min_volume', 10), step=5, key='min_volume')

    enable_spread_filter = st.sidebar.checkbox("Filter by Bid-Ask Spread", value=saved_settings.get('enable_spread_filter', True), key='enable_spread_filter')
    max_spread_pct = None
    if enable_spread_filter:
        max_spread_pct = st.sidebar.number_input("Max Spread %", min_value=0.0, max_value=100.0, value=saved_settings.get('max_spread_pct', 15.0), step=1.0, key='max_spread_pct')

    st.sidebar.subheader("Volatility & Yield")

    hv_options = ['1y', '3m', '1m']
    default_hv = saved_settings.get('hv_choice', '3m')
    hv_index = hv_options.index(default_hv) if default_hv in hv_options else 1

    hv_choice = st.sidebar.selectbox(
        "HV Reference Period",
        options=hv_options,
        index=hv_index,
        key='hv_choice',
        help="Which historical volatility period to use for IV comparisons"
    )

    use_bid_yield_default = saved_settings.get('use_bid_yield', True)
    use_bid_yield = st.sidebar.radio(
        "Calculate yields based on:",
        options=[("Midpoint (Bid+Ask)/2", False), ("Bid Price", True)],
        format_func=lambda x: x[0],
        index=1 if use_bid_yield_default else 0,
        key='use_bid_yield_radio',
        help="Choose whether to calculate yields using bid price (conservative) or midpoint (optimistic)"
    )[1]

    st.sidebar.subheader("Missing Data Handling")

    iv_missing_mode = st.sidebar.radio(
        "When IV is missing:",
        options=["Drop option", "Use ATM IV proxy", "Interpolate"],
        index=1,
        help="How to handle options with missing implied volatility"
    )

    delta_options = ["Disable delta filter", "Use Black-Scholes approx"]
    default_delta_mode = saved_settings.get('delta_missing_mode', 'Use Black-Scholes approx')
    delta_index = delta_options.index(default_delta_mode) if default_delta_mode in delta_options else 1

    delta_missing_mode = st.sidebar.radio(
        "When Delta is missing:",
        options=delta_options,
        index=delta_index,
        key='delta_missing_mode',
        help="How to handle options with missing delta values"
    )

    if delta_missing_mode == "Use Black-Scholes approx":
        st.sidebar.info("Using BS approximation for delta")

    st.sidebar.subheader("Scoring System")

    enable_scoring = st.sidebar.checkbox(
        "Enable Composite Scoring",
        value=saved_settings.get('enable_scoring', False),
        key='enable_scoring',
        help="Calculate a weighted composite score for each option based on vol-adjusted yield, IV richness, and upside sacrifice"
    )

    if enable_scoring:
        # Detailed scoring help documentation
        with st.sidebar.expander("ℹ️ How Scoring Works"):
            st.markdown("""
**Composite Score Formula:**

The final score (0-100) is a weighted average of three components:

---

**Component A: Vol-Adjusted Yield**
```
premium_yield = (option_premium / stock_price) × 100
time_fraction = DTE / 365
expected_move = HV × 100 × √time_fraction

vol_adjusted_yield = premium_yield / expected_move
score_A = min(vol_adjusted_yield / 2.0, 1.0) × 100
```
*Measures: Yield per unit of expected stock movement*

---

**Component B: IV Richness**
```
iv_hv_ratio = IV / HV

score_B = min(max((iv_hv_ratio - 0.8) / 0.7, 0), 1.0) × 100
```
*Measures: How expensive the option is (IV > HV = rich)*

---

**Component C: Upside Sacrifice**
```
pct_OTM = ((strike - price) / price) × 100

score_C = min(pct_OTM / 10.0, 1.0) × 100
```
*Measures: How much upside potential you keep*

---

**Final Score:**
```
total_weight = wA + wB + wC

Final Score = (score_A × wA + score_B × wB + score_C × wC) / total_weight
```

**Higher scores = Better opportunities**
            """)

        st.sidebar.markdown("**Score Component Weights:**")

        weight_yield = st.sidebar.slider(
            "A) Vol-Adjusted Yield",
            min_value=0.0,
            max_value=3.0,
            value=saved_settings.get('weight_yield', 1.0),
            step=0.1,
            key='weight_yield',
            help="Weight for premium yield vs expected price movement (higher = prioritize yield per unit of risk)"
        )

        weight_richness = st.sidebar.slider(
            "B) IV Richness (IV/HV)",
            min_value=0.0,
            max_value=3.0,
            value=saved_settings.get('weight_richness', 1.0),
            step=0.1,
            key='weight_richness',
            help="Weight for implied vs historical volatility (higher = prioritize selling expensive options)"
        )

        weight_upside = st.sidebar.slider(
            "C) Upside Sacrifice (% OTM)",
            min_value=0.0,
            max_value=3.0,
            value=saved_settings.get('weight_upside', 1.0),
            step=0.1,
            key='weight_upside',
            help="Weight for how far OTM the strike is (higher = prioritize preserving upside)"
        )

        top_n_scores = st.sidebar.number_input(
            "Top N to display (cross-ticker)",
            min_value=5,
            max_value=100,
            value=saved_settings.get('top_n_scores', 20),
            step=5,
            key='top_n_scores',
            help="Number of top-scoring options to show in cross-ticker view"
        )
    else:
        weight_yield = 1.0
        weight_richness = 1.0
        weight_upside = 1.0
        top_n_scores = 20

    st.sidebar.divider()

    # Display last scan timestamp if available
    if st.session_state.scan_timestamp:
        scan_time = st.session_state.scan_timestamp
        time_ago = datetime.now() - scan_time
        minutes_ago = int(time_ago.total_seconds() / 60)
        if minutes_ago < 1:
            time_str = "just now"
        elif minutes_ago == 1:
            time_str = "1 minute ago"
        elif minutes_ago < 60:
            time_str = f"{minutes_ago} minutes ago"
        else:
            hours_ago = minutes_ago // 60
            time_str = f"{hours_ago} hour{'s' if hours_ago > 1 else ''} ago"

        # Convert to Eastern Time for display
        # If scan_time is naive (no timezone), assume it's local/UTC
        if scan_time.tzinfo is None:
            # Make it timezone-aware as UTC, then convert to ET
            scan_time_utc = scan_time.replace(tzinfo=ZoneInfo('UTC'))
        else:
            scan_time_utc = scan_time.astimezone(ZoneInfo('UTC'))

        scan_time_et = scan_time_utc.astimezone(ZoneInfo('America/New_York'))
        exact_time = scan_time_et.strftime("%Y-%m-%d %H:%M:%S ET")
        st.sidebar.info(f"**Last scan:** {time_str}\n\n**Exact time:** {exact_time}")

    col_scan1, col_scan2 = st.sidebar.columns(2)
    with col_scan1:
        run_scan = st.button("Run Scan", type="primary", use_container_width=True)
    with col_scan2:
        refresh_scan = st.button("Refresh Data", use_container_width=True)

    if run_scan or refresh_scan:
        tickers = parse_tickers(ticker_input)

        if not tickers:
            st.error("Please enter at least one ticker symbol")
            return

        st.info(f"Scanning {len(tickers)} ticker(s): {', '.join(tickers)}")

        provider = get_default_provider()

        progress_bar = st.progress(0)
        status_text = st.empty()

        # Fetch data for all tickers
        results = {}
        all_ticker_results = {}

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
        st.divider()

        # Process and display results for each ticker
        for ticker, ticker_data in results.items():
            # Compute all metrics for data health check
            underlying = ticker_data['underlying']
            vol_metrics = ticker_data['volatility']
            options = ticker_data['options']

            # Compute all option metrics (before filtering)
            if hv_choice == '3m':
                hv_reference = vol_metrics.hv_3m
            elif hv_choice == '1m':
                hv_reference = vol_metrics.hv_1m
            else:
                hv_reference = vol_metrics.hv_1y

            all_metrics = []
            for contract in options:
                metrics = compute_option_metrics(
                    contract=contract,
                    underlying_price=underlying.current_price,
                    hv_reference=hv_reference,
                    week_52_high=underlying.week_52_high
                )
                all_metrics.append(metrics)

            # Display data health before filtering
            display_data_health(ticker, ticker_data, all_metrics)

            # Now apply filters
            filtered_metrics = process_ticker_options(
                ticker_data=ticker_data,
                min_delta=min_delta,
                max_delta=max_delta,
                min_dte=min_dte,
                max_dte=max_dte,
                otm_only=otm_only,
                min_open_interest=min_open_interest,
                max_spread_pct=max_spread_pct,
                min_volume=min_volume,
                min_strike=min_strike,
                max_strike=max_strike,
                hv_choice=hv_choice
            )

            # Store for cross-ticker regression
            all_ticker_results[ticker] = {
                'ticker_data': ticker_data,
                'filtered_metrics': filtered_metrics
            }

            display_ticker_results(
                ticker,
                ticker_data,
                filtered_metrics,
                hv_choice,
                use_bid_yield,
                enable_scoring=enable_scoring,
                weight_yield=weight_yield,
                weight_richness=weight_richness,
                weight_upside=weight_upside
            )

        # Display cross-ticker regression analysis
        if len(all_ticker_results) > 0:
            display_cross_ticker_regression(all_ticker_results)

        # Display cross-ticker leaderboard
        if len(all_ticker_results) > 0:
            display_leaderboard(all_ticker_results, hv_choice, use_bid_yield)

        # Display top scores cross-ticker (if scoring is enabled)
        if enable_scoring and len(all_ticker_results) > 0:
            display_top_scores_cross_ticker(
                all_ticker_results,
                hv_choice,
                use_bid_yield,
                weight_yield,
                weight_richness,
                weight_upside,
                top_n=top_n_scores
            )

        # Store results in session state
        st.session_state.scan_results = all_ticker_results
        st.session_state.scan_timestamp = datetime.now()

    # Single Stock Deep Dive Section (outside scan block to persist across reruns)
    if st.session_state.scan_results and len(st.session_state.scan_results) > 0:
        st.divider()
        st.header("Single Stock Deep Dive")

        # Ticker selector
        available_tickers = list(st.session_state.scan_results.keys())
        selected_ticker = st.selectbox(
            "Select a ticker for detailed analysis:",
            options=available_tickers,
            index=0,
            key="deep_dive_ticker_selector"
        )

        if selected_ticker:
            ticker_info = st.session_state.scan_results[selected_ticker]
            display_single_stock_deepdive(
                ticker=selected_ticker,
                ticker_data=ticker_info['ticker_data'],
                filtered_metrics=ticker_info['filtered_metrics']
            )

    elif not (run_scan or refresh_scan):
        st.info("Configure your scan parameters in the sidebar and click 'Run Scan' to begin")

        st.subheader("Features")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **Volatility Analysis**
            - Realized (historical) volatility: 1Y, 3M, 1M periods
            - Implied volatility from option prices
            - IV vs HV comparison with richness scoring

            **Yield Metrics**
            - Gross yield (non-annualized premium / stock price)
            - Annualized yield for time-adjusted comparison
            - Bid-based (conservative) or midpoint-based (optimistic)
            """)

        with col2:
            st.markdown("""
            **Advanced Analytics**
            - Delta filtering with Black-Scholes approximation
            - Single-ticker regression: Delta vs Gross Yield
            - Cross-ticker regression for portfolio-level insights
            - 52-week high comparison
            - Earnings and ex-dividend date tracking

            **Filtering Capabilities**
            - Delta range, DTE range, Strike price range
            - OTM-only options
            - Minimum open interest, volume
            - Maximum bid-ask spread
            """)


if __name__ == "__main__":
    main()
