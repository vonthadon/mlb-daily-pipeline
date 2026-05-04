# ⚾ MLB Daily Betting Pipeline

Automated GitHub Actions pipeline that runs every day at **5:15 PM ET**, fetches the full MLB slate, pulls odds from The Odds API, gets lineups from the MLB Stats API, grabs real-time weather via Open-Meteo, runs a predictive model, and emails a full HTML report + ZIP of data files to your inbox.

## What's Included in Each Email

| File | Contents |
|------|----------|
| `full_report.html` | Styled HTML report — slate, lineups, weather, odds, model picks |
| `slate.csv` | Game-by-game slate with pitchers & records |
| `lineups.csv` | Batting orders for all teams |
| `weather.csv` | Game-time weather per stadium |
| `odds.csv` | Best available odds: ML, RL, Totals, Team Totals, F5 (all markets) |
| `value_bets.csv` | Final model picks with edge%, Kelly%, confidence |

## Markets Covered

- ✅ Moneyline (ML)
- ✅ Run Line (Spreads ±1.5)
- ✅ Game Totals (O/U)
- ✅ Team Totals
- ✅ F5 Innings — Moneyline, Run Line, Total

## Model Logic

1. **Pythagorean Win % ** — derived from runs scored/allowed (exponent 1.83)
2. **Log5 Head-to-Head** — team vs team probability
3. **Home Field Advantage** — +4% baseline
4. **ERA Adjustment** — starting pitcher ERA vs league average shifts probability ±3% per ERA point
5. **Edge Calculation** — model probability vs market implied probability (vig removed)
6. **Kelly Criterion** — fractional Kelly (25%) for bet sizing
7. **Confidence Tiers** — HIGH (edge ≥ 6%), MEDIUM (edge 3–6%)

## Setup — GitHub Secrets Required

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|--------|-------|
| `ODDS_API_KEY` | `8bd6c02f4fcb6699f65485eeb6adcd7c` |
| `EMAIL_ADDRESS` | Your Gmail address (e.g. `Vonthadon444@gmail.com`) |
| `EMAIL_PASSWORD` | Your Gmail **App Password** (see below) |

### Creating a Gmail App Password

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Enable **2-Step Verification** if not already on
3. Search for **App passwords** → Create one for "Mail"
4. Copy the 16-character password → paste as `EMAIL_PASSWORD` secret

## Manual Run

You can trigger the pipeline anytime from the **Actions** tab → **⚾ MLB Daily Betting Pipeline** → **Run workflow**.

Optionally pass a specific date (`YYYY-MM-DD`) to backfill a day.

## Schedule

The pipeline runs at `21:15 UTC` daily (5:15 PM ET during EDT). MLB lineups are typically confirmed by 3–4 PM ET, so this timing captures confirmed lineups for most games.

To change the time, edit `.github/workflows/mlb_pipeline.yml` and update the `cron` expression.

## APIs Used

| API | Cost | Key Required |
|-----|------|-------------|
| [The Odds API](https://the-odds-api.com) | Free tier (500 req/mo) | ✅ (yours is set) |
| [MLB Stats API](https://statsapi.mlb.com) | Free | ❌ |
| [Open-Meteo](https://open-meteo.com) | Free, unlimited | ❌ |
