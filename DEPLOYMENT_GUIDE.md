# FIB-PRECISION F&O TRADING TERMINAL - COMPLETE DEPLOYMENT GUIDE

This document provides a step-by-step guide to deploying the **Fib-Precision Indian Stock Market Fibonacci Strategy Platform** to cloud hosting services (free and low-cost tiers), configuring persistent WebSocket market feeds, and verifying production operation.

---

## Architecture Overview & Free Hosting Evaluation

### Why Standard Serverless (e.g. Vercel) Cannot Run the Entire System
- **Serverless Limitation:** Platforms like Vercel or AWS Lambda run stateless functions that terminate after 10–30 seconds. They **cannot** maintain a continuous, persistent WebSocket connection to Angel One's `SmartWebSocketV2` (`wss://smartapisocket.angelone.in/smart-stream`) or execute the background market scanner loop.
- **Recommended Architecture:**
  - **Full-Stack PaaS (Best & Simplest):** Deploy the complete Flask + Socket.IO application on a platform supporting persistent processes (e.g., **Render**, **Railway**, **Fly.io**, or a cloud VPS). This serves both the frontend, the REST APIs, the Socket.IO stream, and the background Angel One WebSocket listener in one unified container.
  - **Database:** Local SQLite (`platform.db`) for lightweight single-instance setups, or **Supabase** / **Neon** for free managed PostgreSQL.

### Free & Low-Cost Hosting Provider Comparison

| Provider | Free Tier Availability | WebSocket Support | Background Worker Support | Sleep Behavior | Recommended Role |
|---|---|---|---|---|---|
| **Render** | Free Web Service (750 hrs/month) | Yes (Socket.IO + WSS) | Yes (In-app thread) | Spins down after 15 min of inactivity (wakes up in ~30s on request) | **Recommended for Free Full-Stack** |
| **Railway** | $5 free trial / $5/mo Hobby | Yes (Native WebSocket) | Yes (Continuous 24/7) | Does not sleep while credit remains | **Recommended for Production** |
| **Fly.io** | Free tier (up to 3 micro VMs) | Yes (Native TCP/WSS) | Yes | Auto-stop option (can be disabled) | Good container alternative |
| **Vercel** | Free Hobby | No persistent backend WS | No background workers | Ephemeral serverless functions only | Frontend static host only (requires separate backend) |
| **Supabase / Neon** | Generous Free PostgreSQL | N/A (Database) | N/A | Inactive pause after 7 days | **Recommended for PostgreSQL DB** |

---

## Production Environment Variables Reference

| Variable | Required? | Example Value | Description |
|---|---|---|---|
| `PORT` | Auto-set | `8080` (or host assigned) | Port the HTTP/WebSocket server listens on |
| `SECRET_KEY` | Recommended | `f7b8c9d0e1f2a3b4...` | Cryptographic secret for signing session tokens |
| `ANGEL_API_KEY` | Optional / UI | `MRx8rHZh` | SmartAPI App Key from smartapi.angelone.in |
| `ANGEL_CLIENT_ID` | Optional / UI | `AAAA492357` | Angel One Client Code / User ID |
| `ANGEL_PIN` | Optional / UI | `6405` | 4-digit Trading PIN |
| `ANGEL_TOTP_SECRET` | Optional / UI | `JBSWY3DPEHPK3PXP` | Google Authenticator Base32 secret for auto TOTP |
| `DATABASE_URL` | Optional | `postgresql://...` | PostgreSQL connection string (defaults to SQLite if unset) |
| `PROXIMITY_THRESHOLD_PCT` | Optional | `0.10` | Percentage threshold for Near-Entry/Near-Target alerts |
| `SCANNER_REFRESH_SECONDS` | Optional | `5` | Background scanner scan frequency in seconds |

---

## Step-by-Step Production Deployment Guide

### STEP 1: Prepare GitHub Repository
1. Navigate to [GitHub](https://github.com/) and sign in.
2. Click **New Repository** (`https://github.com/new`).
3. Name the repository: `stock-market-strategy` (set visibility to **Private** to protect personal configuration).
4. Do not initialize with README or license (you already have a complete repository).

### STEP 2: Push Complete Tested Project to GitHub
In your local project directory (`d:\StockMarketStrategy`), run:
```powershell
# Verify git status
git status

# Stage all files (excluding ignored data/ and config.json)
git add .

# Commit changes
git commit -m "Production release: Fibonacci Strategy Terminal with Angel One SmartAPI"

# Link to your new GitHub repository
git remote add origin https://github.com/YOUR_USERNAME/stock-market-strategy.git
git branch -M main
git push -u origin main
```

---

### STEP 3: Create Free PostgreSQL Database (Optional - Supabase / Neon)
*Note: If you prefer zero configuration, skip this step. The application automatically uses SQLite (`data/platform.db`).*

1. Go to [Supabase](https://supabase.com/) or [Neon](https://neon.tech/) and create a free account.
2. Click **New Project** and select region: **Asia (Mumbai)** or **Singapore** for lowest latency to NSE/BSE.
3. Save the database password securely.
4. Copy the **URI Connection String**:
   ```
   postgresql://postgres:[PASSWORD]@db.xxxx.supabase.co:5432/postgres
   ```

---

### STEP 4: Deploy on Render (Recommended Free Setup)

1. Go to [Render Dashboard](https://dashboard.render.com/) and sign in with GitHub.
2. Click **New +** in the top navigation bar and select **Web Service**.
3. Choose **Build and deploy from a Git repository** and connect your repository: `stock-market-strategy`.
4. Configure the Web Service settings:
   - **Name:** `fib-precision-terminal`
   - **Region:** `Singapore` (closest to Indian exchanges)
   - **Branch:** `main`
   - **Root Directory:** *(leave blank)*
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
   - **Instance Type:** `Free`
5. Scroll down to **Environment Variables** and click **Add Environment Variable**:
   - `PORT`: `8080`
   - `SECRET_KEY`: *(enter a random 32-character string)*
   - `ANGEL_CLIENT_ID`: `AAAA492357` (or your client code)
   - `ANGEL_API_KEY`: `MRx8rHZh`
   - `ANGEL_PIN`: `6405`
   - `ANGEL_TOTP_SECRET`: *(your Base32 authenticator secret for auto TOTP, if available)*
   - `DATABASE_URL`: *(your PostgreSQL URL from Step 3, if configured)*
6. Click **Deploy Web Service**.
7. Wait 2–3 minutes for the build to finish. Render will display:
   ```
   ==> Starting Fib-Precision server on port 8080...
   ==> [InstrumentManager] Loaded 218 F&O stocks and option chains from cache.
   ==> Your service is live at https://fib-precision-terminal.onrender.com
   ```

---

### STEP 5: Alternative Deployment on Railway (Hobby 24/7)

1. Go to [Railway](https://railway.app/) and sign in with GitHub.
2. Click **New Project** → **Deploy from GitHub repo** → select `stock-market-strategy`.
3. Railway automatically detects `Dockerfile` or `Procfile`.
4. Click **Variables** tab and enter:
   - `PORT`: `8080`
   - `ANGEL_CLIENT_ID`: `AAAA492357`
   - `ANGEL_API_KEY`: `MRx8rHZh`
   - `ANGEL_PIN`: `6405`
   - `ANGEL_TOTP_SECRET`: *(your secret)*
5. Click **Settings** tab → **Networking** → **Generate Domain** (e.g. `fib-terminal.up.railway.app`).
6. The app is immediately live with HTTPS and WebSocket support.

---

### STEP 6: Configure CORS and Domain Verification
The application already includes open CORS preflight headers in [`app.py`](file:///d:/StockMarketStrategy/app.py):
```python
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,bypass-tunnel-reminder'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response
```
No extra reverse proxy configuration is required.

---

### STEP 7: Test Production Authentication
1. Open your deployed URL on desktop or mobile: `https://your-app.onrender.com`
2. Check the top bar:
   - **Market Status:** Indicates `MARKET LIVE` during 09:15–15:30 IST or `MARKET CLOSED` outside trading hours.
   - **SmartAPI Status:** Click the red **SmartAPI Disconnected** pill.
3. In the popup modal:
   - Verify Client ID, API Key, and PIN.
   - Enter your current 6-digit TOTP from Google Authenticator (or save your Base32 secret for auto-generation).
   - Click **Connect SmartAPI Live Feed**.
4. The status pill will turn **Green (Connected)** and display your client code.

---

### STEP 8: Test Live Market Streams & Reconnection
1. **Interactive Candlestick Chart:** Select NIFTY 50 or RELIANCE. Switch timeframes (1m, 3m, 5m, 15m, 30m, 1h, 1D). Verify that all 6 strategy price levels (SL, Entry, T1, T2, T3, T4) are drawn as horizontal price lines with prices marked on the right axis.
2. **Option Chain:** Click any strike or CE/PE row in the Option Chain table. Verify that the chart switches immediately to that contract, recalculates option strategy levels, and plots them without refreshing the page.
3. **Automatic Market Scanner:** Verify opportunities update every 5 seconds. Filter by **Bullish Only** or **Near Entry**.
4. **WebSocket Reconnection:** Disable and re-enable your network connection (or toggle Airplane Mode on your phone). The Socket.IO client automatically reconnects and restores all active token subscriptions without page reload.

---

### STEP 9: Test Mobile Responsiveness
1. Open the deployed website on your smartphone (iPhone Safari / Android Chrome).
2. Test responsive tab navigation at the bottom:
   - 📈 **Chart:** Pinch/drag to pan and zoom. Verify the 6 strategy level price table displays beneath the chart with exact prices and P&L points/%.
   - ⛓️ **Chain:** Touch-friendly Call / Strike / Put rows with sticky center Strike column. Tap any CE or PE contract to immediately load its chart.
   - 📡 **Scanner:** Full card layout displaying Direction, Option Action, Underlying LTP, Entry, SL, Targets, and Distance.
   - ⚙️ **Login / Config:** Modal dialog adjusts smoothly without horizontal page overflow.

---

### STEP 10: Monitoring & Health Checks
- **Health Endpoint:** `GET https://your-app.onrender.com/health`
  Returns HTTP 200 with JSON payload:
  ```json
  {
    "status": "healthy",
    "service": "fib-precision-fno",
    "market_status": {
      "is_open": false,
      "status_code": "MARKET_CLOSED",
      "ist_time": "06-Nov-2026 22:45:00 IST"
    }
  }
  ```
- **Uptime Monitoring (Free):** Use [UptimeRobot](https://uptimerobot.com/) or [Cron-Job.org](https://cron-job.org/) to send an HTTP GET request to `/health` every 10 minutes. On Render's free tier, this prevents the free service from spinning down during market hours!

---

## Deployment Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| `AB1050: Invalid totp and client combination` | Time desynchronization or expired 30s TOTP | Enter your Base32 secret in the modal to enable automatic server-side TOTP calculation, or check your phone's clock synchronization in Google Authenticator settings. |
| Render Web Service spins down | 15 minutes of inactivity on free tier | Set up a free monitor at UptimeRobot pinging `/health` every 10 minutes from 09:00 to 15:30 IST. |
| Chart shows "Market Closed" | Time is outside 09:15–15:30 IST Monday–Friday | Normal behavior. The terminal displays the last valid closing prices and historical candles. Live trade ticks resume automatically when the market opens. |
| `WinError 10054` or WebSocket drop | Network glitch or Angel One session expired | The service automatically attempts reconnection with exponential backoff (15 retries). Click the SmartAPI status badge to refresh credentials if session has expired. |
