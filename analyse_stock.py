"""
analyse_stock.py — deep single-stock analysis via three sequential Gemini prompts.

Loads cached fundamentals from data.json (if available), fetches fresh
announcements and the latest quarterly/annual PDFs from NSE, then runs:

  1. why_fell        — diagnoses the specific reason(s) for the price fall
  2. management_quality — assesses capital allocation, pledge risk, track record
  3. investment_case — final scored recommendation conditioned on prompts 1 & 2

Output is saved to analysis/<SYMBOL>.json.

Usage:
    python analyse_stock.py RELIANCE
    python analyse_stock.py TATASTEEL --model gemini-2.5-pro
"""

import os
import sys
import json
import argparse
import datetime
from pathlib import Path

import yfinance as yf
from nse import NSE
from google import genai
from google.genai import types

from helpers import (
    safe_float,
    clean_nan,
    fetch_fundamentals,
    _find_pledge,
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE      = Path("data.json")
PDF_DIR        = Path("pdfs")
ANALYSIS_DIR   = Path("analysis")
DEFAULT_MODEL  = "gemini-2.5-flash"


# ── NSE data fetch ────────────────────────────────────────────────────────────

def fetch_nse_data(symbol):
    """
    Fetch from NSE India for a single symbol:
      - All announcements from the last 90 days
      - Latest 2 annual/quarterly report PDFs (downloaded to PDF_DIR)
      - Board meeting history (quarterly results context)
      - Promoter pledge %

    Returns a dict; every field falls back gracefully on API failure.
    """
    result = {
        "announcements":       [],
        "board_meetings":      [],
        "promoter_pledge_pct": None,
        "pdf_paths":           [],
    }
    cutoff = datetime.date.today() - datetime.timedelta(days=90)

    def _parse_date(dt_str):
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(dt_str[:11].strip(), fmt).date()
            except Exception:
                continue
        return None

    PDF_DIR.mkdir(exist_ok=True)

    with NSE(download_folder=PDF_DIR, server=False) as nse:

        # 1. Announcements ─────────────────────────────────────────────────────
        try:
            raw   = nse.announcements(symbol=symbol)
            items = raw if isinstance(raw, list) else raw.get("data", [])
            for item in items:
                dt_str = (item.get("an_dt") or item.get("date") or
                          item.get("dt")    or item.get("exchdisstime") or "")
                dt = _parse_date(dt_str)
                if dt is None or dt >= cutoff:
                    result["announcements"].append({
                        "date":    dt_str[:10],
                        "subject": (item.get("subject") or item.get("desc") or
                                    item.get("headline") or ""),
                    })
        except Exception as e:
            print(f"  announcements({symbol}): {e}")

        # 2. Board meetings (quarterly results context) ────────────────────────
        try:
            bm    = nse.boardMeetings(symbol=symbol)
            items = bm if isinstance(bm, list) else bm.get("data", [])
            for item in items[:8]:   # last ~2 years of meetings
                result["board_meetings"].append({
                    "date":    item.get("bm_date", ""),
                    "purpose": item.get("bm_purpose") or item.get("purpose") or "",
                    "desc":    item.get("bm_desc")    or item.get("desc")    or "",
                })
        except Exception as e:
            print(f"  boardMeetings({symbol}): {e}")

        # 3. Promoter pledge % ─────────────────────────────────────────────────
        try:
            sh     = nse.shareholding(symbol=symbol)
            pledge = _find_pledge(sh)
            result["promoter_pledge_pct"] = pledge
        except Exception as e:
            print(f"  shareholding({symbol}): {e}")

        # 4. Annual/quarterly PDFs (latest 2) ──────────────────────────────────
        try:
            reports = nse.annual_reports(symbol=symbol)
            items   = reports if isinstance(reports, list) else reports.get("data", [])
            for item in items[:2]:
                pdf_url = (item.get("fileName") or item.get("pdfUrl") or
                           item.get("url")      or item.get("file")   or "")
                if not pdf_url:
                    continue
                try:
                    path = nse.download_document(pdf_url, folder=PDF_DIR)
                    result["pdf_paths"].append(str(path))
                    print(f"  PDF -> {path}")
                except Exception as e:
                    print(f"  download({symbol}): {e}")
        except Exception as e:
            print(f"  annual_reports({symbol}): {e}")

    return result


# ── Gemini helpers ────────────────────────────────────────────────────────────

def _upload_pdfs(client, pdf_paths):
    """
    Upload PDFs to the Gemini Files API.
    Returns a flat list of (label Part, file Part) pairs interleaved.
    Upload failures are skipped silently.
    """
    parts = []
    for path_str in pdf_paths:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            uploaded = client.files.upload(
                path=str(path),
                config={
                    "display_name": path.stem,
                    "mime_type":    "application/pdf",
                },
            )
            parts.append(types.Part.from_text(f"[PDF attached: {path.name}]"))
            parts.append(types.Part.from_uri(
                file_uri=uploaded.uri, mime_type="application/pdf"
            ))
            print(f"  Uploaded: {path.name}")
        except Exception as e:
            print(f"  PDF upload({path.name}): {e}")
    return parts


def _extract_text(response):
    if hasattr(response, "text") and response.text:
        return response.text.strip()
    raw = ""
    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            if hasattr(candidate, "content") and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        raw += part.text
    return raw.strip()


def _parse_json(raw):
    """Strip markdown fences and extract the first JSON object from a string."""
    if "```" in raw:
        for block in raw.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                raw = block
                break
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]
    return json.loads(raw)


def _gemini_json(client, contents, model):
    """
    Call Gemini and return a parsed JSON dict.
    Tries with Google Search grounding first; falls back to a plain call.
    """
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        raw = _extract_text(response)
        if not raw:
            raise ValueError("empty response")
        return _parse_json(raw)
    except Exception as e:
        print(f"  Search grounding failed ({e}), retrying without search...")
        response = client.models.generate_content(model=model, contents=contents)
        raw = _extract_text(response)
        return _parse_json(raw)


# ── Three sequential prompts ──────────────────────────────────────────────────

def prompt_why_fell(client, model, stock, nse_data, pdf_parts):
    """
    Prompt 1 — diagnose the specific reason(s) for the price fall.
    """
    today = datetime.date.today().strftime("%B %d, %Y")
    payload = {
        "ticker":        stock.get("ticker"),
        "sector":        stock.get("sector", "N/A"),
        "price":         stock.get("price"),
        "change_1m":     stock.get("change_1m"),
        "change_3m":     stock.get("change_3m"),
        "drawdown_52w":  stock.get("drawdown_52w"),
        "panic_selling": stock.get("panic_selling"),
        "announcements": nse_data["announcements"],
        "board_meetings": nse_data["board_meetings"],
    }

    prompt = f"""Today is {today}. You are a senior equity research analyst covering Indian equities.

Analyse why {stock.get('ticker')} has fallen sharply. The stock is {stock.get('drawdown_52w', 'N/A')}% below its 52-week high.

STOCK DATA:
{json.dumps(payload, indent=2)}

{"Annual report PDFs are attached above — reference them for any balance-sheet or business context." if pdf_parts else ""}

Classify the fall and assess whether it is TEMPORARY (macro/sentiment/sector rotation/one-off event) or STRUCTURAL (loss of market share, fraud, regulatory ban, business model broken).

Respond ONLY with a valid JSON object — no markdown, no preamble.

{{
  "primary_reason": "one clear sentence identifying the dominant cause",
  "detailed_analysis": "2-3 sentences citing specific evidence from announcements or board meetings",
  "fall_category": "macro | sector-rotation | company-specific | regulatory | promoter-concern | unknown",
  "is_temporary": true,
  "evidence": ["specific point 1", "specific point 2"],
  "structural_concerns": ["list any concrete structural risks found, or empty list if none"]
}}"""

    contents = pdf_parts + [types.Part.from_text(prompt)]
    print("  Running prompt 1/3: why_fell...")
    return _gemini_json(client, contents, model)


def prompt_management_quality(client, model, stock, nse_data, why_fell):
    """
    Prompt 2 — assess management quality and capital allocation discipline.
    Conditioned on prompt 1 output (why_fell).
    """
    today = datetime.date.today().strftime("%B %d, %Y")
    payload = {
        "ticker":              stock.get("ticker"),
        "promoter_pledge_pct": nse_data.get("promoter_pledge_pct"),
        "roe":                 stock.get("roe"),
        "operating_margin":    stock.get("operating_margin"),
        "net_margin":          stock.get("net_margin"),
        "revenue_growth":      stock.get("revenue_growth"),
        "debt_to_equity":      stock.get("debt_to_equity"),
        "ocf_cr":              stock.get("ocf_cr"),
        "announcements":       nse_data["announcements"],
        "board_meetings":      nse_data["board_meetings"],
        "why_fell_diagnosis":  why_fell,
    }

    pledge = nse_data.get("promoter_pledge_pct")
    pledge_note = (
        f"HARD RULE: promoter_pledge_pct is {pledge}% — if > 20%, cap management score at 4 "
        f"and set pledge_risk = 'high'."
        if pledge is not None and pledge > 20
        else "Promoter pledge is within acceptable range or unavailable."
    )

    prompt = f"""Today is {today}. You are a senior equity research analyst covering Indian equities.

Assess the management quality and capital allocation track record of {stock.get('ticker')}.

{pledge_note}

STOCK DATA (including why_fell diagnosis from prior analysis):
{json.dumps(payload, indent=2)}

Focus on:
- Capital allocation (ROE vs cost of capital, dividend / buyback history)
- Margin and growth consistency visible in the metrics
- Any management-related announcements (change in promoter holding, related-party transactions, auditor changes)
- Whether the board meetings reflect proactive or reactive governance

Respond ONLY with a valid JSON object — no markdown, no preamble.

{{
  "score": 7,
  "assessment": "2 sentences summarising overall management quality",
  "capital_allocation": "one sentence on ROE, margins, and reinvestment quality",
  "red_flags": ["specific flag if found, else empty list"],
  "positives": ["specific positive if found, else empty list"],
  "pledge_risk": "low | medium | high"
}}"""

    contents = [types.Part.from_text(prompt)]
    print("  Running prompt 2/3: management_quality...")
    return _gemini_json(client, contents, model)


def prompt_investment_case(client, model, stock, nse_data, why_fell, mgmt):
    """
    Prompt 3 — final scored investment recommendation.
    Conditioned on outputs of prompts 1 & 2.
    """
    today = datetime.date.today().strftime("%B %d, %Y")

    # Build a complete payload for the final prompt
    payload = {
        "ticker":              stock.get("ticker"),
        "name":                stock.get("name"),
        "sector":              stock.get("sector"),
        "price":               stock.get("price"),
        "change_1m":           stock.get("change_1m"),
        "change_3m":           stock.get("change_3m"),
        "drawdown_52w":        stock.get("drawdown_52w"),
        "panic_selling":       stock.get("panic_selling"),
        "pe_ratio":            stock.get("pe_ratio"),
        "forward_pe":          stock.get("forward_pe"),
        "pb_ratio":            stock.get("pb_ratio"),
        "roe":                 stock.get("roe"),
        "operating_margin":    stock.get("operating_margin"),
        "net_margin":          stock.get("net_margin"),
        "revenue_growth":      stock.get("revenue_growth"),
        "debt_to_equity":      stock.get("debt_to_equity"),
        "ocf_cr":              stock.get("ocf_cr"),
        "market_cap_cr":       stock.get("market_cap_cr"),
        "52w_high":            stock.get("52w_high"),
        "52w_low":             stock.get("52w_low"),
        "promoter_pledge_pct": nse_data.get("promoter_pledge_pct"),
        "announcements":       nse_data["announcements"],
        "why_fell":            why_fell,
        "management_quality":  mgmt,
    }

    mgmt_score = mgmt.get("score", 5)
    pledge     = nse_data.get("promoter_pledge_pct")
    hard_rules = []
    if pledge is not None and pledge > 20:
        hard_rules.append(f"promoter_pledge_pct = {pledge}% > 20% → cap score at 4, catalyst_ok = false")
    if mgmt_score <= 3:
        hard_rules.append(f"management score = {mgmt_score} ≤ 3 → cap overall score at 5")
    hard_rule_text = "\n".join(f"  - {r}" for r in hard_rules) if hard_rules else "  None triggered."

    prompt = f"""Today is {today}. You are a senior equity research analyst covering Indian equities.

Build the final investment case for {stock.get('ticker')} using the prior analysis results included in the JSON below.

HARD RULES (must be respected):
{hard_rule_text}

SCORING (+2 each, max 10):
  +2  P/E meaningfully below 5-year historical average (not marginally)
  +2  ROE above 15%
  +2  Balance sheet appropriate for sector (D/E < 0.5 non-financials; NPA quality for banks)
  +2  Specific concrete dated catalyst within 60 days (named event + date — NOT vague)
  +2  Fall is clearly macro/sentiment driven, NOT structural business deterioration

Scale: 8-10 = Strong Buy | 6-7 = Buy on confirmation | 4-5 = Watch | <4 = Avoid

FULL DATA:
{json.dumps(payload, indent=2)}

Respond ONLY with a valid JSON object — no markdown, no preamble.

{{
  "score": 7,
  "action": "Buy (Tranche 1)",
  "thesis": "2-3 sentences — the core investment case, referencing why_fell and management findings",
  "entry_strategy": "how to size and stage the position",
  "catalysts": ["specific event + date if found, else NONE"],
  "risks": ["specific risk 1", "specific risk 2"],
  "thesis_break": "one specific measurable condition that would invalidate the thesis",
  "time_horizon": "e.g. 12-18 months",
  "score_breakdown": {{
    "pe_ok": true,
    "roe_ok": true,
    "debt_ok": true,
    "catalyst_ok": false,
    "macro_driven": true
  }}
}}"""

    contents = [types.Part.from_text(prompt)]
    print("  Running prompt 3/3: investment_case...")
    return _gemini_json(client, contents, model)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def load_cached_stock(symbol):
    """
    Return the stock entry for *symbol* from data.json, or an empty dict if
    the file is missing or the symbol is not present.
    """
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
        stocks = data.get("stocks", [])
        for s in stocks:
            if s.get("ticker", "").upper() == symbol.upper():
                return s
    except Exception as e:
        print(f"  Could not read {DATA_FILE}: {e}")
    return {}


def run_analysis(symbol, model):
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        raise SystemExit(1)

    print(f"\nAnalysing {symbol}...\n")

    # ── Load cached fundamentals (may be empty if symbol not in data.json) ────
    stock = load_cached_stock(symbol)
    if stock:
        print(f"  Loaded cached fundamentals from {DATA_FILE}")
    else:
        print(f"  {symbol} not in {DATA_FILE} — fetching fundamentals fresh...")
        stock = {"ticker": symbol}
        stock.update(fetch_fundamentals(symbol))

    # ── Fetch fresh NSE context + PDFs ────────────────────────────────────────
    print(f"\nFetching NSE data for {symbol}...")
    nse_data = fetch_nse_data(symbol)
    print(f"  {len(nse_data['announcements'])} announcements, "
          f"{len(nse_data['board_meetings'])} board meetings, "
          f"{len(nse_data['pdf_paths'])} PDFs")

    # Override pledge with fresh value if available
    if nse_data["promoter_pledge_pct"] is not None:
        stock["promoter_pledge_pct"] = nse_data["promoter_pledge_pct"]

    # ── Upload PDFs once; reuse across prompts ─────────────────────────────────
    client    = genai.Client(api_key=GEMINI_API_KEY)
    pdf_parts = _upload_pdfs(client, nse_data["pdf_paths"])

    # ── Sequential Gemini prompts ──────────────────────────────────────────────
    print(f"\nRunning Gemini analysis ({model})...")
    why_fell = prompt_why_fell(client, model, stock, nse_data, pdf_parts)
    mgmt     = prompt_management_quality(client, model, stock, nse_data, why_fell)
    inv_case = prompt_investment_case(client, model, stock, nse_data, why_fell, mgmt)

    # ── Assemble output ────────────────────────────────────────────────────────
    output = {
        "symbol":           symbol.upper(),
        "analysed_at":      datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST"),
        "model":            model,
        "fundamentals":     {k: v for k, v in stock.items()
                             if k not in ("why_fell", "catalyst", "score", "action",
                                          "thesis_break", "score_breakdown",
                                          "value_trap_risk", "annual_report_pdf")},
        "why_fell":         why_fell,
        "management_quality": mgmt,
        "investment_case":  inv_case,
    }

    # ── Save ───────────────────────────────────────────────────────────────────
    ANALYSIS_DIR.mkdir(exist_ok=True)
    out_path = ANALYSIS_DIR / f"{symbol.upper()}.json"
    with open(out_path, "w") as f:
        json.dump(clean_nan(output), f, indent=2)
    print(f"\n  Saved -> {out_path}")
    return output


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Deep single-stock analysis via three sequential Gemini prompts"
    )
    parser.add_argument("symbol", help="NSE ticker symbol, e.g. RELIANCE")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Gemini model to use (default: {DEFAULT_MODEL})"
    )
    args = parser.parse_args()

    run_analysis(args.symbol.upper().replace(".NS", ""), args.model)
    print("\nDone!\n")


if __name__ == "__main__":
    main()
