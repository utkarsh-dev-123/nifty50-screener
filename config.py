# ── Screener configuration ────────────────────────────────────────────────────

# Drawdown filter: stock must be between DROP_MIN and DROP_MAX below 52W high
DROP_MIN = 0.25          # 25% below 52W high (minimum drawdown to qualify)
DROP_MAX = 0.65          # 65% below 52W high (maximum — beyond this = value trap risk)

# Graham balance-sheet screens
GRAHAM_MAX_DE     = 100  # debtToEquity < 100 (yFinance reports as %; 100 ≡ 1.0×)
GRAHAM_MIN_CR     = 2.0  # currentRatio > 2.0
GRAHAM_NCAV_MULT  = 2.0  # totalDebt < NCAV_MULT × (currentAssets − totalLiabilities)

# Screener output
TOP_N = 30               # number of candidates to pass to Gemini

# Market reference rate — used for future yield-spread screens
AAA_BOND_YIELD = 0.074   # approximate Indian AAA corporate bond yield (7.4%)
