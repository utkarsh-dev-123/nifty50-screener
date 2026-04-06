# Nifty 50 Falling Knife Screener — Setup Guide

This guide sets up your fully automated system in about 45 minutes.
After setup, you will receive a WhatsApp message + email every weekday morning at 8 AM IST with scored stock picks. All data is logged to Google Sheets automatically.

---

## What you'll set up (in order)

1. Anthropic API key (Claude)
2. Google Sheets + service account
3. Gmail app password
4. Twilio WhatsApp account
5. GitHub (runs the script daily for free)

---

## Step 1 — Get your Anthropic (Claude) API key

1. Go to https://console.anthropic.com
2. Sign in or create an account
3. Click **API Keys** in the left sidebar → **Create Key**
4. Copy the key (starts with `sk-ant-...`)
5. Save it somewhere safe — you'll need it in Step 5

---

## Step 2 — Set up Google Sheets

### 2a. Create the spreadsheet
1. Go to https://sheets.google.com
2. Create a new blank spreadsheet
3. Name it exactly: **Nifty50 Stock Screener**
   (must match what's in the script)

### 2b. Create a Google Service Account
This is what lets the script write to your sheet automatically.

1. Go to https://console.cloud.google.com
2. Create a new project (call it anything, e.g. "StockScreener")
3. In the search bar, search for **"Google Sheets API"** → Enable it
4. Search for **"Google Drive API"** → Enable it
5. Go to **IAM & Admin → Service Accounts → Create Service Account**
6. Name it `stock-screener` → click Create
7. Skip the optional steps → click Done
8. Click on the service account you just created
9. Go to the **Keys** tab → **Add Key → Create new key → JSON**
10. A file downloads — rename it `google_creds.json`
11. Open your Google Sheet → click **Share** → paste the service account email (looks like `stock-screener@your-project.iam.gserviceaccount.com`) → give it **Editor** access

---

## Step 3 — Get a Gmail App Password

You need this so the script can send email on your behalf without using your real password.

1. Go to your Google Account → **Security**
2. Make sure **2-Step Verification** is ON
3. Search for **"App passwords"** in the security page
4. Click **App passwords** → Select app: **Mail** → Select device: **Other** → name it "StockScreener"
5. Copy the 16-character password shown (e.g. `abcd efgh ijkl mnop`)
6. Remove the spaces when you use it: `abcdefghijklmnop`

---

## Step 4 — Set up Twilio WhatsApp

1. Go to https://www.twilio.com → Sign up for a free account
2. After signing in, go to **Messaging → Try it out → Send a WhatsApp message**
3. Follow the instructions to connect your WhatsApp number to the Twilio Sandbox
   (you'll send a join code from your WhatsApp to their number)
4. From the Twilio Console, note down:
   - **Account SID** (starts with `AC...`)
   - **Auth Token**
5. Your WhatsApp number format for the script: `whatsapp:+919876543210`
   (use your country code — India is +91)

---

## Step 5 — Set up GitHub (runs it daily for free)

### 5a. Create a GitHub account
If you don't have one: https://github.com → Sign Up (free)

### 5b. Create a new repository
1. Click **+** → **New repository**
2. Name it `nifty50-screener`
3. Set it to **Private**
4. Click **Create repository**

### 5c. Upload your files
Upload these three files to the repository:
- `screener.py`
- `requirements.txt`
- `.github/workflows/daily_screener.yml`

To upload:
1. In your repository, click **Add file → Upload files**
2. Drag and drop `screener.py` and `requirements.txt`
3. Click **Commit changes**

For the workflow file:
1. Click **Add file → Create new file**
2. In the filename box, type: `.github/workflows/daily_screener.yml`
3. Paste the contents of `daily_screener.yml`
4. Click **Commit changes**

### 5d. Add your secret keys
This keeps your passwords safe — never paste them into the code.

1. In your GitHub repo → **Settings → Secrets and variables → Actions**
2. Click **New repository secret** for each of the following:

| Secret Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key from Step 1 |
| `GOOGLE_CREDS_JSON` | The entire contents of `google_creds.json` (open it, select all, copy) |
| `EMAIL_SENDER` | Your Gmail address |
| `EMAIL_PASSWORD` | Your 16-char Gmail app password from Step 3 |
| `EMAIL_RECIPIENT` | Email where you want to receive alerts (can be same as sender) |
| `TWILIO_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_TO` | Your WhatsApp number e.g. `whatsapp:+919876543210` |

---

## Step 6 — Test it manually

Before waiting for the 8 AM run, trigger it manually to confirm everything works:

1. In your GitHub repo → **Actions** tab
2. Click **Daily Nifty 50 Stock Screener** in the left panel
3. Click **Run workflow → Run workflow**
4. Watch the logs — it should complete in about 2–3 minutes
5. Check your email, WhatsApp, and Google Sheet

---

## What you'll receive every morning

### WhatsApp / Email
```
📊 NIFTY 50 FALLING KNIFE SCREENER — April 5, 2026
==================================================

📌 Market Context: [2-sentence summary of market conditions]

🟢 TCS  |  ₹2,490  |  -34% (1M)  |  Score: 8/10
   Why fell:  FII selling + IT sector pressure from global tariff fears
   Catalyst:  Q4 results April 9 — AI deal momentum expected
   Action:    Buy (Tranche 1)
   Exit if:   Negative constant-currency revenue guidance for FY27

🟡 WIPRO  |  ₹187  |  -28% (1M)  |  Score: 6/10
   ...

🔴 TRENT  |  ₹3,405  |  -36% (1M)  |  Score: 4/10
   ...

🟢 = Buy candidate (7+)  🟡 = Watch (5-6)  🔴 = Avoid (<5)
```

### Google Sheets
- **Daily Log** tab: every stock screened, every day, with all metrics
- **Watchlist** tab: only stocks that scored 7+ (auto-populated)

---

## Schedule

The script runs automatically at **8:00 AM IST, Monday to Friday**.
You can also trigger it manually any time from the GitHub Actions tab.

---

## Estimated costs

| Service | Cost |
|---|---|
| Anthropic API | ~₹2–5 per day (one Claude call) |
| GitHub Actions | Free (within free tier limits) |
| Google Sheets API | Free |
| Twilio WhatsApp | Free during sandbox trial; ~₹0.50/message after |
| Gmail | Free |
| **Total** | **~₹3–10/day** |

---

## Troubleshooting

**Email not arriving?**
- Check your spam folder
- Make sure 2-Step Verification is on in Gmail before creating the app password
- Double-check `EMAIL_PASSWORD` has no spaces

**WhatsApp not arriving?**
- Make sure you sent the join code from your WhatsApp to Twilio's sandbox number
- The sandbox requires re-joining every 72 hours — join once before each test

**Google Sheets error?**
- Make sure the sheet is named exactly `Nifty50 Stock Screener`
- Make sure you shared the sheet with the service account email with Editor access

**GitHub Actions failing?**
- Click on the failed run → view logs — the error message is usually clear
- Most common issue: a secret name has a typo
