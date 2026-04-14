# Nifty 500 Falling Knife Screener — Architecture Guide

## What this project does

Scans all ~500 Nifty 500 constituents daily, applies a multi-stage filter pipeline,
and writes results to `data.json`. A separate on-demand script runs three sequential
Gemini prompts for any stock and writes a deep analysis to `analysis/<SYMBOL>.json`.
Both outputs are rendered by `docs/index.html`.

---

## Two-script architecture

### `daily_screen.py` — daily screener (no Gemini, no PDFs)

Runs every weekday via `.github/workflows/daily_screen.yml`.
No API key required.

```
NSE live constituent list
        │
        ▼
  yfinance 3-month price history
        │
        ├─ Dual lookback filter   (1M < 0, 3M < 0, 3M > −DROP_MAX%)
        │
        ├─ 52W drawdown filter    (DROP_MIN%–DROP_MAX% below 52W high)
        │
        ├─ Graham balance-sheet screens (config.py thresholds)
        │     Screen 6: debtToEquity < 100  (yFinance % scale; 100 = 1.0×)
        │     Screen 7: currentRatio > 2.0
        │     Screen 8: totalDebt < 2 × (currentAssets − totalLiabilities)
        │
        ▼
  Graham survivors
        │
        ├─ fetch_fundamentals()   — yfinance .info (reuses cached dict)
        │
        ├─ fetch_nse_context()    — announcements (last 3) + promoter pledge %
        │                          no PDFs downloaded
        ▼
  save_results() → data.json
```

### `analyse_stock.py` — deep single-stock analysis (Gemini, PDFs)

Triggered on demand via `.github/workflows/analyse_stock.yml` (workflow_dispatch
with a `symbol` input) or locally: `python analyse_stock.py <SYMBOL>`.
Requires `GEMINI_API_KEY`.

```
data.json (cached fundamentals, optional)
        │
        ▼
  fetch_nse_data()
        │  • announcements (last 90 days)
        │  • board meetings (quarterly results context)
        │  • promoter pledge %
        │  • latest 2 annual report PDFs → pdfs/
        │
        ▼
  Gemini Files API — upload PDFs once, reuse across all prompts
        │
        ├─ Prompt 1: why_fell
        │     price metrics + announcements + board meetings + PDFs
        │     → primary_reason, fall_category, is_temporary, evidence
        │
        ├─ Prompt 2: management_quality
        │     financial ratios + pledge + why_fell output
        │     → score/10, capital_allocation, red_flags, pledge_risk
        │
        ├─ Prompt 3: investment_case
        │     all fundamentals + prompt 1 + prompt 2 outputs
        │     → score/10, action, thesis, catalysts, risks, thesis_break
        │
        ▼
  analysis/<SYMBOL>.json
```

Each Gemini prompt tries Google Search grounding first, falls back to a plain call.

---

## File map

| File | Purpose |
|------|---------|
| `daily_screen.py` | Daily pipeline: filter → fundamentals → NSE context → `data.json`. |
| `analyse_stock.py` | On-demand deep analysis: NSE data → 3× Gemini → `analysis/<SYMBOL>.json`. |
| `helpers.py` | Shared utilities: `safe_float`, `clean_nan`, `get_sector_type`, `get_nifty500_tickers`, `passes_graham_screens`, `_find_pledge`, `fetch_fundamentals`. |
| `config.py` | Numeric thresholds (`DROP_MIN`, `DROP_MAX`, Graham limits, `TOP_N`). Edit here to tune without touching logic. |
| `main.py` | **Deprecated.** Thin shim that calls `daily_screen.main()` for backward compatibility. |
| `data.json` | Daily screener output consumed by `docs/index.html`. Overwritten on every run. |
| `analysis/` | Per-stock deep analysis JSONs written by `analyse_stock.py`. |
| `docs/index.html` | Static frontend — sortable table of `data.json` stocks; Analyse button dispatches `analyse_stock.yml` and polls for results. |
| `pdfs/` | Annual report PDFs downloaded by `analyse_stock.py`. Cached — re-runs skip existing files. |
| `requirements.txt` | Python dependencies. |
| `.github/workflows/daily_screen.yml` | Runs `daily_screen.py` weekdays at 9:00 AM IST. |
| `.github/workflows/analyse_stock.yml` | `workflow_dispatch` with `symbol` input; runs `analyse_stock.py`; commits `analysis/`. |

---

## Graham screens logic

All three screens give **benefit of the doubt when data is missing** (result is `None`,
which counts as passing). A stock is eliminated only when data is present *and* fails
the threshold.

- **Screen 6 (D/E)**: yfinance `debtToEquity` is in percentage form — a value of
  `50` means 0.5× D/E. The threshold is `< 100` (≡ D/E < 1.0×).
- **Screen 7 (current ratio)**: direct ratio from yfinance `currentRatio`. Must be
  `> 2.0`.
- **Screen 8 (debt cover)**: `totalDebt < 2 × (currentAssets − totalLiabilities)`.
  Uses `currentAssets` as primary key, falls back to `totalCurrentAssets`.
  `totalLiabilities` tries `totalLiab` as fallback.

Per-screen booleans (`s6_debt_equity`, `s7_current_ratio`, `s8_debt_cover`) are
stored on each surviving candidate and written to `data.json`.

---

## Configuration (`config.py`)

| Constant | Default | Meaning |
|----------|---------|---------|
| `DROP_MIN` | `0.25` | Minimum drawdown from 52W high to qualify (25%) |
| `DROP_MAX` | `0.65` | Maximum drawdown — beyond this is value-trap territory (65%) |
| `GRAHAM_MAX_DE` | `100` | Max `debtToEquity` (yFinance % scale; 100 ≡ 1.0×) |
| `GRAHAM_MIN_CR` | `2.0` | Min `currentRatio` |
| `GRAHAM_NCAV_MULT` | `2.0` | Debt-cover multiplier for Screen 8 |
| `TOP_N` | `30` | Candidates passed through to output |

---

## Known failure modes

### NSE closed / holiday
`get_nifty500_tickers()` and NSE context fetches call the NSE API. On holidays or
maintenance windows, NSE returns empty/error responses. The screener produces 0
candidates or misses announcements. Both workflows have `workflow_dispatch` so you
can re-trigger manually after the exchange opens.

### yfinance key changes
yfinance scrapes Yahoo Finance and occasionally breaks when Yahoo changes its API.
Common symptoms: `info` returns an empty dict, or keys like `debtToEquity` /
`currentRatio` go missing. When all three Graham screens return `None` (benefit of
the doubt), stocks pass unintentionally. Fix: pin a working yfinance version in
`requirements.txt`.

### Gemini PDF size limits
The Gemini Files API accepts PDFs up to 50 MB. Annual reports can exceed this.
`_upload_pdfs()` in `analyse_stock.py` catches upload errors per-file and skips
silently — the text analysis still proceeds without the PDF.

### Gemini search grounding unavailable
Both scripts try `google_search` grounding first and fall back to a plain call on
failure. If both fail, the exception propagates and the run exits non-zero.

---

## --test flag

```bash
python daily_screen.py --test
python main.py --test          # delegates to daily_screen.main()
```

Limits the scan to the **first 5 tickers** returned by NSE. Useful for smoke-testing
after dependency upgrades or verifying the pipeline without waiting 30+ minutes.
