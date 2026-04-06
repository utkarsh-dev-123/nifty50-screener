"""
Nifty 500 Falling Knife Stock Screener — v3
Powered by Google Gemini API (free — no credit card needed)

Scans all ~500 Nifty 500 stocks
Applies quality pre-filters, drawdown filter, dual lookback
Picks the 30 biggest losers that pass all filters
Sends to Gemini for deep analysis with Google Search grounding
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

# ── Full Nifty 500 ticker list (Yahoo Finance .NS format) ─────────────────────
NIFTY500_TICKERS = [
    # ── Large Cap (Nifty 100) ──────────────────────────────────────────────────
    "RELIANCE.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "TCS.NS",
    "ICICIBANK.NS", "INFY.NS", "BAJFINANCE.NS", "LT.NS", "HINDUNILVR.NS",
    "LICI.NS", "SUNPHARMA.NS", "MARUTI.NS", "HCLTECH.NS", "M&M.NS",
    "AXISBANK.NS", "ITC.NS", "TITAN.NS", "ONGC.NS", "KOTAKBANK.NS",
    "NTPC.NS", "ADANIPORTS.NS", "ULTRACEMCO.NS", "ADANIPOWER.NS", "BEL.NS",
    "DMART.NS", "JSWSTEEL.NS", "COALINDIA.NS", "POWERGRID.NS", "VEDL.NS",
    "BAJAJFINSV.NS", "HAL.NS", "BAJAJ-AUTO.NS", "TATASTEEL.NS", "ADANIENT.NS",
    "NESTLEIND.NS", "ZOMATO.NS", "HINDZINC.NS", "ASIANPAINT.NS", "HINDALCO.NS",
    "WIPRO.NS", "IOC.NS", "EICHERMOT.NS", "SBILIFE.NS", "GRASIM.NS",
    "SHRIRAMFIN.NS", "INDIGO.NS", "TVSMOTOR.NS", "DIVISLAB.NS", "JIOFIN.NS",
    "TECHM.NS", "ADANIGREEN.NS", "VARUNBEV.NS", "TORNTPHARM.NS", "PFC.NS",
    "UNIONBANK.NS", "BRITANNIA.NS", "ABB.NS", "PIDILITIND.NS", "DLF.NS",
    "BANKBARODA.NS", "CUMMINSIND.NS", "LTIM.NS", "MUTHOOTFIN.NS", "TRENT.NS",
    "TATAPOWER.NS", "HDFCLIFE.NS", "BPCL.NS", "PNB.NS", "IRFC.NS",
    "SOLARINDS.NS", "INDIANB.NS", "JINDALSTEL.NS", "BSE.NS", "CHOLAFIN.NS",
    "CANBK.NS", "ADANITRANS.NS", "ABBPOW.NS", "MOTHERSON.NS", "INDUSTOWER.NS",
    "TATAMOTORS.NS", "SIEMENS.NS", "CGPOWER.NS", "APOLLOHOSP.NS", "LUPIN.NS",
    "POLYCAB.NS", "TATACONSUM.NS", "GODREJCP.NS", "DRREDDY.NS", "HDFCAMC.NS",
    "HEROMOTOCO.NS", "BAJAJHLD.NS", "MARICO.NS", "GEVERNOVAIND.NS", "AMBUJACEM.NS",
    "CIPLA.NS", "BOSCHLTD.NS", "GMRINFRA.NS", "IDEA.NS", "GAIL.NS",
    "MAXHEALTH.NS", "MAZAGONDOCK.NS", "MCDOWELL-N.NS", "WAAREEENER.NS",
    "ASHOKLEY.NS", "ZYDUSLIFE.NS", "BHEL.NS", "JSWENERGY.NS", "RECLTD.NS",
    "ICICIGI.NS", "SHREECEM.NS", "INDHOTEL.NS", "PERSISTENT.NS", "MANKIND.NS",
    "BFUTILITIE.NS", "LLOYDSME.NS", "ABCAPITAL.NS", "OIL.NS", "AUROPHARMA.NS",
    "SWIGGY.NS", "NHPC.NS", "BHARATFORG.NS", "HEXATRAD.NS", "IDBI.NS",
    "HAVELLS.NS", "DABUR.NS", "NATIONALUM.NS", "ICICIPRULI.NS", "SRF.NS",

    # ── Mid Cap (Nifty Midcap 150) ─────────────────────────────────────────────
    "NYKAA.NS", "LODHA.NS", "HINDPETRO.NS", "NMDC.NS", "TORNTPOWER.NS",
    "GICRE.NS", "POLICYBZR.NS", "FEDERALBNK.NS", "BAJAJHFL.NS", "AUBANK.NS",
    "NAUKRI.NS", "PAYTM.NS", "SAIL.NS", "BANKINDIA.NS", "IOB.NS",
    "ALKEM.NS", "LINDEINDIA.NS", "MCX.NS", "OFSS.NS", "INDUSINDBK.NS",
    "SBICARD.NS", "DIXON.NS", "LTFH.NS", "FORTIS.NS", "JSWINFRA.NS",
    "JSTAINLESS.NS", "UNOMINDA.NS", "GLENMARK.NS", "SCHAEFFLER.NS",
    "ADANITOTGAS.NS", "BIOCON.NS", "LAURUSLABS.NS", "YESBANK.NS",
    "SUZLON.NS", "ABBOTINDIA.NS", "COROMANDEL.NS", "OBEROIRLTY.NS",
    "PHOENIXLTD.NS", "RVNL.NS", "MRF.NS", "NIPPONLIFE.NS", "APLAPOLLO.NS",
    "IDFCFIRSTB.NS", "PATANJALI.NS", "JSWINFRA.NS", "MFSL.NS",
    "SUNDARMFIN.NS", "UPL.NS", "FCTLTD.NS", "COLPAL.NS", "TIINDIA.NS",
    "PRESTIGE.NS", "MAHABANK.NS", "BERGEPAINT.NS", "HINDCOPPER.NS",
    "SUPREMEIND.NS", "GODREJPROP.NS", "BHARATDYN.NS", "PIIND.NS",
    "MPHASIS.NS", "ASTRAL.NS", "PREMIERENE.NS", "MOTILALOFS.NS",
    "IRCTC.NS", "VOLTAS.NS", "COFORGE.NS", "KALYANKJIL.NS", "BALKRISIND.NS",
    "JKCEMENT.NS", "M&MFIN.NS", "APARINDS.NS", "TATACOMM.NS", "UBL.NS",
    "THERMAX.NS", "GLAXO.NS", "KEIINDS.NS", "NLCINDIA.NS", "PETRONET.NS",
    "360ONE.NS", "PAGEIND.NS", "IPCALAB.NS", "AUTHUM.NS", "LTTS.NS",
    "FLUOROCHEM.NS", "RADICO.NS", "AJANTPHARM.NS", "COCHINSHIP.NS",
    "AIAENG.NS", "ASTERDM.NS", "DALBHARAT.NS", "HUDCO.NS", "3MINDIA.NS",
    "CONCOR.NS", "NARAYANA.NS", "IREDA.NS", "POONAWALLA.NS", "MRPL.NS",
    "DELHIVERY.NS", "ESCORTS.NS", "ENDURANCE.NS", "BLUESTARCO.NS",
    "JBCHEPHARM.NS", "SONACOMS.NS", "CENTRALBK.NS", "NAVINFLUOR.NS",
    "KAYNES.NS", "KPITTECH.NS", "TATAELXSI.NS", "KAJARIACER.NS",
    "MANAPPURAM.NS", "CANFINHOME.NS", "CDSL.NS", "CESC.NS", "CROMPTON.NS",
    "CUB.NS", "DEEPAKNTR.NS", "ELGIEQUIP.NS", "EMAMILTD.NS", "EXIDEIND.NS",
    "GNFC.NS", "GRANULES.NS", "GSPL.NS", "GUJGASLTD.NS", "IEX.NS",
    "INOXWIND.NS", "ISEC.NS", "LALPATHLAB.NS", "LICHSGFIN.NS",
    "METROPOLIS.NS", "MGL.NS", "NIACL.NS", "NUVAMA.NS", "PCBL.NS",
    "RAILTEL.NS", "RBLBANK.NS", "ROUTE.NS", "SAFARI.NS", "STARHEALTH.NS",
    "SUMICHEM.NS", "SYNGENE.NS", "TATACHEM.NS", "TIMKEN.NS", "UJJIVANSFB.NS",
    "UCOBANK.NS", "UTIAMC.NS", "ZEEL.NS",

    # ── Small Cap additions (Nifty Smallcap 250 overlap) ──────────────────────
    "AEGISCHEM.NS", "ANGELONE.NS", "ATUL.NS", "BANDHANBNK.NS", "BATAINDIA.NS",
    "BLUEDART.NS", "CAMPUS.NS", "CAPLIPOINT.NS", "CARBORUNIV.NS", "CEATLTD.NS",
    "CENTURYPLY.NS", "CHAMBLFERT.NS", "CLEAN.NS", "CMSINFO.NS", "DBCORP.NS",
    "DCMSHRIRAM.NS", "DEEPAKFERT.NS", "DELTACORP.NS", "DHANUKA.NS", "DMART.NS",
    "EASEMYTRIP.NS", "EIDPARRY.NS", "ELECTCAST.NS", "EMCURE.NS", "EPL.NS",
    "FINEORG.NS", "GESHIP.NS", "GLAND.NS", "GPIL.NS", "GREAVESCOT.NS",
    "GREENPANEL.NS", "GRINDWELL.NS", "HAPPSTMNDS.NS", "HEG.NS", "HFCL.NS",
    "HOMEFIRST.NS", "HONASA.NS", "IFCI.NS", "IGPL.NS", "INDIGOPNTS.NS",
    "INTELLECT.NS", "ION.NS", "ISGEC.NS", "JWL.NS", "JYOTICNC.NS",
    "KARURVYSYA.NS", "KENNAMET.NS", "KNRCON.NS", "LATENTVIEW.NS", "LXCHEM.NS",
    "MAHSEAMLES.NS", "MASTECH.NS", "MEDPLUS.NS", "MIDHANI.NS", "MOLDTKPAC.NS",
    "MTAR.NS", "MULTIBASE.NS", "NAUKRI.NS", "NETWORK18.NS", "NUVOCO.NS",
    "OLECTRA.NS", "ORIENTCEM.NS", "PAISALO.NS", "PCJEWELLER.NS", "PFIZER.NS",
    "PHOENIXLTD.NS", "POLYMED.NS", "POWERMECH.NS", "PRINCEPIPE.NS",
    "PRIVISCL.NS", "PROCTER.NS", "RAINBOW.NS", "RAJRATAN.NS", "RATNAMANI.NS",
    "RAYMOND.NS", "REDINGTON.NS", "RELAXO.NS", "RHIM.NS", "RITES.NS",
    "ROSSARI.NS", "RPOWER.NS", "SAFARI.NS", "SANGHIIND.NS", "SAPPHIRE.NS",
    "SEQUENT.NS", "SGBPHARMA.NS", "SHYAMMETL.NS", "SJVN.NS", "SKFINDIA.NS",
    "SOBHA.NS", "SPARC.NS", "SSWL.NS", "SUBURBANGAS.NS", "SWSOLAR.NS",
    "SYMPHONY.NS", "TANLA.NS", "TARSONS.NS", "TEAMLEASE.NS", "TECHNOE.NS",
    "TITAGARH.NS", "TRITURBINE.NS", "TVSSCS.NS", "UJJIVAN.NS", "UNOMINDA.NS",
    "V2RETAIL.NS", "VAIBHAVGBL.NS", "VEDANTFASH.NS", "VINATIORGA.NS",
    "VIPIND.NS", "VMART.NS", "VTL.NS", "WESTLIFE.NS", "WHIRLPOOL.NS",
    "ZENSARTECH.NS", "ZENTEC.NS",
]

# Deduplicate
NIFTY500_TICKERS = list(dict.fromkeys(NIFTY500_TICKERS))


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def safe_float(value, default=None):
    try:
        v = float(value)
        return default if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return default


def get_sector_type(ticker):
    sym = ticker.replace(".NS", "")
    if sym in BANK_NBFC_TICKERS:  return "bank"
    if sym in PSU_TICKERS:        return "psu"
    if sym in CAPEX_HEAVY_TICKERS: return "capex"
    return "standard"


# ── Quality pre-filter ────────────────────────────────────────────────────────

def passes_quality_filter(ticker, info):
    """
    Returns (passed: bool, reason: str).
    If data unavailable for a metric → pass through (benefit of the doubt).
    """
    sector_type = get_sector_type(ticker)

    # 1. Revenue growth must be positive
    rev_growth = safe_float(info.get("revenueGrowth"))
    if rev_growth is not None and rev_growth <= 0:
        return False, f"revenue shrinking ({rev_growth*100:.1f}%)"

    # 2. Operating cash flow must be positive (skip capex-heavy)
    if sector_type not in ("capex",):
        ocf = safe_float(info.get("operatingCashflow"))
        if ocf is not None and ocf <= 0:
            return False, "negative operating cash flow"

    # 3. Net profit margin > 8% (skip banks — report differently)
    if sector_type == "standard":
        margin = safe_float(info.get("profitMargins"))
        if margin is not None and margin < 0.08:
            return False, f"thin margin ({margin*100:.1f}% < 8%)"

    # 4. ROE by sector
    roe = safe_float(info.get("returnOnEquity"))
    if roe is not None:
        if sector_type == "bank" and roe < 0.08:
            return False, f"low ROE for bank ({roe*100:.1f}% < 8%)"
        elif sector_type == "psu" and roe < 0.06:
            return False, f"low ROE for PSU ({roe*100:.1f}% < 6%)"
        elif sector_type in ("standard", "capex") and roe < 0.12:
            return False, f"low ROE ({roe*100:.1f}% < 12%)"

    return True, "ok"


# ── Main scanner ──────────────────────────────────────────────────────────────

def fetch_candidates(n=30):
    """
    Full pipeline for all Nifty 500 stocks:
      1. Fetch 3-month price history
      2. Dual lookback filter (1M and 3M both negative, 3M not worse than -40%)
      3. Drawdown filter (20–65% below 52W high)
      4. Quality pre-filter (revenue, OCF, margin, ROE — sector-aware)
      5. Volume spike detection
      6. Rank by 1M decline, return top n
    """
    total   = len(NIFTY500_TICKERS)
    print(f"Scanning {total} Nifty 500 stocks...\n")

    q_passed = q_failed = d_failed = l_failed = 0
    candidates = []

    for i, ticker in enumerate(NIFTY500_TICKERS, 1):
        sym = ticker.replace(".NS", "")
        try:
            # ── Price history (3 months) ───────────────────────────────────────
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

            # 1-month change (~21 trading days)
            idx_1m       = max(0, len(close) - 21)
            price_1m_ago = float(close.iloc[idx_1m])
            if math.isnan(price_1m_ago) or price_1m_ago == 0:
                continue
            change_1m = ((current_price - price_1m_ago) / price_1m_ago) * 100

            # 3-month change
            price_3m_ago = float(close.iloc[0])
            if math.isnan(price_3m_ago) or price_3m_ago == 0:
                continue
            change_3m = ((current_price - price_3m_ago) / price_3m_ago) * 100

            # ── FILTER: Dual lookback ──────────────────────────────────────────
            if change_1m >= 0 or change_3m >= 0 or change_3m < -40:
                l_failed += 1
                continue

            # ── Fundamentals (needed for quality filter + drawdown) ────────────
            info     = yf.Ticker(ticker).info
            high_52w = safe_float(info.get("fiftyTwoWeekHigh"))

            # ── FILTER: Drawdown 20–65% from 52W high ─────────────────────────
            if high_52w and high_52w > 0:
                drawdown = ((current_price - high_52w) / high_52w) * 100
                if drawdown > -20 or drawdown < -65:
                    d_failed += 1
                    continue
            else:
                drawdown = None

            # ── FILTER: Quality pre-filter ────────────────────────────────────
            passed, reason = passes_quality_filter(ticker, info)
            if not passed:
                q_failed += 1
                print(f"  ✗ {sym:20s}  {reason}")
                continue
            q_passed += 1

            # ── Volume spike ───────────────────────────────────────────────────
            avg_vol_3m    = float(volume.mean())
            avg_vol_5d    = float(volume.iloc[-5:].mean())
            volume_ratio  = round(avg_vol_5d / avg_vol_3m, 2) if avg_vol_3m > 0 else None
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

            # Progress heartbeat every 50 stocks
            if i % 50 == 0:
                print(f"  ... {i}/{total} scanned, {len(candidates)} candidates so far")

        except Exception as e:
            print(f"  Skipping {sym}: {e}")

    print(f"\n  ── Filter summary ───────────────────────────────")
    print(f"     Dual lookback eliminated:  {l_failed}")
    print(f"     Drawdown filter eliminated:{d_failed}")
    print(f"     Quality filter: {q_passed} passed, {q_failed} failed")
    print(f"     Final candidates:          {len(candidates)}")

    if not candidates:
        return []

    candidates.sort(key=lambda x: x["change_1m"])
    top = candidates[:n]
    print(f"\n  Top {n}: {[s['ticker'] for s in top]}\n")
    return top


# ── Fundamentals fetcher ──────────────────────────────────────────────────────

def fetch_fundamentals(ticker_sym):
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

The investor uses a FALLING KNIFE strategy — buying fundamentally strong Nifty 500 stocks (large, mid and small cap) that have dropped sharply due to TEMPORARY or MACRO reasons, NOT structural business deterioration.

These stocks have already passed quality pre-filters (positive revenue growth, positive OCF, minimum ROE, appropriate margins) and are 20–65% below their 52-week highs. Your job is to add intelligence — search for the actual reason behind each fall and score them rigorously.

STOCKS DATA (includes 1M change, 3M change, drawdown from 52W high, panic_selling flag):
{stocks_json}

SCORING RULES — be strict, do not inflate:
  +2 if P/E is meaningfully below 5-year historical average (not marginally)
  +2 if ROE is above 15%
  +2 if balance sheet is appropriate for sector (D/E < 0.5 non-financials; NPA quality for banks)
  +2 if SPECIFIC CONCRETE DATED catalyst within 60 days (earnings date, RBI decision, order win — NOT "may recover" or "sentiment may improve")
  +2 if fall is clearly macro/sentiment driven (FII selling, crude, rates, geopolitics) NOT structural (losing share, fraud, regulatory ban)

HARD RULES:
- If promoter pledging > 20%: cap score at 4, set catalyst_ok = false. Search BSE shareholding for this.
- catalyst_ok = true ONLY if you found a specific event with a named date or announcement. Vague forward-looking statements do NOT count.
- If panic_selling = true (volume spike), this is a positive signal — note it in why_fell.
- Check sector concentration: if more than 4 stocks from the same sector appear, note in market_context.
- For small-cap stocks (market_cap_cr < 5000): apply extra scrutiny on debt and management quality.

Scoring scale: 8-10 = Strong Buy. 6-7 = Buy on confirmation. 4-5 = Watch. <4 = Avoid.

Respond ONLY with a valid JSON object — no markdown, no preamble, no trailing text.

{{
  "date": "{today}",
  "market_context": "3 sentences: macro backdrop driving the selling, what sectors are most affected, and what falling knife investors should watch this week",
  "stocks": [
    {{
      "ticker": "...",
      "name": "...",
      "why_fell": "2 specific sentences citing actual recent news — no vague macro statements unless that IS the reason",
      "catalyst": "Specific event + date if known. Write NONE if no concrete catalyst found.",
      "promoter_pledge_pct": "X% — search BSE/NSE shareholding data, or write Unknown",
      "value_trap_risk": "low/medium/high — one sentence with specific reason",
      "score": 7,
      "action": "Buy (Tranche 1)",
      "thesis_break": "One specific measurable condition, e.g. 'Q4 revenue growth turns negative' not 'if fundamentals deteriorate'",
      "score_breakdown": {{
        "pe_ok": true,
        "roe_ok": true,
        "debt_ok": true,
        "catalyst_ok": false,
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
        stock.update({
            "price":            fund.get("price", "N/A"),
            "change_1m":        fund.get("change_1m", "N/A"),
            "change_3m":        fund.get("change_3m", "N/A"),
            "drawdown_52w":     fund.get("drawdown_52w", "N/A"),
            "volume_ratio":     fund.get("volume_ratio", "N/A"),
            "panic_selling":    fund.get("panic_selling", False),
            "name":             fund.get("name", stock.get("ticker", "")),
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
    analysis["index"]        = "Nifty 500"
    analysis["version"]      = "3.0"

    clean = clean_nan(analysis)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(clean, f, indent=2)
    print(f"  Saved → {OUTPUT_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  Nifty 500 Screener v3  —  {datetime.date.today()}")
    print(f"{'='*55}\n")

    candidates = fetch_candidates(n=30)

    if not candidates:
        print("No candidates passed filters — market may be closed or filters too strict.")
        raise SystemExit(1)

    print("Fetching fundamentals for candidates...")
    for stock in candidates:
        print(f"  {stock['ticker']}")
        stock.update(fetch_fundamentals(stock["ticker"]))

    analysis = analyse_with_gemini(candidates)
    print(f"\n  Scored {len(analysis.get('stocks', []))} stocks.\n")

    save_results(analysis, candidates)
    print("\nDone! ✓\n")


if __name__ == "__main__":
    main()
