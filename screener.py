"""
Nifty 200 Falling Knife Stock Screener
Powered by Google Gemini API (free — no credit card needed)

Covers all 200 stocks in the Nifty 200 index (Nifty 100 + Nifty Midcap 100)
Picks the 7 biggest losers of the past month for falling knife analysis.
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

# ── Full Nifty 200 constituent list (Yahoo Finance .NS tickers) ───────────────
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
    "HAVELLS.NS", "HEROMOTOCO.NS", "HINDPETRO.NS", "ICICIGI.NS",
    "ICICIPRULI.NS", "INDIANB.NS", "INDIGO.NS", "IOC.NS", "IRCTC.NS",
    "JINDALSTEL.NS", "JUBLFOOD.NS", "LICI.NS", "LODHA.NS", "LUPIN.NS",
    "MARICO.NS", "MOTHERSON.NS", "MUTHOOTFIN.NS", "NAUKRI.NS", "NHPC.NS",
    "NMDC.NS", "OFSS.NS", "PAGEIND.NS", "PAYTM.NS", "PFC.NS", "PIDILITIND.NS",
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
    "EXIDEIND.NS", "FEDERALBNK.NS", "FLUOROCHEM.NS", "FRETAIL.NS",
    "GLENMARK.NS", "GLAXO.NS", "GNFC.NS", "GODREJPROP.NS",
    "GRANULES.NS", "GSPL.NS", "GUJGASLTD.NS", "HDFCAMC.NS",
    "HONASA.NS", "IDFCFIRSTB.NS", "IEX.NS", "INDHOTEL.NS",
    "INDUSTOWER.NS", "INOXWIND.NS", "IREDA.NS", "ISEC.NS",
    "JKCEMENT.NS", "KAJARIACER.NS", "KPITTECH.NS", "LALPATHLAB.NS",
    "LAURUSLABS.NS", "LICHSGFIN.NS", "LTIM.NS", "LTTS.NS",
    "MANAPPURAM.NS", "MAXHEALTH.NS", "MCX.NS", "METROPOLIS.NS",
    "MFSL.NS", "MGL.NS", "MPHASIS.NS", "MRF.NS", "NATIONALUM.NS",
    "NIACL.NS", "NLCINDIA.NS", "NUVAMA.NS", "OBEROIRLTY.NS",
    "OIL.NS", "ORIENTELEC.NS", "PCBL.NS", "PERSISTENT.NS",
    "PETRONET.NS", "PHOENIXLTD.NS", "POLYCAB.NS", "POONAWALLA.NS",
    "PRESTIGE.NS", "PRINCEPIPE.NS", "RADICO.NS", "RAILTEL.NS",
    "RAINBOW.NS", "RBLBANK.NS", "ROUTE.NS", "SAFARI.NS",
    "SBICARD.NS", "SCHAEFFLER.NS", "SOLARINDS.NS", "SONACOMS.NS",
    "STARHEALTH.NS", "SUMICHEM.NS", "SUNDARMFIN.NS", "SUPREMEIND.NS",
    "SYNGENE.NS", "TATACHEM.NS", "TATACOMM.NS", "THERMAX.NS",
    "TIMKEN.NS", "TRENT.NS", "TRITURBINE.NS", "UCOBANK.NS",
    "UJJIVANSFB.NS", "UNIONBANK.NS", "UPL.NS", "UTIAMC.NS",
    "VARUNBEV.NS", "VBL.NS", "VOLTAS.NS", "WHIRLPOOL.NS",
    "WIPRO.NS", "ZEEL.NS", "ZYDUSLIFE.NS",
]

# Deduplicate (some tickers appear in both Nifty 50 and midcap sections)
NIFTY200_TICKERS = list(dict.fromkeys(NIFTY200_TICKERS))


def clean_nan(obj):
    """Recursively replace NaN/Inf floats with None so JSON stays valid."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def fetch_top_losers(n=7):
    print(f"Fetching market data for {len(NIFTY200_TICKERS)} Nifty 200 stocks...")
    results = []
    for ticker in NIFTY200_TICKERS:
        try:
            hist = yf.download(ticker, period="1mo", interval="1d",
                               progress=False, auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue

            close = hist["Close"]

            # Squeeze to 1D Series if needed (handles newer yfinance multi-index)
            if hasattr(close, "squeeze"):
                close = close.squeeze()

            # Skip if still 2D
            if hasattr(close, "columns"):
                continue

            start_price = float(close.iloc[0])
            end_price   = float(close.iloc[-1])

            if math.isnan(start_price) or math.isnan(end_price):
                continue

            change_pct = ((end_price - start_price) / start_price) * 100
            results.append({
                "ticker":    ticker.replace(".NS", ""),
                "price":     round(end_price, 2),
                "change_1m": round(change_pct, 2),
            })
        except Exception as e:
            print(f"  Skipping {ticker}: {e}")

    results.sort(key=lambda x: x["change_1m"])
    losers = results[:n]
    print(f"  Scanned {len(results)} stocks. Top {n} losers: {[s['ticker'] for s in losers]}")
    return losers


def fetch_fundamentals(ticker_ns):
    try:
        info = yf.Ticker(ticker_ns + ".NS").info

        def pct(key):
            v = info.get(key)
            try:
                return round(float(v) * 100, 1) if v is not None and not math.isnan(float(v)) else "N/A"
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
            "name":             info.get("longName", ticker_ns),
            "sector":           info.get("sector", "N/A"),
            "pe_ratio":         safe("trailingPE"),
            "forward_pe":       safe("forwardPE"),
            "pb_ratio":         safe("priceToBook"),
            "roe":              pct("returnOnEquity"),
            "debt_to_equity":   safe("debtToEquity"),
            "operating_margin": pct("operatingMargins"),
            "revenue_growth":   pct("revenueGrowth"),
            "market_cap_cr":    round(info.get("marketCap", 0) / 1e7, 0) if info.get("marketCap") else "N/A",
            "52w_high":         safe("fiftyTwoWeekHigh"),
            "52w_low":          safe("fiftyTwoWeekLow"),
        }
    except Exception as e:
        print(f"  Could not fetch fundamentals for {ticker_ns}: {e}")
        return {}


def analyse_with_gemini(stocks):
    print("Sending to Gemini for analysis...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    today       = datetime.date.today().strftime("%B %d, %Y")
    stocks_json = json.dumps(stocks, indent=2)

    prompt = f"""Today is {today}. You are a stock research analyst for the Indian equity market.

The investor uses a falling knife strategy — buying fundamentally strong Nifty 200 stocks that have dropped sharply due to temporary/macro reasons, not structural ones. Nifty 200 includes both large-cap (Nifty 100) and mid-cap (Nifty Midcap 100) stocks.

Search for the latest news on each stock to explain why it fell and identify a real upcoming catalyst.

STOCKS DATA:
{stocks_json}

Score each stock 1-10:
  +2 if P/E is below its 5-year historical average
  +2 if ROE is above 15%
  +2 if D/E is below 0.5 (or sector-appropriate for banks/PSUs)
  +2 if a clear specific recovery catalyst exists
  +2 if the fall is macro/sentiment driven not structural

Score 7-10 = Buy (Tranche 1). Score 5-6 = Watch. Below 5 = Avoid.

You MUST respond with ONLY a valid JSON object. No explanation, no markdown, no text before or after the JSON. Start your response with {{ and end with }}.

{{
  "date": "{today}",
  "market_context": "2 sentences on Nifty 200 conditions for a falling knife investor today",
  "stocks": [
    {{
      "ticker": "...",
      "why_fell": "2 sentences using recent news",
      "catalyst": "specific event or date",
      "value_trap_risk": "low/medium/high — one sentence",
      "score": 7,
      "action": "Buy (Tranche 1)",
      "thesis_break": "one condition that invalidates this thesis",
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
            raise ValueError("Empty response from Gemini with search grounding")
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


def save_results(analysis, stocks):
    fund_map = {s["ticker"]: s for s in stocks}
    for stock in analysis["stocks"]:
        fund = fund_map.get(stock["ticker"], {})
        stock.update({
            "price":            fund.get("price", "N/A"),
            "change_1m":        fund.get("change_1m", "N/A"),
            "name":             fund.get("name", stock["ticker"]),
            "sector":           fund.get("sector", "N/A"),
            "pe_ratio":         fund.get("pe_ratio", "N/A"),
            "forward_pe":       fund.get("forward_pe", "N/A"),
            "roe":              fund.get("roe", "N/A"),
            "debt_to_equity":   fund.get("debt_to_equity", "N/A"),
            "operating_margin": fund.get("operating_margin", "N/A"),
            "market_cap_cr":    fund.get("market_cap_cr", "N/A"),
            "revenue_growth":   fund.get("revenue_growth", "N/A"),
            "52w_high":         fund.get("52w_high", "N/A"),
            "52w_low":          fund.get("52w_low", "N/A"),
        })

    analysis["generated_at"] = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    analysis["index"] = "Nifty 200"

    clean = clean_nan(analysis)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(clean, f, indent=2)
    print(f"  Saved → {OUTPUT_FILE}")


def main():
    print(f"\n{'='*55}")
    print(f"  Nifty 200 Screener  —  {datetime.date.today()}")
    print(f"{'='*55}\n")

    losers = fetch_top_losers(n=7)
    if not losers:
        print("ERROR: No losers found — market may be closed today. Exiting.")
        raise SystemExit(1)

    print("\nFetching fundamentals...")
    for stock in losers:
        print(f"  {stock['ticker']}")
        stock.update(fetch_fundamentals(stock["ticker"]))

    analysis = analyse_with_gemini(losers)
    print(f"\nAnalysis done. {len(analysis['stocks'])} stocks scored.\n")

    save_results(analysis, losers)
    print("\nDone! ✓\n")


if __name__ == "__main__":
    main()
