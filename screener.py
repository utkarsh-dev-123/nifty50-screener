"""
Nifty 200 Falling Knife Stock Screener — v2
Powered by Google Gemini API (free — no credit card needed)

What's new in v2:
  - Expanded to 20 stocks (from 7)
  - Quality pre-filter: revenue growth > 0, OCF > 0, ROE > 12%, margin > 8%
  - Sector-aware filter: banks/NBFCs and PSUs get relaxed thresholds
  - Drawdown filter: only stocks 20–65% below their 52W high
  - Dual lookback: both 1-month AND 3-month must be negative, 3M not worse than -40%
  - Volume spike detection: flags panic selling
  - Tighter Gemini prompt: no vague catalysts allowed
"""

import os
import json
import math
import datetime
import yfinance as yf
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OUTPUT_FILE    = "data.json"

# ── Sector classification for filter overrides ────────────────────────────────
# Banks and NBFCs: skip margin filter, use lower ROE threshold
BANK_NBFC_TICKERS = {
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANDHANBNK", "FEDERALBNK", "IDFCFIRSTB", "RBLBANK", "AUBANK", "CUB",
    "INDIANB", "BANKBARODA", "CANBK", "PNB", "UNIONBANK", "UCOBANK",
    "BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM",
    "LICHSGFIN", "CANFINHOME", "POONAWALLA", "SHRIRAMFIN", "ABCAPITAL",
    "SBICARD", "JIOFIN", "HDFCAMC", "UTIAMC", "CAMS", "ISEC", "NUVAMA",
    "LICI", "SBILIFE", "HDFCLIFE", "ICICIGI", "ICICIPRULI", "STARHEALTH",
    "NIACL", "MFSL",
}

# PSUs: loosen ROE to 8%, strict on OCF
PSU_TICKERS = {
    "NTPC", "ONGC", "COALINDIA", "POWERGRID", "BHEL", "SAIL", "NMDC",
    "GAIL", "IOC", "BPCL", "HINDPETRO", "OIL", "NHPC", "NLCINDIA",
    "RECLTD", "PFC", "IRCTC", "CONCOR", "RAILTEL", "IREDA", "LICI",
    "BANKBARODA", "CANBK", "PNB", "UNIONBANK", "UCOBANK", "INDIANB",
}

# Capital goods / infra: lumpy cash flows, loosen OCF filter
CAPEX_HEAVY_TICKERS = {
    "LT", "SIEMENS", "ABB", "THERMAX", "CUMMINSIND", "BHEL", "TIINDIA",
    "TATAPOWER", "ADANIPOWER", "ADANIGREEN", "ADANIPORTS",
}

# ── Full Nifty 200 constituent list ───────────────────────────────────────────
NIFTY200_TICKERS = [
    # ── Nifty 50 ──────────────────────────────────────────────────────────────
    "RELIANCE.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "TCS.NS",
    "ICICIBANK.NS", "INFY.NS", "BAJFINANCE.NS", "LT.NS", "HINDUNILVR.NS",
    "SUNPHARMA.NS", "MARUTI.NS", "HCLTECH.NS", "M&M.NS", "AXISBANK.NS",
    "ITC.NS", "TITAN.NS", "KOTAKBANK.NS", "NTPC.NS", "ONGC.NS",
    "ULTRACEMCO.NS", "ADANIPORTS.NS", "WIPRO.NS", "BAJAJFINSV.NS",
    "TATAMOTORS.NS", "POWERGRID.NS", "NESTLEIND.NS", "TATASTEEL.NS",
    "JSWSTEEL.NS", "GRASIM.NS", "COALINDIA.NS", "ASIANPAINT.NS",
    "HINDALCO.NS", "DRREDDY.NS", "CIPLA.NS", "TECHM.NS", "TRENT.NS",
    "INDUSINDBK.NS", "EICHERMOT.NS", "BRITANNIA.NS", "APOLLOHOSP.NS",
    "HEROMOTOCO.NS", "BPCL.NS", "SHRIRAMFIN.NS", "BEL.NS",
    "BAJAJ-AUTO.NS", "DIVISLAB.NS", "SBILIFE.NS", "HDFCLIFE.NS", "JIOFIN.NS",

    # ── Nifty Next 50 (51–100) ────────────────────────────────────────────────
    "ADANIENT.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "AMBUJACEM.NS",
    "BANKBARODA.NS", "BHEL.NS", "BOSCHLTD.NS", "CANBK.NS", "CHOLAFIN.NS",
    "COLPAL.NS", "DABUR.NS", "DLF.NS", "GAIL.NS", "GODREJCP.NS",
    "HAVELLS.NS", "HINDPETRO.NS", "ICICIGI.NS", "ICICIPRULI.NS",
    "INDIANB.NS", "INDIGO.NS", "IOC.NS", "IRCTC.NS", "JINDALSTEL.NS",
    "JUBLFOOD.NS", "LICI.NS", "LODHA.NS", "LUPIN.NS", "MARICO.NS",
    "MOTHERSON.NS", "MUTHOOTFIN.NS", "NAUKRI.NS", "NHPC.NS", "NMDC.NS",
    "OFSS.NS", "PAGEIND.NS", "PAYTM.NS", "PFC.NS", "PIDILITIND.NS",
    "PIIND.NS", "PNB.NS", "POLICYBZR.NS", "RECLTD.NS", "SAIL.NS",
    "SIEMENS.NS", "TORNTPHARM.NS", "TATACONSUM.NS", "TIINDIA.NS",
    "TATAPOWER.NS", "VEDL.NS", "ZOMATO.NS",

    # ── Nifty Midcap 100 (101–200) ────────────────────────────────────────────
    "ABCAPITAL.NS", "ABFRL.NS", "ALKEM.NS", "APLLTD.NS", "ASTRAL.NS",
    "AUROPHARMA.NS", "AUBANK.NS", "BALKRISIND.NS", "BANDHANBNK.NS",
    "BATAINDIA.NS", "BERGEPAINT.NS", "BIOCON.NS", "BLUEDART.NS",
    "CAMS.NS", "CANFINHOME.NS", "CASTROLIND.NS", "CDSL.NS", "CESC.NS",
    "CGPOWER.NS", "COFORGE.NS", "CONCOR.NS", "CROMPTON.NS", "CUB.NS",
    "CUMMINSIND.NS", "DALBHARAT.NS", "DEEPAKNTR.NS", "DELHIVERY.NS",
    "DIXON.NS", "ELGIEQUIP.NS", "EMAMILTD.NS", "ESCORTS.NS",
    "EXIDEIND.NS", "FEDERALBNK.NS", "FLUOROCHEM.NS", "GLENMARK.NS",
    "GODREJPROP.NS", "GRANULES.NS", "GSPL.NS", "GUJGASLTD.NS",
    "HDFCAMC.NS", "HONASA.NS", "IDFCFIRSTB.NS", "IEX.NS", "INDHOTEL.NS",
    "INDUSTOWER.NS", "IREDA.NS", "ISEC.NS", "JKCEMENT.NS", "KAJARIACER.NS",
    "KPITTECH.NS", "LALPATHLAB.NS", "LAURUSLABS.NS", "LICHSGFIN.NS",
    "LTIM.NS", "LTTS.NS", "MANAPPURAM.NS", "MAXHEALTH.NS", "MCX.NS",
    "METROPOLIS.NS", "MFSL.NS", "MGL.NS", "MPHASIS.NS", "MRF.NS",
    "NATIONALUM.NS", "NIACL.NS", "NLCINDIA.NS", "NUVAMA.NS", "OBEROIRLTY.NS",
    "OIL.NS", "PCBL.NS", "PERSISTENT.NS", "PETRONET.NS", "PHOENIXLTD.NS",
    "POLYCAB.NS", "POONAWALLA.NS", "PRESTIGE.NS", "RADICO.NS", "RAILTEL.NS",
    "RBLBANK.NS", "ROUTE.NS", "SAFARI.NS", "SBICARD.NS", "SCHAEFFLER.NS",
    "SOLARINDS.NS", "SONACOMS.NS", "STARHEALTH.NS", "SUMICHEM.NS",
    "SUNDARMFIN.NS", "SUPREMEIND.NS", "SYNGENE.NS", "TATACHEM.NS",
    "TATACOMM.NS", "THERMAX.NS", "TIMKEN.NS", "UJJIVANSFB.NS",
    "UNIONBANK.NS", "UPL.NS", "UTIAMC.NS", "VARUNBEV.NS", "VOLTAS.NS",
    "ZYDUSLIFE.NS",
]

NIFTY200_TICKERS = list(dict.fromkeys(NIFTY200_TICKERS))


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_nan(obj):
    """Recursively replace NaN/Inf floats with None so JSON stays valid."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def safe_float(value, default=None):
    """Convert to float safely, return default if NaN/None/error."""
    try:
        v = float(value)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def get_sector_type(ticker):
    """Returns 'bank', 'psu', 'capex' or 'standard'."""
    sym = ticker.replace(".NS", "")
    if sym in BANK_NBFC_TICKERS:
        return "bank"
    if sym in PSU_TICKERS:
        return "psu"
    if sym in CAPEX_HEAVY_TICKERS:
        return "capex"
    return "standard"


# ── Quality pre-filter ────────────────────────────────────────────────────────

def passes_quality_filter(ticker, info):
    """
    Returns (passed: bool, reason: str)
    If data is unavailable for a metric, we pass through (benefit of the doubt).
    """
    sym = ticker.replace(".NS", "")
    sector_type = get_sector_type(ticker)

    # ── 1. Revenue growth must be positive ────────────────────────────────────
    rev_growth = safe_float(info.get("revenueGrowth"))
    if rev_growth is not None and rev_growth <= 0:
        return False, f"revenue shrinking ({rev_growth*100:.1f}%)"

    # ── 2. Operating cash flow must be positive ────────────────────────────────
    # Relaxed for capex-heavy sectors (lumpy project cash flows)
    if sector_type not in ("capex",):
        ocf = safe_float(info.get("operatingCashflow"))
        if ocf is not None and ocf <= 0:
            return False, f"negative operating cash flow"

    # ── 3. Net profit margin > 8% (skip for banks — they report differently) ──
    if sector_type == "standard":
        margin = safe_float(info.get("profitMargins"))
        if margin is not None and margin < 0.08:
            return False, f"thin margin ({margin*100:.1f}% < 8%)"

    # ── 4. ROE thresholds by sector type ──────────────────────────────────────
    roe = safe_float(info.get("returnOnEquity"))
    if roe is not None:
        if sector_type == "bank" and roe < 0.08:
            return False, f"low ROE for bank ({roe*100:.1f}% < 8%)"
        elif sector_type == "psu" and roe < 0.06:
            return False, f"low ROE for PSU ({roe*100:.1f}% < 6%)"
        elif sector_type in ("standard", "capex") and roe < 0.12:
            return False, f"low ROE ({roe*100:.1f}% < 12%)"

    return True, "ok"


# ── Main data fetcher ─────────────────────────────────────────────────────────

def fetch_candidates(n=20):
    """
    Full pipeline:
      1. Fetch 3-month price history for all Nifty 200 stocks
      2. Apply quality pre-filter using fundamentals
      3. Apply drawdown filter (20–65% below 52W high)
      4. Apply dual lookback (1M negative, 3M negative but > -40%)
      5. Detect volume spike (panic selling signal)
      6. Rank by 1-month decline, return top n
    """
    print(f"Scanning {len(NIFTY200_TICKERS)} Nifty 200 stocks...\n")

    passed_quality   = 0
    failed_quality   = 0
    failed_drawdown  = 0
    failed_lookback  = 0
    candidates       = []

    for ticker in NIFTY200_TICKERS:
        sym = ticker.replace(".NS", "")
        try:
            # ── Fetch 3 months of price history ───────────────────────────────
            hist = yf.download(ticker, period="3mo", interval="1d",
                               progress=False, auto_adjust=True)
            if hist.empty or len(hist) < 10:
                continue

            close = hist["Close"]
            if hasattr(close, "squeeze"):
                close = close.squeeze()
            if hasattr(close, "columns"):
                continue

            volume = hist["Volume"]
            if hasattr(volume, "squeeze"):
                volume = volume.squeeze()

            current_price = float(close.iloc[-1])
            if math.isnan(current_price):
                continue

            # ── 1-month change (last ~21 trading days) ─────────────────────────
            idx_1m = max(0, len(close) - 21)
            price_1m_ago = float(close.iloc[idx_1m])
            if math.isnan(price_1m_ago) or price_1m_ago == 0:
                continue
            change_1m = ((current_price - price_1m_ago) / price_1m_ago) * 100

            # ── 3-month change ─────────────────────────────────────────────────
            price_3m_ago = float(close.iloc[0])
            if math.isnan(price_3m_ago) or price_3m_ago == 0:
                continue
            change_3m = ((current_price - price_3m_ago) / price_3m_ago) * 100

            # ── 52-week high (from yfinance info) ──────────────────────────────
            info = yf.Ticker(ticker).info
            high_52w = safe_float(info.get("fiftyTwoWeekHigh"))

            # ── FILTER: Dual lookback ──────────────────────────────────────────
            # Both 1M and 3M must be negative (stock is in a falling trend)
            # 3M decline must not be worse than -40% (avoid structural collapses)
            if change_1m >= 0:
                failed_lookback += 1
                continue
            if change_3m >= 0:
                failed_lookback += 1
                continue
            if change_3m < -40:
                failed_lookback += 1
                continue

            # ── FILTER: Drawdown from 52W high (20% to 65%) ───────────────────
            if high_52w and high_52w > 0:
                drawdown = ((current_price - high_52w) / high_52w) * 100
                if drawdown > -20:   # Not fallen enough to be interesting
                    failed_drawdown += 1
                    continue
                if drawdown < -65:   # Too far gone — likely structural
                    failed_drawdown += 1
                    continue
            else:
                drawdown = None

            # ── FILTER: Quality pre-filter ────────────────────────────────────
            passed, reason = passes_quality_filter(ticker, info)
            if not passed:
                failed_quality += 1
                print(f"  ✗ {sym:20s} quality fail: {reason}")
                continue

            passed_quality += 1

            # ── Volume spike detection ────────────────────────────────────────
            # Compare last 5 days average volume vs 3-month average
            avg_vol_3m   = float(volume.mean())
            avg_vol_5d   = float(volume.iloc[-5:].mean())
            volume_ratio = round(avg_vol_5d / avg_vol_3m, 2) if avg_vol_3m > 0 else None
            panic_selling = volume_ratio is not None and volume_ratio >= 1.5

            candidates.append({
                "ticker":        sym,
                "price":         round(current_price, 2),
                "change_1m":     round(change_1m, 2),
                "change_3m":     round(change_3m, 2),
                "drawdown_52w":  round(drawdown, 1) if drawdown else None,
                "volume_ratio":  volume_ratio,
                "panic_selling": panic_selling,
            })

        except Exception as e:
            print(f"  Skipping {ticker}: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  Filter summary:")
    print(f"    Quality pre-filter:  {passed_quality} passed, {failed_quality} failed")
    print(f"    Drawdown filter:     {failed_drawdown} eliminated")
    print(f"    Dual lookback:       {failed_lookback} eliminated")
    print(f"    Candidates left:     {len(candidates)}")

    # ── Rank by worst 1-month change, take top n ───────────────────────────────
    candidates.sort(key=lambda x: x["change_1m"])
    top = candidates[:n]
    print(f"\n  Top {n} falling knives: {[s['ticker'] for s in top]}\n")
    return top


# ── Fundamentals fetcher ──────────────────────────────────────────────────────

def fetch_fundamentals(ticker_sym):
    """Fetch detailed fundamentals for a single stock for the Gemini prompt."""
    try:
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


# ── Gemini analysis ───────────────────────────────────────────────────────────

def analyse_with_gemini(stocks):
    print("Sending to Gemini for analysis...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    today       = datetime.date.today().strftime("%B %d, %Y")
    stocks_json = json.dumps(stocks, indent=2)

    prompt = f"""Today is {today}. You are a senior equity research analyst specialising in Indian markets.

The investor uses a FALLING KNIFE strategy — buying fundamentally strong Nifty 200 stocks that have dropped sharply due to TEMPORARY or MACRO reasons, NOT structural business deterioration.

These stocks have already passed quality filters (positive revenue growth, positive OCF, minimum ROE, appropriate margins). They are also 20–65% below their 52-week highs. Your job is to add intelligence — search for the actual reason behind each fall and score them rigorously.

STOCKS DATA (includes 1M change, 3M change, drawdown from 52W high, and whether panic selling was detected):
{stocks_json}

SCORING RULES (strict — do not inflate scores):
  +2 if P/E is meaningfully below its 5-year historical average (not just slightly below)
  +2 if ROE is above 15% (use actual ROE from data provided)
  +2 if balance sheet is appropriate for sector (D/E < 0.5 for non-financials; for banks use NPA quality)
  +2 if a SPECIFIC, CONCRETE, DATED catalyst exists within the next 60 days (earnings date, policy decision, order announcement — NOT "sector may recover" or "management may improve guidance")
  +2 if the fall is clearly macro/sentiment driven (FII selling, crude spike, rate fears, geopolitics) NOT structural (losing market share, revenue decline, management fraud, regulatory action)

IMPORTANT RULES:
- If promoter pledging is above 20%, set score to max 4 regardless of other factors. Search for this.
- If the reason for the fall is a structural business problem (not macro), set macro_driven = false and deduct accordingly.
- For catalyst_ok = true, the catalyst MUST have a specific date or event. "Sector recovery" or "market sentiment improvement" does NOT count.
- If panic_selling is true in the data, that is a positive signal (capitulation) — factor it in.
- Sector concentration: if more than 3 stocks are from the same sector, note this in market_context.

Score 8-10 = Strong Buy (Tranche 1 now). Score 6-7 = Buy (Tranche 1 on confirmation). Score 4-5 = Watch. Below 4 = Avoid.

Respond ONLY with valid JSON. No markdown, no explanation, no text outside the JSON object.

{{
  "date": "{today}",
  "market_context": "3 sentences: current Nifty 200 macro backdrop, what is driving the selling, and what a falling knife investor should watch for this week",
  "stocks": [
    {{
      "ticker": "...",
      "name": "...",
      "why_fell": "2 specific sentences citing actual recent news or events — no vague statements",
      "catalyst": "Specific event with date if possible, e.g. 'Q4 results on April 14' or 'RBI policy on June 6'. Write NONE if no concrete catalyst exists.",
      "promoter_pledge_pct": "X% or Unknown — search for this",
      "value_trap_risk": "low/medium/high — one sentence with specific reason",
      "score": 7,
      "action": "Strong Buy (Tranche 1)",
      "thesis_break": "One specific, measurable condition that invalidates this thesis, e.g. 'Revenue growth turns negative in Q4 results'",
      "score_breakdown": {{
        "pe_ok": true,
        "roe_ok": true,
        "debt_ok": true,
        "catalyst_ok": true,
        "macro_driven": true
      }}
    }}
  ]
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        raw = ""
        if hasattr(response, "text") and response.text:
            raw = response.text.strip()
        elif hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and candidate.content:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            raw += part.text
            raw = raw.strip()
        if not raw:
            raise ValueError("Empty response with search grounding")
    except Exception as e:
        print(f"  Search grounding failed ({e}), retrying without search...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = ""
        if hasattr(response, "text") and response.text:
            raw = response.text.strip()
        elif hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and candidate.content:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            raw += part.text
            raw = raw.strip()

    print(f"  Gemini response length: {len(raw)} chars")

    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]

    return json.loads(raw)


# ── Save results ──────────────────────────────────────────────────────────────

def save_results(analysis, stocks):
    fund_map = {s["ticker"]: s for s in stocks}
    for stock in analysis["stocks"]:
        fund = fund_map.get(stock["ticker"], {})
        price_data = fund_map.get(stock["ticker"], {})
        stock.update({
            "price":            price_data.get("price", "N/A"),
            "change_1m":        price_data.get("change_1m", "N/A"),
            "change_3m":        price_data.get("change_3m", "N/A"),
            "drawdown_52w":     price_data.get("drawdown_52w", "N/A"),
            "volume_ratio":     price_data.get("volume_ratio", "N/A"),
            "panic_selling":    price_data.get("panic_selling", False),
            "name":             fund.get("name", stock["ticker"]),
            "sector":           fund.get("sector", "N/A"),
            "pe_ratio":         fund.get("pe_ratio", "N/A"),
            "forward_pe":       fund.get("forward_pe", "N/A"),
            "roe":              fund.get("roe", "N/A"),
            "debt_to_equity":   fund.get("debt_to_equity", "N/A"),
            "operating_margin": fund.get("operating_margin", "N/A"),
            "net_margin":       fund.get("net_margin", "N/A"),
            "revenue_growth":   fund.get("revenue_growth", "N/A"),
            "ocf_cr":           fund.get("ocf_cr", "N/A"),
            "market_cap_cr":    fund.get("market_cap_cr", "N/A"),
            "52w_high":         fund.get("52w_high", "N/A"),
            "52w_low":          fund.get("52w_low", "N/A"),
        })

    analysis["generated_at"] = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    analysis["index"]        = "Nifty 200"
    analysis["version"]      = "2.0"

    clean = clean_nan(analysis)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(clean, f, indent=2)
    print(f"  Saved → {OUTPUT_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  Nifty 200 Screener v2  —  {datetime.date.today()}")
    print(f"{'='*55}\n")

    # Step 1: Scan all stocks through the full filter pipeline
    candidates = fetch_candidates(n=20)

    if not candidates:
        print("ERROR: No candidates passed all filters — market may be closed or filters too strict.")
        raise SystemExit(1)

    # Step 2: Fetch detailed fundamentals for the 20 candidates
    print("Fetching fundamentals for candidates...")
    for stock in candidates:
        print(f"  {stock['ticker']}")
        stock.update(fetch_fundamentals(stock["ticker"]))

    # Step 3: Gemini analysis
    analysis = analyse_with_gemini(candidates)
    print(f"\n  Analysis done. {len(analysis.get('stocks', []))} stocks scored.\n")

    # Step 4: Save
    save_results(analysis, candidates)
    print("\nDone! ✓\n")


if __name__ == "__main__":
    main()
