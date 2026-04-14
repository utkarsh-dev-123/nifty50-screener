# DEPRECATED — main.py is kept only for backward compatibility.
#
# The monolithic pipeline has been split into two focused scripts:
#
#   daily_screen.py    Price/drawdown/Graham filter + NSE context → data.json
#                      Runs every weekday via .github/workflows/daily_screen.yml
#                      No Gemini, no PDFs — fast and free.
#
#   analyse_stock.py   Deep single-stock analysis via three sequential Gemini
#                      prompts (why_fell, management_quality, investment_case).
#                      Triggered on demand via .github/workflows/analyse_stock.yml
#                      or: python analyse_stock.py <SYMBOL>
#
# This file now simply delegates to daily_screen.main() so that any
# existing scripts or CI steps that call `python main.py` still work.

import daily_screen

if __name__ == "__main__":
    daily_screen.main()
