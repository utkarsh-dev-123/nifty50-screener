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

def get_nifty500_tickers():
    """Fetch live Nifty 500 constituents from NSE India and return in Yahoo Finance .NS format."""
    print("Fetching Nifty 500 constituents from NSE India...")
    with NSE(download_folder=Path("."), server=False) as nse:
        data = nse.listEquityStocksByIndex("NIFTY 500")
    tickers = [item["symbol"] + ".NS" for item in data["data"]]
    print(f"  Fetched {len(tickers)} constituents.\n")
    return tickers


# ── Graham balance-sheet screens ─────────────────────────────────────────────

def passes_graham_screens(ticker, info):
    """
    Returns a dict with per-screen results and an overall pass/fail.
    Missing data → None (benefit of the doubt; treated as passing).

    Screen 6: debtToEquity < 100  (yFinance reports D/E as %, 100 ≡ 1.0×)
    Screen 7: currentRatio > 2.0
    Screen 8: totalDebt < 2 × (currentAssets − totalLiabilities)
    """
    failures = []

    # Screen 6 — debt-to-equity
    de = safe_float(info.get("debtToEquity"))
    if de is not None:
        s6 = de < 100
        if not s6:
            failures.append(f"D/E {de:.1f}% ≥ 100%")
    else:
        s6 = None

    # Screen 7 — current ratio
    cr = safe_float(info.get("currentRatio"))
    if cr is not None:
        s7 = cr > 2.0
        if not s7:
            failures.append(f"current ratio {cr:.2f} ≤ 2.0")
    else:
        s7 = None

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
