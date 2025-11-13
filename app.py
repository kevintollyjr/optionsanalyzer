"""
Covered Call Scanner & Volatility Richness Analyzer

A professional-grade Streamlit application for scanning covered call opportunities
and analyzing implied volatility richness vs historical volatility.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import plotly.graph_objects as go
import plotly.express as px
from sklearn.linear_model import LinearRegression

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

# Bloomberg-style CSS
st.markdown("""
<style>
    /* Main theme colors */
    :root {
        --bg-primary: #000000;
        --bg-secondary: #1a1a1a;
        --text-primary: #ffffff;
        --text-secondary: #b0b0b0;
        --accent-orange: #ff6600;
        --accent-blue: #0066cc;
        --border-color: #333333;
    }

    /* Global styles */
    .stApp {
        background-color: #000000;
    }

    /* Headers */
    h1, h2, h3 {
        color: #ff6600 !important;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    /* Metrics */
    [data-testid="stMetricValue"] {
        color: #00ff00;
        font-size: 24px;
        font-weight: 700;
        font-family: 'Courier New', monospace;
    }

    [data-testid="stMetricLabel"] {
        color: #b0b0b0;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* Data tables */
    .dataframe {
        background-color: #1a1a1a;
        border: 1px solid #333333;
        color: #ffffff;
        font-family: 'Courier New', monospace;
        font-size: 12px;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0d0d0d;
        border-right: 2px solid #ff6600;
    }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #ff6600;
    }

    /* Buttons */
    .stButton > button {
        background-color: #ff6600;
        color: #000000;
        font-weight: 700;
        border: none;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s;
    }

    .stButton > button:hover {
        background-color: #ff8833;
        box-shadow: 0 0 10px rgba(255, 102, 0, 0.5);
    }

    /* Info boxes */
    .stAlert {
        background-color: #1a1a1a;
        border-left: 4px solid #0066cc;
        color: #ffffff;
    }

    /* Divider */
    hr {
        border-color: #ff6600;
        border-width: 2px;
    }

    /* Input fields */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input {
        background-color: #1a1a1a;
        color: #ffffff;
        border: 1px solid #333333;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        background-color: #1a1a1a;
        color: #ff6600;
        font-weight: 600;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #1a1a1a;
        border-bottom: 2px solid #ff6600;
    }

    .stTabs [data-baseweb="tab"] {
        color: #b0b0b0;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        color: #ff6600;
        border-bottom: 3px solid #ff6600;
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


def create_options_dataframe(option_metrics: List[OptionMetrics], hv_label: str, use_bid_yield: bool = False) -> pd.DataFrame:
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
            'Gross Yield': gross_yield,
            'Ann. Yield': ann_yield,
            'Delta': opt.computed_delta,
            'Moneyness': opt.moneyness,
            'Strike vs 52W High': opt.strike_vs_52wk_high,
            'OI': opt.contract.open_interest,
            'Volume': opt.contract.volume,
            'Spread %': opt.bid_ask_spread_pct,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    if 'Richness' in df.columns:
        df = df.sort_values('Richness', ascending=False)

    return df


def display_ticker_results(
    ticker: str,
    ticker_data: Dict,
    filtered_metrics: List[OptionMetrics],
    hv_choice: str,
    use_bid_yield: bool = False
):
    """Display results for a single ticker."""
    underlying = ticker_data['underlying']
    vol_metrics = ticker_data['volatility']

    st.markdown(f"## {ticker}")
    st.markdown("---")

    # Display metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric("CURRENT PRICE", f"${underlying.current_price:.2f}")

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
        st.metric("52W HIGH", week_52_high_str)

    with col6:
        st.metric("OPTIONS FOUND", len(filtered_metrics))

    # Fundamental info
    col7, col8 = st.columns(2)
    with col7:
        earnings_str = underlying.earnings_date.strftime('%Y-%m-%d') if underlying.earnings_date else "N/A"
        st.info(f"**NEXT EARNINGS:** {earnings_str}")
    with col8:
        ex_div_str = underlying.ex_dividend_date.strftime('%Y-%m-%d') if underlying.ex_dividend_date else "N/A"
        st.info(f"**EX-DIVIDEND DATE:** {ex_div_str}")

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

    df = create_options_dataframe(filtered_metrics, hv_label, use_bid_yield=use_bid_yield)

    if hv_ref is not None:
        df[hv_label] = hv_ref

    # Top opportunities by IV Richness
    st.markdown("### TOP OPPORTUNITIES BY IV RICHNESS")
    top_by_richness = df.nlargest(5, 'Richness') if 'Richness' in df.columns and not df['Richness'].isna().all() else df.head(5)

    display_cols = ['Expiration', 'DTE', 'Strike', 'Bid', 'Ask', 'Mid', 'IV', hv_label, 'IV/HV', 'Richness', 'Gross Yield', 'Ann. Yield', 'Delta', 'Strike vs 52W High']
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
    if 'Gross Yield' in display_df.columns:
        display_df['Gross Yield'] = display_df['Gross Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Ann. Yield' in display_df.columns:
        display_df['Ann. Yield'] = display_df['Ann. Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Delta' in display_df.columns:
        display_df['Delta'] = display_df['Delta'].apply(lambda x: format_number(x, 3) if pd.notna(x) else 'N/A')
    if 'Strike vs 52W High' in display_df.columns:
        display_df['Strike vs 52W High'] = display_df['Strike vs 52W High'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')

    st.dataframe(display_df, use_container_width=True)

    # Top opportunities by Annualized Yield
    st.markdown("### TOP OPPORTUNITIES BY ANNUALIZED YIELD")
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
    if 'Gross Yield' in display_df_yield.columns:
        display_df_yield['Gross Yield'] = display_df_yield['Gross Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Ann. Yield' in display_df_yield.columns:
        display_df_yield['Ann. Yield'] = display_df_yield['Ann. Yield'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')
    if 'Delta' in display_df_yield.columns:
        display_df_yield['Delta'] = display_df_yield['Delta'].apply(lambda x: format_number(x, 3) if pd.notna(x) else 'N/A')
    if 'Strike vs 52W High' in display_df_yield.columns:
        display_df_yield['Strike vs 52W High'] = display_df_yield['Strike vs 52W High'].apply(lambda x: format_percentage(x) if pd.notna(x) else 'N/A')

    st.dataframe(display_df_yield, use_container_width=True)

    # Full data table
    with st.expander(f"ALL {len(df)} OPTIONS (SORTABLE TABLE)"):
        st.dataframe(df, use_container_width=True, height=400)

    # Charts
    st.markdown("### ANALYTICS")

    col1, col2 = st.columns(2)

    with col1:
        if not df.empty and 'Strike' in df.columns and 'IV/HV' in df.columns:
            fig_richness = px.scatter(
                df.dropna(subset=['IV/HV']),
                x='Strike',
                y='IV/HV',
                color='DTE',
                size='Ann. Yield',
                hover_data=['Expiration', 'Mid', 'Ann. Yield'],
                title=f'{ticker}: IV/HV Ratio by Strike',
                labels={'IV/HV': 'IV/HV Ratio', 'Strike': 'Strike Price'},
                template='plotly_dark'
            )
            fig_richness.add_hline(y=1.0, line_dash="dash", line_color="#ff6600",
                                   annotation_text="Fair Value (IV=HV)")
            fig_richness.update_layout(
                plot_bgcolor='#1a1a1a',
                paper_bgcolor='#0d0d0d',
                font_color='#ffffff'
            )
            st.plotly_chart(fig_richness, use_container_width=True)

    with col2:
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
                labels={'Ann. Yield %': 'Annualized Yield (%)', 'Strike': 'Strike Price'},
                template='plotly_dark'
            )
            fig_yield.update_layout(
                plot_bgcolor='#1a1a1a',
                paper_bgcolor='#0d0d0d',
                font_color='#ffffff'
            )
            st.plotly_chart(fig_yield, use_container_width=True)

    # Single-ticker regression
    st.markdown("### REGRESSION ANALYSIS: DELTA VS GROSS YIELD")

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
            marker=dict(size=8, color='#0066cc', opacity=0.6)
        ))

        x_line = np.linspace(regression_df['Delta'].min(), regression_df['Delta'].max(), 100)
        y_line = slope * x_line + intercept
        fig_regression.add_trace(go.Scatter(
            x=x_line,
            y=y_line,
            mode='lines',
            name=f'Regression Line (R²={r_squared:.3f})',
            line=dict(color='#ff6600', width=2)
        ))

        fig_regression.update_layout(
            title=f'{ticker}: Delta vs Gross Yield Regression',
            xaxis_title='Delta',
            yaxis_title='Gross Yield (%)',
            hovermode='closest',
            template='plotly_dark',
            plot_bgcolor='#1a1a1a',
            paper_bgcolor='#0d0d0d',
            font_color='#ffffff'
        )

        st.plotly_chart(fig_regression, use_container_width=True)

        col_reg1, col_reg2, col_reg3 = st.columns(3)
        with col_reg1:
            st.metric("R² (GOODNESS OF FIT)", f"{r_squared:.4f}")
        with col_reg2:
            st.metric("SLOPE", f"{slope:.4f}")
        with col_reg3:
            st.metric("INTERCEPT", f"{intercept:.4f}%")

        st.info(f"**REGRESSION EQUATION:** Gross Yield (%) = {slope:.4f} × Delta + {intercept:.4f}")

    else:
        st.warning("Not enough data points for regression analysis (need at least 3 options with valid delta and gross yield)")

    st.markdown("---")


def display_cross_ticker_regression(all_ticker_results: Dict):
    """Display cross-ticker regression analysis for all tickers combined."""
    st.markdown("## CROSS-TICKER REGRESSION ANALYSIS")
    st.markdown("### Delta vs Gross Yield: All Tickers Combined")

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
        textfont=dict(size=8, color='#ffffff'),
        marker=dict(
            size=10,
            color=df_all['DTE'],
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="DTE"),
            opacity=0.7,
            line=dict(width=1, color='#ffffff')
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
        line=dict(color='#ff6600', width=3, dash='dash')
    ))

    fig_cross.update_layout(
        title='Cross-Ticker Analysis: Delta vs Gross Yield',
        xaxis_title='Delta',
        yaxis_title='Gross Yield (%)',
        hovermode='closest',
        template='plotly_dark',
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#0d0d0d',
        font=dict(color='#ffffff', size=12),
        showlegend=True,
        height=700
    )

    st.plotly_chart(fig_cross, use_container_width=True)

    # Display statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("TOTAL OPTIONS", len(df_all))
    with col2:
        st.metric("R² (GOODNESS OF FIT)", f"{r_squared:.4f}")
    with col3:
        st.metric("SLOPE", f"{slope:.4f}")
    with col4:
        st.metric("INTERCEPT", f"{intercept:.4f}%")

    st.info(f"**REGRESSION EQUATION:** Gross Yield (%) = {slope:.4f} × Delta + {intercept:.4f}")

    # Show data table
    with st.expander("VIEW ALL DATA POINTS"):
        display_df = df_all[['Label', 'Ticker', 'Expiration', 'Strike', 'Delta', 'Gross Yield', 'DTE']].copy()
        display_df = display_df.sort_values('Gross Yield', ascending=False)
        st.dataframe(display_df, use_container_width=True, height=400)

    st.markdown("---")


def main():
    """Main Streamlit application."""

    st.title("OPTIONS ANALYTICS PLATFORM")
    st.markdown("##### Covered Call Scanner & Volatility Richness Analyzer")

    # Sidebar configuration
    st.sidebar.markdown("## CONFIGURATION")

    ticker_input = st.sidebar.text_input(
        "Tickers (comma-separated)",
        value="",
        help="Enter stock tickers separated by commas, e.g., MO, APO, LRCX, JPM"
    )

    st.sidebar.markdown("### Delta Range")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_delta = st.number_input("Min Delta", min_value=0.0, max_value=1.0, value=0.15, step=0.05)
    with col2:
        max_delta = st.number_input("Max Delta", min_value=0.0, max_value=1.0, value=0.30, step=0.05)

    st.sidebar.markdown("### Expiration Range (DTE)")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        min_dte = st.number_input("Min DTE", min_value=1, max_value=730, value=5, step=1)
    with col4:
        max_dte = st.number_input("Max DTE", min_value=1, max_value=730, value=90, step=1)

    st.sidebar.markdown("### Additional Filters")

    otm_only = st.sidebar.checkbox("OTM Only", value=True, help="Only show out-of-the-money options")

    enable_oi_filter = st.sidebar.checkbox("Filter by Open Interest", value=True)
    min_open_interest = None
    if enable_oi_filter:
        min_open_interest = st.sidebar.number_input("Min Open Interest", min_value=0, value=100, step=10)

    enable_spread_filter = st.sidebar.checkbox("Filter by Bid-Ask Spread", value=True)
    max_spread_pct = None
    if enable_spread_filter:
        max_spread_pct = st.sidebar.number_input("Max Spread %", min_value=0.0, max_value=100.0, value=15.0, step=1.0)

    st.sidebar.markdown("### Volatility Comparison")
    hv_choice = st.sidebar.selectbox(
        "HV Reference Period",
        options=['1y', '3m', '1m'],
        index=0,
        help="Which historical volatility period to use for IV comparisons"
    )

    st.sidebar.markdown("### Yield Calculation")
    use_bid_yield = st.sidebar.radio(
        "Calculate yields based on:",
        options=[("Midpoint (Bid+Ask)/2", False), ("Bid Price", True)],
        format_func=lambda x: x[0],
        index=1,  # Default to Bid Price (conservative)
        help="Choose whether to calculate yields using bid price (conservative) or midpoint (optimistic)"
    )[1]

    run_scan = st.sidebar.button("RUN SCAN", type="primary", use_container_width=True)

    if run_scan:
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
        st.markdown("---")

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

            # Store for cross-ticker regression
            all_ticker_results[ticker] = {
                'ticker_data': ticker_data,
                'filtered_metrics': filtered_metrics
            }

            display_ticker_results(ticker, ticker_data, filtered_metrics, hv_choice, use_bid_yield)

        # Display cross-ticker regression analysis
        if len(all_ticker_results) > 0:
            display_cross_ticker_regression(all_ticker_results)

    else:
        st.info("Configure your scan parameters in the sidebar and click 'RUN SCAN' to begin")

        st.markdown("### OVERVIEW")
        st.markdown("""
        This professional-grade options analytics platform provides comprehensive analysis for covered call strategies:

        **Volatility Analysis**
        - Realized (historical) volatility: 1Y, 3M, 1M periods
        - Implied volatility from option prices
        - IV vs HV comparison with richness scoring

        **Yield Metrics**
        - Gross yield (non-annualized premium / stock price)
        - Annualized yield for time-adjusted comparison
        - Bid-based (conservative) or midpoint-based (optimistic) calculations

        **Advanced Analytics**
        - Delta filtering with Black-Scholes approximation
        - Regression analysis: Delta vs Gross Yield
        - Cross-ticker regression for portfolio-level insights
        - 52-week high comparison
        - Earnings and ex-dividend date tracking

        **Filtering Capabilities**
        - Delta range (probability-based filtering)
        - Days to expiration (DTE) range
        - OTM-only options
        - Minimum open interest (liquidity)
        - Maximum bid-ask spread (transaction cost control)
        """)


if __name__ == "__main__":
    main()
