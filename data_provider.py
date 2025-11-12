"""
Data provider abstraction layer for fetching underlying and option chain data.

This module provides a clean interface for fetching:
- Current underlying prices
- Historical price data for realized volatility calculations
- Option chains (calls only)

The design allows for easy substitution of data providers (e.g., yfinance, IBKR, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np
import yfinance as yf


@dataclass
class UnderlyingData:
    """Container for underlying stock data."""
    ticker: str
    current_price: float
    currency: str
    fetch_time: datetime


@dataclass
class OptionContract:
    """Container for a single option contract data."""
    ticker: str
    expiration: datetime
    strike: float
    option_type: str  # 'CALL' or 'PUT'
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    implied_volatility: Optional[float]
    delta: Optional[float]
    open_interest: Optional[int]
    volume: Optional[int]
    contract_symbol: Optional[str] = None

    @property
    def mid_price(self) -> Optional[float]:
        """
        Compute the mid price using the following priority:
        1. If bid and ask are both present and positive, use (bid + ask) / 2
        2. Otherwise, use last if available and reasonable
        3. Otherwise, use whichever of bid/ask is available
        """
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0

        if self.last is not None and self.last > 0:
            return self.last

        if self.bid is not None and self.bid > 0:
            return self.bid

        if self.ask is not None and self.ask > 0:
            return self.ask

        return None

    @property
    def bid_ask_spread_pct(self) -> Optional[float]:
        """
        Calculate bid-ask spread as a percentage of mid price.
        Returns None if cannot be calculated.
        """
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask <= 0:
            return None

        mid = self.mid_price
        if mid is None or mid <= 0:
            return None

        spread = self.ask - self.bid
        return (spread / mid) * 100.0


class DataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    def fetch_underlying_price(self, ticker: str) -> UnderlyingData:
        """Fetch current underlying price."""
        pass

    @abstractmethod
    def fetch_historical_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Fetch historical adjusted close prices.

        Returns:
            DataFrame with DatetimeIndex and at least an 'Adj Close' column
        """
        pass

    @abstractmethod
    def fetch_option_chain(
        self,
        ticker: str,
        expiration_dates: Optional[List[date]] = None
    ) -> List[OptionContract]:
        """
        Fetch option chain for calls only.

        Args:
            ticker: Stock ticker symbol
            expiration_dates: Optional list of specific expiration dates to fetch.
                             If None, fetch all available expirations.

        Returns:
            List of OptionContract objects
        """
        pass

    @abstractmethod
    def get_available_expirations(self, ticker: str) -> List[date]:
        """Get list of available option expiration dates."""
        pass


class YFinanceProvider(DataProvider):
    """Data provider implementation using yfinance."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def fetch_underlying_price(self, ticker: str) -> UnderlyingData:
        """Fetch current underlying price using yfinance."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Try multiple fields for current price
            current_price = (
                info.get('currentPrice') or
                info.get('regularMarketPrice') or
                info.get('previousClose')
            )

            if current_price is None or current_price <= 0:
                # Fallback: get latest from history
                hist = stock.history(period='1d')
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]

            if current_price is None or current_price <= 0:
                raise ValueError(f"Unable to fetch valid price for {ticker}")

            currency = info.get('currency', 'USD')

            return UnderlyingData(
                ticker=ticker,
                current_price=float(current_price),
                currency=currency,
                fetch_time=datetime.now()
            )

        except Exception as e:
            raise RuntimeError(f"Failed to fetch underlying price for {ticker}: {str(e)}")

    def fetch_historical_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """Fetch historical adjusted close prices using yfinance."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date, auto_adjust=False)

            if hist.empty:
                raise ValueError(f"No historical data available for {ticker}")

            # Ensure we have adjusted close
            if 'Adj Close' not in hist.columns and 'Close' in hist.columns:
                hist['Adj Close'] = hist['Close']

            return hist[['Adj Close']].copy()

        except Exception as e:
            raise RuntimeError(f"Failed to fetch historical prices for {ticker}: {str(e)}")

    def get_available_expirations(self, ticker: str) -> List[date]:
        """Get list of available option expiration dates."""
        try:
            stock = yf.Ticker(ticker)
            expirations = stock.options

            if not expirations:
                return []

            # Convert string dates to date objects
            return [datetime.strptime(exp, '%Y-%m-%d').date() for exp in expirations]

        except Exception as e:
            raise RuntimeError(f"Failed to fetch expiration dates for {ticker}: {str(e)}")

    def fetch_option_chain(
        self,
        ticker: str,
        expiration_dates: Optional[List[date]] = None
    ) -> List[OptionContract]:
        """Fetch option chain for calls only using yfinance."""
        try:
            stock = yf.Ticker(ticker)

            if expiration_dates is None:
                expiration_dates = self.get_available_expirations(ticker)

            if not expiration_dates:
                return []

            contracts = []

            for exp_date in expiration_dates:
                try:
                    # yfinance expects string format
                    exp_str = exp_date.strftime('%Y-%m-%d')

                    # Fetch option chain for this expiration
                    opt_chain = stock.option_chain(exp_str)
                    calls = opt_chain.calls

                    if calls.empty:
                        continue

                    # Convert expiration to datetime
                    exp_datetime = datetime.combine(exp_date, datetime.min.time())

                    # Process each call option
                    for _, row in calls.iterrows():
                        contract = OptionContract(
                            ticker=ticker,
                            expiration=exp_datetime,
                            strike=float(row.get('strike', 0)),
                            option_type='CALL',
                            bid=float(row['bid']) if pd.notna(row.get('bid')) and row.get('bid') > 0 else None,
                            ask=float(row['ask']) if pd.notna(row.get('ask')) and row.get('ask') > 0 else None,
                            last=float(row['lastPrice']) if pd.notna(row.get('lastPrice')) and row.get('lastPrice') > 0 else None,
                            implied_volatility=float(row['impliedVolatility']) if pd.notna(row.get('impliedVolatility')) else None,
                            delta=None,  # yfinance doesn't provide greeks directly
                            open_interest=int(row['openInterest']) if pd.notna(row.get('openInterest')) else None,
                            volume=int(row['volume']) if pd.notna(row.get('volume')) else None,
                            contract_symbol=row.get('contractSymbol')
                        )

                        contracts.append(contract)

                except Exception as e:
                    # Log but continue with other expirations
                    print(f"Warning: Failed to fetch options for {ticker} expiring {exp_date}: {str(e)}")
                    continue

            return contracts

        except Exception as e:
            raise RuntimeError(f"Failed to fetch option chain for {ticker}: {str(e)}")


def get_default_provider() -> DataProvider:
    """Get the default data provider (yfinance)."""
    return YFinanceProvider()
