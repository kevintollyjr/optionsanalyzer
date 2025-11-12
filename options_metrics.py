"""
Options metrics calculation module.

This module provides functions to compute:
- Premium yields (non-annualized and annualized)
- Option moneyness
- Black-Scholes approximations for delta when not provided
- Filtering and scoring of option candidates
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, List
import numpy as np
from scipy.stats import norm

from data_provider import OptionContract


@dataclass
class OptionMetrics:
    """Container for computed option metrics."""
    # Original contract data
    contract: OptionContract

    # Computed metrics
    dte: int  # Days to expiration
    option_price: Optional[float]  # Mid price or fallback
    premium_yield: Optional[float]  # P / S (non-annualized)
    annualized_premium_yield: Optional[float]  # Annualized yield
    moneyness: Optional[float]  # (Strike - Spot) / Spot
    iv_to_hv_ratio: Optional[float]  # IV / HV
    iv_minus_hv: Optional[float]  # IV - HV (in percentage points)
    richness_score: Optional[float]  # Composite richness measure
    computed_delta: Optional[float]  # BS delta if not provided
    bid_ask_spread_pct: Optional[float]  # Spread as % of mid


def compute_days_to_expiry(expiration: datetime, reference_date: date = None) -> int:
    """
    Compute days to expiration.

    Args:
        expiration: Expiration datetime
        reference_date: Reference date (default: today)

    Returns:
        Number of days to expiration (integer)
    """
    if reference_date is None:
        reference_date = date.today()

    exp_date = expiration.date() if isinstance(expiration, datetime) else expiration
    delta = exp_date - reference_date

    return max(delta.days, 0)


def compute_premium_yield(option_price: float, underlying_price: float) -> float:
    """
    Compute premium yield (non-annualized).

    Formula: premium_yield = option_price / underlying_price

    This represents the percentage return if the option expires worthless.

    Args:
        option_price: Option price per share (mid or last)
        underlying_price: Current underlying price

    Returns:
        Premium yield as a decimal (e.g., 0.02 = 2%)
    """
    if underlying_price <= 0:
        return 0.0

    return option_price / underlying_price


def compute_annualized_premium_yield(
    premium_yield: float,
    days_to_expiry: int
) -> float:
    """
    Compute annualized premium yield using simple linear scaling.

    Formula: annualized_yield = premium_yield * (365 / days_to_expiry)

    Note: This uses simple interest, not compounding.

    Args:
        premium_yield: Non-annualized premium yield (decimal)
        days_to_expiry: Days until expiration

    Returns:
        Annualized premium yield as a decimal
    """
    if days_to_expiry <= 0:
        return 0.0

    return premium_yield * (365.0 / days_to_expiry)


def compute_moneyness(strike: float, spot: float) -> float:
    """
    Compute option moneyness.

    Formula: moneyness = (strike - spot) / spot

    For calls:
    - Negative = ITM (in-the-money)
    - Zero = ATM (at-the-money)
    - Positive = OTM (out-of-the-money)

    Args:
        strike: Option strike price
        spot: Current underlying price

    Returns:
        Moneyness as a decimal
    """
    if spot <= 0:
        return 0.0

    return (strike - spot) / spot


def black_scholes_delta(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str = 'CALL'
) -> float:
    """
    Compute Black-Scholes delta.

    Delta represents the rate of change of option price with respect to
    underlying price. For a call, delta is between 0 and 1.

    Formula:
        d1 = [ln(S/K) + (r + σ²/2) * T] / (σ * sqrt(T))
        delta_call = N(d1)
        delta_put = N(d1) - 1

    where N() is the cumulative standard normal distribution.

    Args:
        spot: Current underlying price
        strike: Option strike price
        time_to_expiry_years: Time to expiration in years
        risk_free_rate: Risk-free interest rate (as decimal, e.g., 0.05 for 5%)
        volatility: Implied volatility (as decimal, e.g., 0.25 for 25%)
        option_type: 'CALL' or 'PUT'

    Returns:
        Delta value
    """
    if time_to_expiry_years <= 0 or volatility <= 0 or spot <= 0 or strike <= 0:
        return 0.0

    try:
        # Compute d1
        d1 = (
            np.log(spot / strike) +
            (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry_years
        ) / (volatility * np.sqrt(time_to_expiry_years))

        # Compute delta based on option type
        if option_type.upper() == 'CALL':
            delta = norm.cdf(d1)
        else:  # PUT
            delta = norm.cdf(d1) - 1.0

        return float(delta)

    except (ValueError, ZeroDivisionError):
        return 0.0


def compute_option_metrics(
    contract: OptionContract,
    underlying_price: float,
    hv_reference: Optional[float] = None,
    risk_free_rate: float = 0.045,
    reference_date: date = None
) -> OptionMetrics:
    """
    Compute comprehensive metrics for an option contract.

    Args:
        contract: OptionContract object
        underlying_price: Current underlying price
        hv_reference: Reference historical volatility for comparison (e.g., hv_1y)
        risk_free_rate: Risk-free rate for BS delta calculation (default: 4.5%)
        reference_date: Reference date for DTE calculation (default: today)

    Returns:
        OptionMetrics object with all computed metrics
    """
    # Compute DTE
    dte = compute_days_to_expiry(contract.expiration, reference_date)

    # Get option price
    option_price = contract.mid_price

    # Compute premium yields
    premium_yield = None
    annualized_premium_yield = None
    if option_price is not None and option_price > 0 and underlying_price > 0:
        premium_yield = compute_premium_yield(option_price, underlying_price)
        annualized_premium_yield = compute_annualized_premium_yield(premium_yield, dte)

    # Compute moneyness
    moneyness = compute_moneyness(contract.strike, underlying_price)

    # Compute IV vs HV metrics
    iv_to_hv_ratio = None
    iv_minus_hv = None
    richness_score = None

    if contract.implied_volatility is not None and hv_reference is not None:
        if hv_reference > 0:
            iv_to_hv_ratio = contract.implied_volatility / hv_reference
            iv_minus_hv = contract.implied_volatility - hv_reference
            richness_score = iv_to_hv_ratio

    # Compute delta if not provided
    computed_delta = contract.delta
    if computed_delta is None and contract.implied_volatility is not None:
        time_to_expiry_years = dte / 365.0
        computed_delta = black_scholes_delta(
            spot=underlying_price,
            strike=contract.strike,
            time_to_expiry_years=time_to_expiry_years,
            risk_free_rate=risk_free_rate,
            volatility=contract.implied_volatility,
            option_type=contract.option_type
        )

    # Get bid-ask spread
    bid_ask_spread_pct = contract.bid_ask_spread_pct

    return OptionMetrics(
        contract=contract,
        dte=dte,
        option_price=option_price,
        premium_yield=premium_yield,
        annualized_premium_yield=annualized_premium_yield,
        moneyness=moneyness,
        iv_to_hv_ratio=iv_to_hv_ratio,
        iv_minus_hv=iv_minus_hv,
        richness_score=richness_score,
        computed_delta=computed_delta,
        bid_ask_spread_pct=bid_ask_spread_pct
    )


def filter_options(
    option_metrics: List[OptionMetrics],
    min_delta: Optional[float] = None,
    max_delta: Optional[float] = None,
    min_dte: Optional[int] = None,
    max_dte: Optional[int] = None,
    otm_only: bool = False,
    min_open_interest: Optional[int] = None,
    max_spread_pct: Optional[float] = None,
    underlying_price: Optional[float] = None
) -> List[OptionMetrics]:
    """
    Filter option metrics based on various criteria.

    Args:
        option_metrics: List of OptionMetrics to filter
        min_delta: Minimum absolute delta
        max_delta: Maximum absolute delta
        min_dte: Minimum days to expiration
        max_dte: Maximum days to expiration
        otm_only: If True, only include OTM options (strike >= spot for calls)
        min_open_interest: Minimum open interest
        max_spread_pct: Maximum bid-ask spread as percentage of mid
        underlying_price: Current underlying price (required if otm_only=True)

    Returns:
        Filtered list of OptionMetrics
    """
    filtered = []

    for opt in option_metrics:
        # Skip if essential data is missing
        if opt.option_price is None or opt.option_price <= 0:
            continue

        if opt.contract.strike is None or opt.contract.strike <= 0:
            continue

        # DTE filters
        if min_dte is not None and opt.dte < min_dte:
            continue

        if max_dte is not None and opt.dte > max_dte:
            continue

        # Delta filters
        if min_delta is not None or max_delta is not None:
            delta = opt.computed_delta
            if delta is None:
                # If delta filtering is required but delta is unavailable, skip
                continue

            abs_delta = abs(delta)
            if min_delta is not None and abs_delta < min_delta:
                continue

            if max_delta is not None and abs_delta > max_delta:
                continue

        # OTM filter
        if otm_only and underlying_price is not None:
            if opt.contract.option_type == 'CALL':
                if opt.contract.strike < underlying_price:
                    continue
            else:  # PUT
                if opt.contract.strike > underlying_price:
                    continue

        # Open interest filter
        if min_open_interest is not None:
            if opt.contract.open_interest is None or opt.contract.open_interest < min_open_interest:
                continue

        # Bid-ask spread filter
        if max_spread_pct is not None:
            if opt.bid_ask_spread_pct is None or opt.bid_ask_spread_pct > max_spread_pct:
                continue

        filtered.append(opt)

    return filtered


def format_percentage(value: Optional[float], decimals: int = 2) -> str:
    """Format a decimal value as a percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def format_number(value: Optional[float], decimals: int = 2) -> str:
    """Format a number with specified decimal places."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"
