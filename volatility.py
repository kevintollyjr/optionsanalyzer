"""
Volatility calculation module.

This module provides functions to compute:
- Realized (historical) volatility from price data
- Rolling volatility over different windows
- Volatility comparison metrics
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


@dataclass
class VolatilityMetrics:
    """Container for volatility metrics of an underlying."""
    ticker: str
    hv_1y: Optional[float]  # 1-year annualized realized volatility
    hv_3m: Optional[float]  # 3-month annualized realized volatility
    hv_1m: Optional[float]  # 1-month annualized realized volatility
    current_price: float
    data_start_date: Optional[pd.Timestamp] = None
    data_end_date: Optional[pd.Timestamp] = None


def compute_log_returns(prices: pd.Series) -> pd.Series:
    """
    Compute log returns from a price series.

    Formula: r_t = ln(P_t / P_{t-1})

    Args:
        prices: Series of prices (adjusted close)

    Returns:
        Series of log returns (first value will be NaN)
    """
    return np.log(prices / prices.shift(1))


def compute_realized_volatility(
    prices: pd.DataFrame,
    window_days: int = 252,
    trading_days_per_year: int = 252
) -> Optional[float]:
    """
    Compute annualized realized volatility from historical prices.

    Uses log returns and standard deviation.

    Formula:
        1. Compute daily log returns: r_t = ln(P_t / P_{t-1})
        2. Compute standard deviation of returns over the window
        3. Annualize: σ_annual = σ_daily * sqrt(trading_days_per_year)

    Args:
        prices: DataFrame with 'Adj Close' column and DatetimeIndex
        window_days: Number of trading days to use for calculation
        trading_days_per_year: Typically 252 for US markets

    Returns:
        Annualized realized volatility (as a decimal, e.g., 0.25 = 25%)
        Returns None if insufficient data
    """
    if prices is None or prices.empty:
        return None

    if 'Adj Close' not in prices.columns:
        return None

    # Get the price series
    price_series = prices['Adj Close'].dropna()

    if len(price_series) < window_days:
        # Use all available data if we don't have enough
        window_days = len(price_series)

    if window_days < 20:  # Minimum threshold for meaningful volatility
        return None

    # Take the last N trading days
    recent_prices = price_series.tail(window_days)

    # Compute log returns
    log_returns = compute_log_returns(recent_prices)

    # Drop NaN values
    log_returns = log_returns.dropna()

    if len(log_returns) < 10:  # Need reasonable sample size
        return None

    # Compute standard deviation of returns
    daily_vol = log_returns.std()

    # Annualize the volatility
    annual_vol = daily_vol * np.sqrt(trading_days_per_year)

    return float(annual_vol)


def compute_rolling_volatility(
    prices: pd.DataFrame,
    window_days: int = 252,
    trading_days_per_year: int = 252
) -> pd.Series:
    """
    Compute rolling annualized volatility over time.

    Useful for charting historical volatility trends.

    Args:
        prices: DataFrame with 'Adj Close' column and DatetimeIndex
        window_days: Rolling window size in trading days
        trading_days_per_year: Typically 252 for US markets

    Returns:
        Series of annualized rolling volatility, indexed by date
    """
    if prices is None or prices.empty or 'Adj Close' not in prices.columns:
        return pd.Series(dtype=float)

    price_series = prices['Adj Close'].dropna()

    # Compute log returns
    log_returns = compute_log_returns(price_series)

    # Compute rolling standard deviation
    rolling_std = log_returns.rolling(window=window_days, min_periods=20).std()

    # Annualize
    rolling_vol = rolling_std * np.sqrt(trading_days_per_year)

    return rolling_vol.dropna()


def compute_volatility_metrics(
    ticker: str,
    historical_prices: pd.DataFrame,
    current_price: float
) -> VolatilityMetrics:
    """
    Compute comprehensive volatility metrics for a ticker.

    Computes:
    - 1-year (252 trading days) realized volatility
    - 3-month (~63 trading days) realized volatility
    - 1-month (~21 trading days) realized volatility

    Args:
        ticker: Stock ticker symbol
        historical_prices: DataFrame with 'Adj Close' column
        current_price: Current underlying price

    Returns:
        VolatilityMetrics object with computed metrics
    """
    data_start = historical_prices.index.min() if not historical_prices.empty else None
    data_end = historical_prices.index.max() if not historical_prices.empty else None

    # Compute realized volatility for different windows
    hv_1y = compute_realized_volatility(historical_prices, window_days=252)
    hv_3m = compute_realized_volatility(historical_prices, window_days=63)
    hv_1m = compute_realized_volatility(historical_prices, window_days=21)

    return VolatilityMetrics(
        ticker=ticker,
        hv_1y=hv_1y,
        hv_3m=hv_3m,
        hv_1m=hv_1m,
        current_price=current_price,
        data_start_date=data_start,
        data_end_date=data_end
    )


def compare_iv_to_hv(
    implied_volatility: float,
    realized_volatility: float
) -> tuple[float, float]:
    """
    Compare implied volatility to realized volatility.

    Returns both the ratio and the difference.

    Args:
        implied_volatility: Current IV (as decimal, e.g., 0.25)
        realized_volatility: Historical volatility (as decimal)

    Returns:
        Tuple of (iv_to_hv_ratio, iv_minus_hv)
        - iv_to_hv_ratio: IV / HV (higher = IV is richer vs realized)
        - iv_minus_hv: IV - HV (in percentage points)
    """
    if realized_volatility is None or realized_volatility <= 0:
        return None, None

    if implied_volatility is None or implied_volatility <= 0:
        return None, None

    ratio = implied_volatility / realized_volatility
    difference = implied_volatility - realized_volatility

    return ratio, difference


def compute_richness_score(
    implied_volatility: Optional[float],
    realized_volatility: Optional[float]
) -> Optional[float]:
    """
    Compute a "richness score" for IV vs HV.

    This is a heuristic measure where:
    - Score > 1.0: IV is higher than HV (rich)
    - Score = 1.0: IV equals HV (fair value)
    - Score < 1.0: IV is lower than HV (cheap)

    Currently uses the simple ratio IV / HV, but could be extended
    to incorporate percentile rankings, z-scores, etc.

    Args:
        implied_volatility: Current IV (as decimal)
        realized_volatility: Historical volatility (as decimal)

    Returns:
        Richness score (IV / HV ratio), or None if cannot be computed
    """
    ratio, _ = compare_iv_to_hv(implied_volatility, realized_volatility)
    return ratio


def format_volatility_pct(vol: Optional[float]) -> str:
    """
    Format volatility as a percentage string.

    Args:
        vol: Volatility as decimal (e.g., 0.2534)

    Returns:
        Formatted string (e.g., "25.34%")
    """
    if vol is None:
        return "N/A"
    return f"{vol * 100:.2f}%"
