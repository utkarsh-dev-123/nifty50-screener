"""
Nifty 50 Falling Knife Stock Screener
Powered by Google Gemini API (free — no credit card needed)
"""

import os
import json
import datetime
import yfinance as yf
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OUTPUT_FILE    = "data.json"

NIFTY50_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFY.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "KOTAKBANK.NS", "HCLTECH.NS", "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "BAJFINANCE.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS", "WIPRO.NS",
    "NTPC.NS", "ONGC.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "M&M.NS",
    "TATASTEEL.NS", "POWERGRID.NS", "COALINDIA.NS", "BAJAJFINSV.NS",
    "NESTLEIND.NS", "GRASIM.NS", "CIPLA.NS", "DRREDDY.NS", "TECHM.NS",
    "HINDALCO.NS", "TRENT.NS", "INDUSINDBK.NS", "EICHERMOT.NS", "BRITANNIA.NS",
    "APOLLOHOSP.NS", "HEROMOTOCO.NS", "BPCL.NS", "SHRIRAMFIN.NS", "BEL.NS",
    "BAJAJ-AUTO.NS", "DIVISLAB.NS", "SBILIFE.NS", "HDFCLIFE.NS", "JIOFIN.NS",
    "TATAMTRDVR.NS"
]


def fetch_top_losers(n=7):
    print("Fetching market data...")
    results = []
    for ticker in NIFTY50_TICKERS:
        try:
            hist = yf.download(ticker, period="1mo", interval="1d",
                               progress=False, auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue
            close = hist["Close"]
            if hasattr(close, "squeeze"):
                close = close.squeeze()
            start_price = float(close.iloc[0])
            end_price   = float(close.iloc[-1])
            change_pct  = ((end_price - start_price) / start_price) * 100
            results.append({
                "ticker":    ticker.replace(".NS", ""),
                "price":     round(end_price, 2),
                "change_1m": round(change_pct, 2),
            })
        except Exception as e:
            print(f"  Skipping {ticker}: {e}")

    results.sort(key=lambda x: x["change_1m"])
    losers = results[:n]
    print(f"  Found {len(losers)} losers: {[s['ticker'] for s in losers]}")
    return losers


def fetch_fundamentals(ticker_ns):
    try:
        info = yf.Ticker(ticker_ns + ".NS").info
        def pct(key):
            v = info.get(key)
            return round(v * 100, 1) if v else "N/A"
        return {
            "name":             info.get("longName", ticker_ns),
            "sector":           info.get("sector", "N/A"),
            "pe_ratio":         info.get("trailingPE", "N/A"),
            "forward_pe":       info.get("forwardPE", "N/A"),
            "pb_ratio":         info.get("priceToBook", "N/A"),
            "roe":              pct("returnOnEquity"),
            "debt_to_equity":   info.get("debtToEquity", "N/A"),
            "operating_margin": pct("operatingMargins"),
            "revenue_growth":   pct("revenueGrowth"),
            "market_cap_cr":    round(info.get("marketCap", 0) / 1e7, 0) if info.get("marketCap") else "N/A",
            "52w_high":         info.get("fiftyTwoWeekHigh", "N/A"),
            "52w_low":          info.get("fiftyTwoWeekLow", "N/A"),
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

The investor uses a falling knife strategy — buying fundamentally strong Nifty 50 stocks that have dropped sharply due to temporary/macro reasons, not structural ones.

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
  "market_context": "2 sentences on Nifty 50 conditions for a falling knife investor today",
  "stocks": [
    {{
      "ticker": "...",
      "why_fell": "2 sentences",
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

    # Try with Google Search grounding first, fall back without if it fails
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        # Extract text from response — handle both direct .text and candidates
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

    # Strip markdown fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break

    # Find JSON boundaries
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
    with open(OUTPUT_FILE, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"  Saved → {OUTPUT_FILE}")


def main():
    print(f"\n{'='*55}")
    print(f"  Nifty 50 Screener  —  {datetime.date.today()}")
    print(f"{'='*55}\n")

    losers = fetch_top_losers(n=7)
    if not losers:
        print("ERROR: No losers found. Exiting.")
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
