"""
Nifty 50 Falling Knife Stock Screener
Powered by Google Gemini API (free tier — no credit card needed)
Runs daily, writes to Google Sheets, sends Email + WhatsApp

Get your free Gemini API key at: https://ai.google.dev
No credit card required. Free tier = 250 requests/day. You need 1.
"""

import os
import json
import datetime
import google.generativeai as genai
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from twilio.rest import Client

# ── CONFIG (edit these) ──────────────────────────────────────────────────────
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]  # free at ai.google.dev
GOOGLE_CREDS_FILE   = "google_creds.json"           # path to your Google service account JSON
SPREADSHEET_NAME    = "Nifty50 Stock Screener"      # must exist in your Google Drive

EMAIL_SENDER        = os.environ["EMAIL_SENDER"]   # your Gmail address
EMAIL_PASSWORD      = os.environ["EMAIL_PASSWORD"] # Gmail app password (not your login password)
EMAIL_RECIPIENT     = os.environ["EMAIL_RECIPIENT"]

TWILIO_SID          = os.environ["TWILIO_SID"]
TWILIO_AUTH_TOKEN   = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM         = "whatsapp:+14155238886"      # Twilio sandbox number
TWILIO_TO           = os.environ["TWILIO_TO"]      # your number e.g. whatsapp:+919876543210
# ─────────────────────────────────────────────────────────────────────────────

NIFTY50_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFOSYS.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "KOTAKBANK.NS", "HCLTECH.NS", "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "BAJFINANCE.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS", "WIPRO.NS",
    "NTPC.NS", "ONGC.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "TATAMOTORS.NS",
    "TATASTEEL.NS", "M&M.NS", "POWERGRID.NS", "COALINDIA.NS", "BAJAJFINSV.NS",
    "NESTLEIND.NS", "GRASIM.NS", "CIPLA.NS", "DRREDDY.NS", "TECHM.NS",
    "HINDALCO.NS", "TRENT.NS", "INDUSINDBK.NS", "EICHERMOT.NS", "BRITANNIA.NS",
    "APOLLOHOSP.NS", "HEROMOTOCO.NS", "BPCL.NS", "SHRIRAMFIN.NS", "BEL.NS",
    "BAJAJ-AUTO.NS", "DIVISLAB.NS", "SBILIFE.NS", "HDFCLIFE.NS", "JIOFIN.NS"
]


def fetch_top_losers(n=7):
    """Fetch Nifty 50 stocks sorted by 1-month % change, return worst n."""
    print("Fetching market data...")
    results = []
    for ticker in NIFTY50_TICKERS:
        try:
            info = yf.Ticker(ticker).fast_info
            hist = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue
            start_price = float(hist["Close"].iloc[0])
            end_price   = float(hist["Close"].iloc[-1])
            change_pct  = ((end_price - start_price) / start_price) * 100

            results.append({
                "ticker":      ticker.replace(".NS", ""),
                "name":        ticker.replace(".NS", ""),
                "price":       round(end_price, 2),
                "change_1m":   round(change_pct, 2),
            })
        except Exception as e:
            print(f"  Skipping {ticker}: {e}")
            continue

    results.sort(key=lambda x: x["change_1m"])
    return results[:n]


def fetch_fundamentals(ticker_ns):
    """Pull key fundamentals from yfinance for a single ticker."""
    try:
        t = yf.Ticker(ticker_ns + ".NS")
        i = t.info
        return {
            "pe_ratio":           i.get("trailingPE",          "N/A"),
            "forward_pe":         i.get("forwardPE",           "N/A"),
            "pb_ratio":           i.get("priceToBook",         "N/A"),
            "roe":                round(i.get("returnOnEquity", 0) * 100, 1) if i.get("returnOnEquity") else "N/A",
            "debt_to_equity":     i.get("debtToEquity",        "N/A"),
            "operating_margin":   round(i.get("operatingMargins", 0) * 100, 1) if i.get("operatingMargins") else "N/A",
            "revenue_growth":     round(i.get("revenueGrowth", 0) * 100, 1) if i.get("revenueGrowth") else "N/A",
            "free_cashflow":      i.get("freeCashflow",        "N/A"),
            "market_cap_cr":      round(i.get("marketCap", 0) / 1e7, 0) if i.get("marketCap") else "N/A",
            "52w_high":           i.get("fiftyTwoWeekHigh",    "N/A"),
            "52w_low":            i.get("fiftyTwoWeekLow",     "N/A"),
            "sector":             i.get("sector",              "N/A"),
            "industry":           i.get("industry",            "N/A"),
        }
    except Exception as e:
        print(f"  Could not fetch fundamentals for {ticker_ns}: {e}")
        return {}


def analyse_with_gemini(losers_with_fundamentals):
    """Send stock data to Gemini for falling knife analysis and scoring.

    Uses Gemini 2.5 Flash with Google Search grounding enabled — so Gemini
    automatically searches the web to explain WHY each stock fell, which is
    the hardest part to do without a live AI. Free tier: 250 requests/day.
    """
    print("Sending to Gemini for analysis...")
    genai.configure(api_key=GEMINI_API_KEY)

    today = datetime.date.today().strftime("%B %d, %Y")
    stocks_json = json.dumps(losers_with_fundamentals, indent=2)

    prompt = f"""Today is {today}. You are a stock research analyst specialising in the Indian equity market and the Nifty 50 index.

Below are the top Nifty 50 losers over the past month, along with their fundamental metrics. The investor uses a "falling knife" strategy — buying fundamentally strong stocks that have fallen sharply due to temporary or macro reasons, not structural problems.

Use Google Search to find the latest news on each stock so you can accurately explain why it fell and identify a real upcoming catalyst.

STOCKS DATA:
{stocks_json}

For each stock, provide:

1. WHY IT FELL — A concise 2-sentence explanation of the most likely reason for the decline (macro, sector-wide, company-specific, or sentiment-driven). Use recent news.

2. CATALYST FOR RECOVERY — One specific, concrete catalyst that could reverse the decline (e.g. upcoming earnings date, policy tailwind, debt repayment, cycle bottom). Be specific — name the event and date if possible.

3. VALUE TRAP RISK — Is the fall structural (avoid) or temporary (opportunity)? One sentence.

4. FALLING KNIFE SCORE (1–10) — Score based on:
   - P/E below 5-year historical average? (+2)
   - ROE above 15%? (+2)
   - D/E below 0.5 (or sector-appropriate)? (+2)
   - Clear recovery catalyst exists? (+2)
   - Fall is macro/sentiment-driven, not structural? (+2)
   Score 7+ = Strong buy candidate. 5–6 = Watch. Below 5 = Avoid.

5. SUGGESTED ACTION — One of: "Buy (Tranche 1)", "Watch for Q results", or "Avoid".

6. THESIS BREAK SIGNAL — One specific condition that would invalidate the investment thesis.

Respond in valid JSON only. No markdown, no preamble, no explanation outside the JSON. Format:
{{
  "date": "{today}",
  "stocks": [
    {{
      "ticker": "...",
      "why_fell": "...",
      "catalyst": "...",
      "value_trap_risk": "...",
      "score": <number>,
      "action": "...",
      "thesis_break": "..."
    }}
  ],
  "market_context": "A 2-sentence summary of the overall Nifty 50 market context today and what it means for falling knife investors."
}}"""

    # Enable Google Search grounding so Gemini can look up recent news
    # This is what lets it explain WHY stocks fell — the key value-add
    search_tool = genai.protos.Tool(
        google_search=genai.protos.GoogleSearch()
    )

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        tools=[search_tool],
    )

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown fences if Gemini wraps in ```json ... ```
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def write_to_sheets(analysis, losers_with_fundamentals):
    """Append today's results to Google Sheets."""
    print("Writing to Google Sheets...")
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
    gc    = gspread.authorize(creds)
    sh    = gc.open(SPREADSHEET_NAME)

    # ── Sheet 1: Daily Log ───────────────────────────────────────────────────
    try:
        log_sheet = sh.worksheet("Daily Log")
    except gspread.WorksheetNotFound:
        log_sheet = sh.add_worksheet("Daily Log", rows=1000, cols=20)
        log_sheet.append_row([
            "Date", "Ticker", "Price (₹)", "1M Change %",
            "P/E", "ROE %", "D/E", "Op Margin %",
            "Score", "Action", "Why Fell", "Catalyst", "Thesis Break"
        ])

    today = analysis["date"]
    fund_map = {s["ticker"]: s for s in losers_with_fundamentals}

    for stock in analysis["stocks"]:
        t = stock["ticker"]
        f = fund_map.get(t, {})
        log_sheet.append_row([
            today,
            t,
            f.get("price", ""),
            f.get("change_1m", ""),
            f.get("pe_ratio", ""),
            f.get("roe", ""),
            f.get("debt_to_equity", ""),
            f.get("operating_margin", ""),
            stock["score"],
            stock["action"],
            stock["why_fell"],
            stock["catalyst"],
            stock["thesis_break"],
        ])

    # ── Sheet 2: Watchlist (score >= 7) ──────────────────────────────────────
    try:
        watch_sheet = sh.worksheet("Watchlist")
    except gspread.WorksheetNotFound:
        watch_sheet = sh.add_worksheet("Watchlist", rows=500, cols=10)
        watch_sheet.append_row(["Date Added", "Ticker", "Price", "Score", "Action", "Catalyst", "Thesis Break"])

    for stock in analysis["stocks"]:
        if stock["score"] >= 7:
            t = stock["ticker"]
            f = fund_map.get(t, {})
            watch_sheet.append_row([
                today, t, f.get("price", ""),
                stock["score"], stock["action"],
                stock["catalyst"], stock["thesis_break"]
            ])

    print(f"  Written {len(analysis['stocks'])} rows to Google Sheets.")


def format_digest(analysis, losers_with_fundamentals):
    """Format a clean plain-text digest for email and WhatsApp."""
    fund_map = {s["ticker"]: s for s in losers_with_fundamentals}
    lines = [
        f"📊 NIFTY 50 FALLING KNIFE SCREENER — {analysis['date']}",
        "=" * 50,
        "",
        f"📌 Market Context: {analysis['market_context']}",
        "",
    ]

    for s in analysis["stocks"]:
        f = fund_map.get(s["ticker"], {})
        score = s["score"]
        emoji = "🟢" if score >= 7 else ("🟡" if score >= 5 else "🔴")
        lines += [
            f"{emoji} {s['ticker']}  |  ₹{f.get('price','?')}  |  {f.get('change_1m','?')}% (1M)  |  Score: {score}/10",
            f"   Why fell:  {s['why_fell']}",
            f"   Catalyst:  {s['catalyst']}",
            f"   Action:    {s['action']}",
            f"   Exit if:   {s['thesis_break']}",
            "",
        ]

    lines += [
        "─" * 50,
        "🟢 = Buy candidate (7+)  🟡 = Watch (5-6)  🔴 = Avoid (<5)",
        "Full data → Google Sheets: Nifty50 Stock Screener",
        "⚠️  Not investment advice. Verify before acting.",
    ]
    return "\n".join(lines)


def send_email(digest_text):
    """Send digest via Gmail."""
    print("Sending email...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Nifty 50 Screener — {datetime.date.today().strftime('%d %b %Y')}"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT

    # Plain text part
    msg.attach(MIMEText(digest_text, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
    print("  Email sent.")


def send_whatsapp(digest_text):
    """Send digest via Twilio WhatsApp."""
    print("Sending WhatsApp...")
    # WhatsApp messages have a 1600-char limit; send in chunks if needed
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    chunks = [digest_text[i:i+1500] for i in range(0, len(digest_text), 1500)]
    for chunk in chunks:
        client.messages.create(
            from_=TWILIO_FROM,
            to=TWILIO_TO,
            body=chunk
        )
    print("  WhatsApp sent.")


def main():
    print(f"\n{'='*55}")
    print(f"  Nifty 50 Screener  —  {datetime.date.today()}")
    print(f"{'='*55}\n")

    # Step 1: Fetch top losers
    losers = fetch_top_losers(n=7)
    print(f"Top losers: {[s['ticker'] for s in losers]}\n")

    # Step 2: Enrich with fundamentals
    for stock in losers:
        print(f"  Fetching fundamentals: {stock['ticker']}")
        fund = fetch_fundamentals(stock["ticker"])
        stock.update(fund)

    # Step 3: Gemini analysis (free — uses Google Search grounding)
    analysis = analyse_with_gemini(losers)
    print(f"\nAnalysis complete. Stocks scored: {len(analysis['stocks'])}\n")

    # Step 4: Write to Google Sheets
    write_to_sheets(analysis, losers)

    # Step 5: Format and send alerts
    digest = format_digest(analysis, losers)
    print("\n" + digest + "\n")
    send_email(digest)
    send_whatsapp(digest)

    print("\nDone! ✓\n")


if __name__ == "__main__":
    main()
