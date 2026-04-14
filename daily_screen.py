"""
daily_screener.py — lightweight daily pipeline (no Gemini, no PDFs).

Scans all Nifty 500 stocks, applies price/drawdown/Graham filters,
fetches fundamentals and NSE announcements/pledge, then writes data.json.

Usage:
    python daily_screener.py          # full scan
    python daily_screener.py --test   # first 5 tickers only
"""

import sys
import json
import math
import argparse
import datetime
from pathlib import Path

import yfinance as yf
from nse import NSE

import config
from helpers import (
    safe_float,
    clean_nan,
    get_nifty500_tickers,
    passes_graham_screens,
    fetch_fundamentals,
)

OUTPUT_FILE = "data.json"


# ── NSE context: announcements + pledge (no PDF) ──────────────────────────────

def fetch_nse_context(symbol, nse):
    """
    Fetch from NSE India for a Graham-filter survivor:
      - Last 3 announcements from the past 90 days
      - Promoter pledge % (from shareholding)

    Both fall back gracefully — missing data is returned as empty/None.
    """
    result = {
        "announcements":       [],
        "promoter_pledge_pct": None,
    }
    cutoff = datetime.date.today() - datetime.timedelta(days=90)

    # 1. Announcements ─────────────────────────────────────────────────────────
    try:
        raw   = nse.announcements(symbol=symbol)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        recent = []
        for item in items:
            dt_str = (item.get("an_dt") or item.get("date") or
                      item.get("dt")    or item.get("exchdisstime") or "")
            dt = None
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    dt = datetime.datetime.strptime(dt_str[:11].strip(), fmt).date()
                    break
                except Exception:
                    continue
            if dt is None or dt >= cutoff:
                recent.append({
                    "date":    dt_str[:10],
                    "subject": (item.get("subject") or item.get("desc") or
                                item.get("headline") or ""),
                })
        result["announcements"] = recent[:3]
    except Exception as e:
        print(f"    announcements({symbol}): {e}")

    # 2. Promoter pledge % ─────────────────────────────────────────────────────
    try:
        from helpers import _find_pledge
        sh     = nse.shareholding(symbol=symbol)
        pledge = _find_pledge(sh)
        result["promoter_pledge_pct"] = pledge
    except Exception as e:
        print(f"    shareholding({symbol}): {e}")

    return result


# ── Main scanner ──────────────────────────────────────────────────────────────

def fetch_candidates(n=30, test=False):
    """
    Full pipeline for all Nifty 500 stocks:
      1. Fetch 3-month price history
      2. Dual lookback filter (1M and 3M both negative, 3M not worse than -40%)
      3. Drawdown filter (DROP_MIN–DROP_MAX below 52W high, from config)
      4. Graham balance-sheet screens (D/E, current ratio, debt cover)
      5. Volume spike detection
      6. Rank by 1M decline, return top n

    In test mode only the first 5 tickers are scanned.
    The raw yfinance info dict is cached in _yf_info so fetch_fundamentals
    can reuse it without a second network call.
    """
    tickers = get_nifty500_tickers()
    if test:
        tickers = tickers[:5]
        print("  [TEST MODE: limited to 5 tickers]\n")
    total = len(tickers)
    print(f"Scanning {total} Nifty 500 stocks...\n")

    drop_min_pct = config.DROP_MIN * 100   # e.g. 25.0
    drop_max_pct = config.DROP_MAX * 100   # e.g. 65.0

    q_passed = q_failed = d_failed = l_failed = 0
    candidates = []

    for i, ticker in enumerate(tickers, 1):
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
            if change_1m >= 0 or change_3m >= 0 or change_3m < -drop_max_pct:
                l_failed += 1
                continue

            # ── Fundamentals (needed for quality filter + drawdown) ────────────
            info     = yf.Ticker(ticker).info
            high_52w = safe_float(info.get("fiftyTwoWeekHigh"))

            # ── FILTER: Drawdown DROP_MIN–DROP_MAX from 52W high ──────────────
            if high_52w and high_52w > 0:
                drawdown = ((current_price - high_52w) / high_52w) * 100
                if drawdown > -drop_min_pct or drawdown < -drop_max_pct:
                    d_failed += 1
                    continue
            else:
                drawdown = None

            # ── FILTER: Graham balance-sheet screens ──────────────────────────
            graham = passes_graham_screens(ticker, info)
            if not graham["passed"]:
                q_failed += 1
                print(f"  x {sym:20s}  {graham['reason']}")
                continue
            q_passed += 1

            # ── Volume spike ───────────────────────────────────────────────────
            avg_vol_3m   = float(volume.mean())
            avg_vol_5d   = float(volume.iloc[-5:].mean())
            volume_ratio = round(avg_vol_5d / avg_vol_3m, 2) if avg_vol_3m > 0 else None
            panic_selling = volume_ratio is not None and volume_ratio >= 1.5

            candidates.append({
                "ticker":           sym,
                "price":            round(current_price, 2),
                "change_1m":        round(change_1m, 2),
                "change_3m":        round(change_3m, 2),
                "drawdown_52w":     round(drawdown, 1) if drawdown is not None else None,
                "volume_ratio":     volume_ratio,
                "panic_selling":    panic_selling,
                "s6_debt_equity":   graham["s6_debt_equity"],
                "s7_current_ratio": graham["s7_current_ratio"],
                "s8_debt_cover":    graham["s8_debt_cover"],
                "_yf_info":         info,   # cached — reused by fetch_fundamentals
            })

            if i % 50 == 0:
                print(f"  ... {i}/{total} scanned, {len(candidates)} candidates so far")

        except Exception as e:
            print(f"  Skipping {sym}: {e}")

    print(f"\n  -- Filter summary -----------------------------------")
    print(f"     Dual lookback eliminated:   {l_failed}")
    print(f"     Drawdown filter eliminated: {d_failed}")
    print(f"     Quality filter: {q_passed} passed, {q_failed} failed")
    print(f"     Final candidates:           {len(candidates)}")

    if not candidates:
        return []

    candidates.sort(key=lambda x: x["change_1m"])
    top = candidates[:n]
    print(f"\n  Top {n}: {[s['ticker'] for s in top]}\n")
    return top


# ── Save results ──────────────────────────────────────────────────────────────

def save_results(stocks):
    output = {
        "date":         datetime.date.today().isoformat(),
        "generated_at": datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST"),
        "index":        "Nifty 500",
        "version":      "daily",
        "stocks":       stocks,
    }
    clean = clean_nan(output)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(clean, f, indent=2)
    print(f"  Saved {len(stocks)} stocks → {OUTPUT_FILE}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nifty 500 Daily Screener (no Gemini)")
    parser.add_argument("--test", action="store_true",
                        help="Scan only the first 5 tickers (fast smoke-test)")
    args = parser.parse_args()

    top_n = 5 if args.test else config.TOP_N

    print(f"\n{'='*55}")
    print(f"  Nifty 500 Daily Screener  |  {datetime.date.today()}"
          + ("  [TEST]" if args.test else ""))
    print(f"{'='*55}\n")

    # Stage 1 — price/drawdown/Graham filter
    candidates = fetch_candidates(n=top_n, test=args.test)

    if not candidates:
        print("No candidates passed filters - market may be closed or filters too strict.")
        raise SystemExit(1)

    # Stage 2 — fundamentals (reuses cached yfinance info)
    print("Fetching fundamentals for candidates...")
    for stock in candidates:
        print(f"  {stock['ticker']}")
        cached_info = stock.pop("_yf_info", None)
        stock.update(fetch_fundamentals(stock["ticker"], info=cached_info))

    # Stage 3 — NSE announcements + pledge (no PDFs)
    print("\nFetching NSE context (announcements, shareholding)...")
    with NSE(download_folder=Path("."), server=False) as nse:
        for stock in candidates:
            print(f"  {stock['ticker']}")
            stock.update(fetch_nse_context(stock["ticker"], nse))

    # Stage 4 — write data.json
    save_results(candidates)
    print("\nDone!\n")


if __name__ == "__main__":
    main()
