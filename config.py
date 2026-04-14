# ── Screener configuration ────────────────────────────────────────────────────

# Drawdown filter: stock must be between DROP_MIN and DROP_MAX below 52W high
DROP_MIN = 0.25          # 25% below 52W high (minimum drawdown to qualify)
DROP_MAX = 0.65          # 65% below 52W high (maximum — beyond this = value trap risk)

# Graham balance-sheet screens
GRAHAM_MAX_DE     = 100  # debtToEquity < 100 (yFinance reports as %; 100 ≡ 1.0×)
GRAHAM_MIN_CR     = 2.0  # currentRatio > 2.0
GRAHAM_NCAV_MULT  = 2.0  # totalDebt < NCAV_MULT × (currentAssets − totalLiabilities)

# Screener output
TOP_N = 30               # number of candidates to pass to Gemini (legacy; no longer used as cap)

# Market reference rate — used for future yield-spread screens
AAA_BOND_YIELD = 0.074   # approximate Indian AAA corporate bond yield (7.4%)

# Stage 1 — single day drop trigger
MIN_1D_DROP          = -5.0   # pChange ≤ -5% counts as a trigger

# Stage 3 — monthly price history OR filter
MIN_1M_DROP          = -10.0  # 1-month change ≤ -10% counts as trigger
MIN_3M_DROP          = -10.0  # 3-month change ≤ -10% counts as trigger
MAX_3M_DROP          = -50.0  # worse than -50% in 3M = freefall, reject
MAX_1Y_DROP          = -70.0  # worse than -70% in 1Y = structural, reject

# Stage 2 — listing age
MIN_LISTING_AGE_DAYS = 365    # reject stocks listed < 1 year ago

# Stage 5 — small cap structural decline
SMALL_CAP_CR          = 5000  # market cap threshold in Crores
SMALL_CAP_YOY_DECLINE = -0.15 # reject if down 15%+ two years running
