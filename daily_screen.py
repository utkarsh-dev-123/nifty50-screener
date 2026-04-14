"""
daily_screen.py — 8-stage pipeline (no Gemini, no PDFs).

Scans all Nifty 500 stocks through 8 progressive filters and writes data.json.

Pipeline:
  Stage 0 — Universe via NseIndiaApi (symbols + live price/pChange)
  Stage 1 — Drop stocks with missing price/pChange (no API calls)
  Stage 2 — Age filter: reject stocks listed < 1 year (NseIndiaApi equityMetaInfo)
  Stage 3 — Momentum OR filter + freefall reject (yFinance 2y monthly)
  Stage 4 — Fundamentals + 52W drawdown filter (yFinance .info)
  Stage 5 — Small cap structural decline check (uses Stage 3 prices, no extra calls)
  Stage 6 — Graham balance-sheet screens, sector-aware (uses cached .info)
  Stage 7 — NSE context: announcements + promoter pledge (NseIndiaApi)
  Stage 8 — Build output dicts and save to data.json

Usage:
    python daily_screen.py          # full scan
    python daily_screen.py --test   # first 10 stocks only (smoke-test)
"""

import json
import math
import time
import argparse
import datetime
from pathlib import Path

import yfinance as yf
from nse import NSE

import config
from helpers import (
    safe_float,
    clean_nan,
    get_nifty500_stocks,
    passes_graham_screens,
    fetch_fundamentals,
    _find_pledge,
)

OUTPUT_FILE = "data.json"


# ── Stage 7 helper: NSE context ───────────────────────────────────────────────

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

    # 1. Announcements
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

    # 2. Promoter pledge %
    try:
        sh     = nse.shareholding(symbol=symbol)
        pledge = _find_pledge(sh)
        result["promoter_pledge_pct"] = pledge
    except Exception as e:
        print(f"    shareholding({symbol}): {e}")

    return result


# ── 8-stage pipeline ──────────────────────────────────────────────────────────

def fetch_candidates(test=False):
    """
    Run all 8 stages and return a list of candidate dicts sorted by
    change_1m ascending (worst performing first).
    Internal-only fields (_yf_info, price_1y_ago, price_2y_ago,
    current_price) are stripped before returning.
    """

    # ── STAGE 0 — Universe ────────────────────────────────────────────────────
    print("Stage 0: Fetching Nifty 500 universe from NSE...")
    stocks  = get_nifty500_stocks()
    s0_total = len(stocks)

    if test:
        stocks = stocks[:10]
        print(f"  [TEST MODE: limited to {len(stocks)} stocks]\n")

    # ── STAGE 1 — Drop missing price/pChange (no API calls) ──────────────────
    print("Stage 1: Filtering stocks with missing price/pChange data...")
    s0_no_data = 0
    stage1 = []
    for s in stocks:
        if s["pChange"] is None or s["lastPrice"] is None or s["lastPrice"] == 0:
            s0_no_data += 1
            continue
        s["triggered_1d"] = s["pChange"] <= config.MIN_1D_DROP
        stage1.append(s)
    print(f"  {len(stage1)} stocks have valid price data\n")

    # ── STAGE 2 — Age filter (NseIndiaApi equityMetaInfo) ────────────────────
    print("Stage 2: Filtering stocks listed < 1 year ago...")
    age_failed = 0
    stage2    = []
    today     = datetime.date.today()

    with NSE(download_folder=Path("."), server=False) as nse:
        for s in stage1:
            sym = s["symbol"]
            try:
                meta = nse.equityMetaInfo(sym)
                listing_str = (meta.get("listingDate") or
                               meta.get("listing_date") or
                               meta.get("listingdate") or "")
                listing_date = None
                for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        listing_date = datetime.datetime.strptime(
                            listing_str[:11].strip(), fmt).date()
                        break
                    except Exception:
                        continue

                if listing_date is not None:
                    age_days = (today - listing_date).days
                    if age_days < config.MIN_LISTING_AGE_DAYS:
                        age_failed += 1
                        continue
            except Exception:
                pass  # benefit of doubt if API fails

            stage2.append(s)
            time.sleep(0.4)

    print(f"  {len(stage2)} stocks passed age filter\n")

    # ── STAGE 3 — Price history + OR momentum filter (yFinance) ──────────────
    print("Stage 3: Downloading price history and applying momentum OR filter...")
    momentum_failed = 0
    freefall_failed = 0
    stage3          = []
    n2              = len(stage2)

    for i, s in enumerate(stage2, 1):
        sym    = s["symbol"]
        ticker = s["ticker"]
        try:
            hist = yf.download(ticker, period="2y", interval="1mo",
                               progress=False, auto_adjust=True)
            if hist.empty:
                continue

            close = hist["Close"].squeeze()
            if len(close) < 6:
                continue

            current_price = float(close.iloc[-1])
            if math.isnan(current_price) or current_price == 0:
                continue

            # 1M change: last month vs 2 months ago
            change_1m = None
            if len(close) >= 2:
                prev = float(close.iloc[-2])
                if prev and not math.isnan(prev):
                    change_1m = (current_price - prev) / prev * 100

            # 3M change: last vs 4 months ago
            change_3m = None
            if len(close) >= 4:
                prev = float(close.iloc[-4])
                if prev and not math.isnan(prev):
                    change_3m = (current_price - prev) / prev * 100

            # 1Y change: last vs 13 months ago
            change_1y = None
            if len(close) >= 13:
                prev = float(close.iloc[-13])
                if prev and not math.isnan(prev):
                    change_1y = (current_price - prev) / prev * 100

            # Store prices for Stage 5 small cap check
            price_1y_ago = float(close.iloc[-13]) if len(close) >= 13 else None
            price_2y_ago = float(close.iloc[-25]) if len(close) >= 25 else None

            # OR trigger: keep stock if ANY condition met
            pChange = s["pChange"]
            triggered = (
                (pChange is not None and pChange <= config.MIN_1D_DROP) or
                (change_1m is not None and change_1m <= config.MIN_1M_DROP) or
                (change_3m is not None and change_3m <= config.MIN_3M_DROP)
            )
            if not triggered:
                momentum_failed += 1
                continue

            # Hard reject: freefall (these are NOT contrarian opportunities)
            if change_3m is not None and change_3m < config.MAX_3M_DROP:
                freefall_failed += 1
                continue
            if change_1y is not None and change_1y < config.MAX_1Y_DROP:
                freefall_failed += 1
                continue

            # Volume
            volume     = hist["Volume"].squeeze()
            avg_vol    = float(volume.mean())   if len(volume) > 0 else 0
            recent_vol = float(volume.iloc[-1]) if len(volume) > 0 else 0
            volume_ratio  = round(recent_vol / avg_vol, 2) if avg_vol > 0 else None
            panic_selling = volume_ratio is not None and volume_ratio >= 1.5

            s.update({
                "current_price": round(current_price, 2),
                "change_1m":     round(change_1m, 2) if change_1m is not None else None,
                "change_3m":     round(change_3m, 2) if change_3m is not None else None,
                "change_1y":     round(change_1y, 2) if change_1y is not None else None,
                "price_1y_ago":  price_1y_ago,
                "price_2y_ago":  price_2y_ago,
                "volume_ratio":  volume_ratio,
                "panic_selling": panic_selling,
                "triggered_1m":  change_1m is not None and change_1m <= config.MIN_1M_DROP,
                "triggered_3m":  change_3m is not None and change_3m <= config.MIN_3M_DROP,
            })
            stage3.append(s)

            if i % 50 == 0:
                print(f"  ... {i}/{n2} processed, {len(stage3)} survivors so far")

        except Exception as e:
            print(f"  Skipping {sym}: {e}")

    print(f"  {len(stage3)} stocks passed momentum filter\n")

    # ── STAGE 4 — Fundamentals + 52W drawdown filter (yFinance .info) ────────
    print("Stage 4: Fetching fundamentals and applying drawdown filter...")
    drawdown_failed = 0
    stage4          = []
    drop_min_pct    = config.DROP_MIN * 100
    drop_max_pct    = config.DROP_MAX * 100

    for s in stage3:
        sym    = s["symbol"]
        ticker = s["ticker"]
        try:
            info          = yf.Ticker(ticker).info
            market_cap    = safe_float(info.get("marketCap"))
            market_cap_cr = round(market_cap / 1e7, 1) if market_cap else None
            high_52w      = safe_float(info.get("fiftyTwoWeekHigh"))
            low_52w       = safe_float(info.get("fiftyTwoWeekLow"))
            sector        = info.get("sector", "Unknown")
            current_price = s["current_price"]

            # Drawdown from 52W high
            if high_52w and high_52w > 0:
                drawdown = ((current_price - high_52w) / high_52w) * 100
                if drawdown > -drop_min_pct or drawdown < -drop_max_pct:
                    drawdown_failed += 1
                    continue
            else:
                drawdown = None  # benefit of doubt

            s.update({
                "market_cap_cr": market_cap_cr,
                "high_52w":      high_52w,
                "low_52w":       low_52w,
                "sector":        sector,
                "drawdown_52w":  round(drawdown, 1) if drawdown is not None else None,
                "_yf_info":      info,
            })
            stage4.append(s)

        except Exception as e:
            print(f"  Skipping {sym}: {e}")

    print(f"  {len(stage4)} stocks passed drawdown filter\n")

    # ── STAGE 5 — Small cap structural decline (uses Stage 3 prices) ─────────
    print("Stage 5: Checking small cap structural decline...")
    smallcap_failed = 0
    stage5          = []

    for s in stage4:
        sym           = s["symbol"]
        market_cap_cr = s.get("market_cap_cr")
        current_price = s["current_price"]
        price_1y_ago  = s.get("price_1y_ago")
        price_2y_ago  = s.get("price_2y_ago")

        if market_cap_cr is not None and market_cap_cr < config.SMALL_CAP_CR:
            if price_1y_ago is not None and price_2y_ago is not None:
                yr1 = (current_price - price_1y_ago) / price_1y_ago
                yr2 = (price_1y_ago  - price_2y_ago) / price_2y_ago
                if yr1 < config.SMALL_CAP_YOY_DECLINE and yr2 < config.SMALL_CAP_YOY_DECLINE:
                    smallcap_failed += 1
                    print(f"  x {sym:20s}  small cap structural decline "
                          f"(yr1={yr1*100:.0f}%, yr2={yr2*100:.0f}%)")
                    continue

        s["is_small_cap"] = (market_cap_cr is not None and
                             market_cap_cr < config.SMALL_CAP_CR)
        stage5.append(s)

    print(f"  {len(stage5)} stocks passed small cap check\n")

    # ── STAGE 6 — Graham balance-sheet screens (uses cached .info) ───────────
    print("Stage 6: Applying Graham balance-sheet screens...")
    graham_failed = 0
    graham_passed = 0
    stage6        = []

    for s in stage5:
        sym    = s["symbol"]
        info   = s["_yf_info"]
        graham = passes_graham_screens(s["ticker"], info)
        if not graham["passed"]:
            graham_failed += 1
            print(f"  x {sym:20s}  {graham['reason']}")
            continue
        graham_passed += 1
        s.update({
            "s6_debt_equity":   graham["s6_debt_equity"],
            "s7_current_ratio": graham["s7_current_ratio"],
            "s8_debt_cover":    graham["s8_debt_cover"],
        })
        stage6.append(s)

    print(f"  {graham_passed} passed, {graham_failed} failed Graham screens\n")

    # ── STAGE 7 — NSE context ─────────────────────────────────────────────────
    print("Stage 7: Fetching NSE context (announcements, shareholding)...")
    with NSE(download_folder=Path("."), server=False) as nse:
        for s in stage6:
            sym = s["symbol"]
            print(f"  {sym}")
            s.update(fetch_nse_context(sym, nse))

    # ── Filter summary ────────────────────────────────────────────────────────
    candidates = stage6
    print(f"\n  Stage 0  Total universe:          {s0_total}")
    print(f"  Stage 1  No price/pChange data:   {s0_no_data}")
    print(f"  Stage 2  Listed < 1 year:         {age_failed}")
    print(f"  Stage 3  No momentum trigger:     {momentum_failed}")
    print(f"  Stage 3  Freefall rejected:       {freefall_failed}")
    print(f"  Stage 4  Drawdown out of range:   {drawdown_failed}")
    print(f"  Stage 5  Small cap structural:    {smallcap_failed}")
    print(f"  Stage 6  Graham failed:           {graham_failed}")
    print(f"  Stage 6  Graham passed:           {graham_passed}")
    print(f"  FINAL    Candidates:              {len(candidates)}")

    if not candidates:
        return []

    candidates.sort(key=lambda x: (x.get("change_1m") or 0))
    return candidates


# ── Stage 8 helper: build clean output dict ───────────────────────────────────

def build_output(s):
    """Assemble the JSON-safe output dict for a single candidate."""
    info         = s.get("_yf_info", {})
    fundamentals = fetch_fundamentals(s["symbol"], info=info)

    return {
        "ticker":              s["symbol"],
        "name":                fundamentals.get("name") or s.get("name", s["symbol"]),
        "sector":              s.get("sector", "Unknown"),
        "price":               s.get("current_price"),
        "pChange":             s.get("pChange"),
        "change_1m":           s.get("change_1m"),
        "change_3m":           s.get("change_3m"),
        "change_1y":           s.get("change_1y"),
        "drawdown_52w":        s.get("drawdown_52w"),
        "market_cap_cr":       s.get("market_cap_cr"),
        "is_small_cap":        s.get("is_small_cap", False),
        "volume_ratio":        s.get("volume_ratio"),
        "panic_selling":       s.get("panic_selling", False),
        "triggered_1d":        s.get("triggered_1d", False),
        "triggered_1m":        s.get("triggered_1m", False),
        "triggered_3m":        s.get("triggered_3m", False),
        "s6_debt_equity":      s.get("s6_debt_equity"),
        "s7_current_ratio":    s.get("s7_current_ratio"),
        "s8_debt_cover":       s.get("s8_debt_cover"),
        "pe_ratio":            fundamentals.get("pe_ratio"),
        "pb_ratio":            fundamentals.get("pb_ratio"),
        "roe":                 fundamentals.get("roe"),
        "debt_to_equity":      fundamentals.get("debt_to_equity"),
        "operating_margin":    fundamentals.get("operating_margin"),
        "net_margin":          fundamentals.get("net_margin"),
        "revenue_growth":      fundamentals.get("revenue_growth"),
        "ocf_cr":              fundamentals.get("ocf_cr"),
        "52w_high":            s.get("high_52w"),
        "52w_low":             s.get("low_52w"),
        "promoter_pledge_pct": s.get("promoter_pledge_pct"),
        "announcements":       s.get("announcements", []),
    }


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
    parser = argparse.ArgumentParser(description="Nifty 500 Daily Screener — 8-stage pipeline")
    parser.add_argument("--test", action="store_true",
                        help="Scan only the first 10 stocks (fast smoke-test)")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Nifty 500 Daily Screener  |  {datetime.date.today()}"
          + ("  [TEST]" if args.test else ""))
    print(f"{'='*55}\n")

    # Stages 0–7
    candidates = fetch_candidates(test=args.test)

    if not candidates:
        print("No candidates passed filters — market may be closed or filters too strict.")
        raise SystemExit(1)

    # Stage 8 — build output dicts and save
    print("\nStage 8: Building output and saving to data.json...")
    output_stocks = [build_output(s) for s in candidates]
    save_results(output_stocks)
    print("\nDone!\n")


if __name__ == "__main__":
    main()
