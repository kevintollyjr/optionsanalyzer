# Enhancement Plan: Options Analytics Platform

## Implemented Features

### 1. Data Health Indicators (Per Ticker)
**Before each ticker's results table:**
- ✓ Underlying price status
- ✓ Historical data days loaded
- ✓ Options expirations loaded (with DTE range)
- ⚠ IV missing percentage (with chosen proxy mode)
- ⚠ Delta approximation status
- ❌ Fetch failures with specific errors

### 2. Missing Data Mode Controls (Sidebar)
**For Missing IV:**
- Drop option entirely
- Use ATM IV as proxy for that expiry
- Use strike-weighted IV interpolation

**For Missing Delta:**
- Disable delta filtering
- Use Black-Scholes approximation (current default)

**Global banner when in approximation mode**

### 3. Caching Layer
- Cache ticker data for 15 minutes per ticker
- Avoid re-hitting API on filter changes
- "Last Scan" snapshot with timestamp
- Dropdown to reload previous scans
- Compare day-over-day results

### 4. Cross-Ticker Leaderboard View
**Consolidated table across all tickers with:**
- Ticker
- Expiration (DTE)
- Strike (% OTM)
- IV, HV_ref, IV/HV ratio
- Richness score
- Ann. premium yield
- Combo score (weighted)

**Top filters:**
- Multi-select tickers
- Min richness threshold
- Min annualized yield
- Sortable by any column

### 5. Presets System
**Saved configurations:**
- Preset dropdown: Default / 25D-Near / 25D-MidTerm / Custom
- Save current settings as new preset
- Delete/rename presets
- Store in session state (persists during session)

### 6. CSV Export Everywhere
- Export button on every table
- Timestamp in filename
- Full unformatted data for Excel analysis

### 7. Link-Outs (Nice to Have)
- Links to Yahoo Finance option chain
- Constructable broker links

### 8. Details Card on Row Click (Future Enhancement)
- Pop-up with full metrics
- Simple P&L scenarios table
- Quick sanity checks

## Implementation Priority

**Phase 1 (Now):**
- Data health indicators
- Missing-data mode controls
- Cross-ticker leaderboard
- CSV exports

**Phase 2 (Next):**
- Presets system
- Caching layer
- Link-outs

**Phase 3 (Future):**
- Details card on row click
- Advanced P&L modeling
