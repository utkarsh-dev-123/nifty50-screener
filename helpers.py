"""
helpers.py — utility functions extracted from main.py.
"""

import math
from pathlib import Path

import yfinance as yf
from nse import NSE

# ── Sector classification sets ────────────────────────────────────────────────

BANK_NBFC_TICKERS = {
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANDHANBNK", "FEDERALBNK", "IDFCFIRSTB", "RBLBANK", "AUBANK", "CUB",
    "INDIANB", "BANKBARODA", "CANBK", "PNB", "UNIONBANK", "UCOBANK",
    "BANKINDIA", "IOB", "CENTRALBK", "MAHABANK", "YESBANK", "IDBI",
    "BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM",
    "LICHSGFIN", "CANFINHOME", "POONAWALLA", "SHRIRAMFIN", "ABCAPITAL",
    "SBICARD", "JIOFIN", "HDFCAMC", "UTIAMC", "CAMS", "ISEC", "NUVAMA",
    "LICI", "SBILIFE", "HDFCLIFE", "ICICIGI", "ICICIPRULI", "STARHEALTH",
    "NIACL", "MFSL", "GICRE", "POLICYBZR", "BAJAJHFL", "LTFH",
    "360ONE", "MOTILALOFS", "SUNDARMFIN",
}

PSU_TICKERS = {
    "NTPC", "ONGC", "COALINDIA", "POWERGRID", "BHEL", "SAIL", "NMDC",
    "GAIL", "IOC", "BPCL", "HINDPETRO", "OIL", "NHPC", "NLCINDIA",
    "RECLTD", "PFC", "IRCTC", "CONCOR", "RAILTEL", "IREDA", "LICI",
    "BANKBARODA", "CANBK", "PNB", "UNIONBANK", "UCOBANK", "INDIANB",
    "HAL", "BEL", "RVNL", "COCHINSHIP", "MAZAGONDOCK", "IRFC",
    "HUDCO", "MRPL", "BANKINDIA", "IOB", "CENTRALBK", "MAHABANK",
    "SJVN", "NBCC", "TITAGARH", "BEML",
}

CAPEX_HEAVY_TICKERS = {
    "LT", "SIEMENS", "ABB", "THERMAX", "CUMMINSIND", "BHEL", "TIINDIA",
    "TATAPOWER", "ADANIPOWER", "ADANIGREEN", "ADANIPORTS", "ADANIENT",
    "JSWENERGY", "TORNTPOWER", "SUZLON", "WAAREEENER", "PREMIERENE",
    "GMRINFRA", "APLAPOLLO",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_float(value, default=None):
    try:
        v = float(value)
        return default if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return default


def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def get_sector_type(ticker):
    sym = ticker.replace(".NS", "")
    if sym in BANK_NBFC_TICKERS:   return "bank"
    if sym in PSU_TICKERS:         return "psu"
    if sym in CAPEX_HEAVY_TICKERS: return "capex"
    return "standard"


# ── Live Nifty 500 constituent fetch ─────────────────────────────────────────

def get_nifty500_stocks():
    """
    Fetch live Nifty 500 constituents from NSE India.
    Returns a list of dicts with symbol, ticker, price data, and metadata.
    """
    print("Fetching Nifty 500 constituents from NSE India...")
    with NSE(download_folder=Path("."), server=False) as nse:
        data = nse.listEquityStocksByIndex("NIFTY 500")

    stocks = []
    for item in data["data"]:
        sym = item.get("symbol", "")
        if not sym:
            continue
        stocks.append({
            "symbol":    sym,
            "ticker":    sym + ".NS",
            "pChange":   safe_float(item.get("pChange")),
            "lastPrice": safe_float(item.get("lastPrice")),
            "yearHigh":  safe_float(item.get("yearHigh")),
            "yearLow":   safe_float(item.get("yearLow")),
            "name":      item.get("meta", {}).get("companyName", sym),
        })
    print(f"  Fetched {len(stocks)} Nifty 500 stocks from NSE")
    return stocks


def get_nifty500_tickers():
    """Fallback: return ticker strings (Yahoo Finance .NS format) from get_nifty500_stocks()."""
    stocks = get_nifty500_stocks()
    return [s["ticker"] for s in stocks]


# ── Graham balance-sheet screens ─────────────────────────────────────────────

# Sectors where currentRatio < 2 is structurally normal:
# Financial: leverage is their core business model
# Technology / Communication Services: asset-light,
#   low working capital, subscription/service revenue
SCREEN7_EXEMPT_SECTORS = {
    "Financial Services", "Banking", "Insurance",
    "Asset Management", "Capital Markets",
    "Technology",
    "Communication Services",
}


def passes_graham_screens(ticker, info):
    """
    Returns a dict with per-screen results and an overall pass/fail.
    Missing data → None (benefit of the doubt; treated as passing).

    Screen 6: debtToEquity < 100  (yFinance reports D/E as %, 100 ≡ 1.0×)
    Screen 7: currentRatio > 2.0  (skipped for SCREEN7_EXEMPT_SECTORS —
      financials and asset-light tech/services where metric is not meaningful)
    Screen 8: totalDebt < 2 × (currentAssets − totalLiabilities)
    """
    failures = []
    sector       = info.get("sector", "")
    is_financial = sector in SCREEN7_EXEMPT_SECTORS

    # Screen 6 — debt-to-equity
    de = safe_float(info.get("debtToEquity"))
    if de is not None:
        s6 = de < 100
        if not s6:
            failures.append(f"D/E {de:.1f}% ≥ 100%")
    else:
        s6 = None

    # Screen 7 — current ratio
    # Skipped for financial sector AND asset-light sectors (Technology,
    # Communication Services) where ratio < 2 is structurally normal
    if sector in SCREEN7_EXEMPT_SECTORS:
        s7 = None  # benefit of doubt — metric not meaningful here
    else:
        cr = safe_float(info.get("currentRatio"))
        if cr is not None:
            s7 = cr > 2.0
            if not s7:
                failures.append(f"current ratio {cr:.2f} ≤ 2.0")
        else:
            s7 = None
            # Uncomment to debug Screen 7 null coverage:
            # print(f"    Screen 7: currentRatio missing for {ticker} (sector: {sector})")

    # Screen 8 — total debt vs net current assets
    total_debt  = safe_float(info.get("totalDebt"))
    curr_assets = safe_float(info.get("currentAssets") or info.get("totalCurrentAssets"))
    total_liab  = safe_float(info.get("totalLiabilities") or info.get("totalLiab"))
    if total_debt is not None and curr_assets is not None and total_liab is not None:
        s8 = total_debt < 2 * (curr_assets - total_liab)
        if not s8:
            nca = curr_assets - total_liab
            failures.append(f"debt {total_debt/1e7:.0f}Cr > 2×NCA {nca/1e7:.0f}Cr")
    else:
        s8 = None

    passed = len(failures) == 0
    return {
        "passed":            passed,
        "reason":            "; ".join(failures) if failures else "ok",
        "s6_debt_equity":    s6,
        "s7_current_ratio":  s7,
        "s8_debt_cover":     s8,
    }


# ── Pledge helper ─────────────────────────────────────────────────────────────

def _find_pledge(obj):
    """Recursively search any dict/list structure for a pledge percentage field."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "pledge" in k.lower():
                val = safe_float(v)
                if val is not None:
                    return val
            found = _find_pledge(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_pledge(item)
            if found is not None:
                return found
    return None


# ── Fundamentals fetcher ──────────────────────────────────────────────────────

def fetch_fundamentals(ticker_sym, info=None):
    try:
        if info is None:
            info = yf.Ticker(ticker_sym + ".NS").info

        def pct(key):
            v = info.get(key)
            try:
                f = float(v)
                return round(f * 100, 1) if not math.isnan(f) else "N/A"
            except Exception:
                return "N/A"

        def safe(key):
            v = info.get(key, "N/A")
            try:
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return "N/A"
            except Exception:
                pass
            return v

        return {
            "name":             info.get("longName", ticker_sym),
            "sector":           info.get("sector", "N/A"),
            "pe_ratio":         safe("trailingPE"),
            "forward_pe":       safe("forwardPE"),
            "pb_ratio":         safe("priceToBook"),
            "roe":              pct("returnOnEquity"),
            "debt_to_equity":   safe("debtToEquity"),
            "operating_margin": pct("operatingMargins"),
            "net_margin":       pct("profitMargins"),
            "revenue_growth":   pct("revenueGrowth"),
            "ocf_cr":           round(info.get("operatingCashflow", 0) / 1e7, 1) if info.get("operatingCashflow") else "N/A",
            "market_cap_cr":    round(info.get("marketCap", 0) / 1e7, 0) if info.get("marketCap") else "N/A",
            "52w_high":         safe("fiftyTwoWeekHigh"),
            "52w_low":          safe("fiftyTwoWeekLow"),
        }
    except Exception as e:
        print(f"  Could not fetch fundamentals for {ticker_sym}: {e}")
        return {}
