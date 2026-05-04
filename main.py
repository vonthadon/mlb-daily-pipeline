import os
import sys
import json
import zipfile
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.fetch_odds import fetch_mlb_odds, get_best_odds
from scripts.fetch_lineups import get_todays_games, get_pitcher_stats
from scripts.fetch_weather import get_game_weather
from scripts.model import get_team_standings, run_all_predictions
from scripts.generate_report import generate_email_html, generate_detail_html, generate_csv_files
from scripts.send_email import send_daily_email

OUTPUT_DIR = Path('output')
SENT_STATE = Path('sent_pregame.json')
ET = timezone(timedelta(hours=-4))   # EDT offset


def normalize(name):
    return name.lower().split()[-1] if name else ''


def merge_games(mlb_games, odds_games):
    merged = list(mlb_games)
    odds_map = {}
    for og in odds_games:
        key = (normalize(og['home_team']), normalize(og['away_team']))
        odds_map[key] = og

    for mg in merged:
        h, a = normalize(mg['home_team']), normalize(mg['away_team'])
        match = odds_map.get((h, a)) or odds_map.get((a, h))
        if match:
            mg['odds'] = match.get('odds', {})
            mg['commence_time'] = match.get('commence_time', mg.get('game_date', ''))
            mg['home_team'] = match['home_team']
            mg['away_team'] = match['away_team']
        else:
            mg.setdefault('odds', {})
            mg.setdefault('commence_time', mg.get('game_date', ''))

    covered = {(normalize(g['home_team']), normalize(g['away_team'])) for g in merged}
    for og in odds_games:
        k = (normalize(og['home_team']), normalize(og['away_team']))
        if k not in covered:
            merged.append({
                'home_team': og['home_team'], 'away_team': og['away_team'],
                'commence_time': og.get('commence_time', ''),
                'game_date': og.get('commence_time', ''), 'status': 'Scheduled',
                'venue': '', 'home_pitcher': 'TBD', 'away_pitcher': 'TBD',
                'home_pitcher_id': None, 'away_pitcher_id': None,
                'home_lineup': [], 'away_lineup': [], 'odds': og.get('odds', {}),
                'home_pitcher_stats': {}, 'away_pitcher_stats': {},
            })
    return merged


def load_sent_state():
    """Load already-sent pregame game PKs for today."""
    if SENT_STATE.exists():
        try:
            data = json.loads(SENT_STATE.read_text())
            today = date.today().isoformat()
            return set(data.get(today, []))
        except Exception:
            pass
    return set()


def save_sent_state(sent_pks):
    """Persist sent pregame game PKs."""
    today = date.today().isoformat()
    existing = {}
    if SENT_STATE.exists():
        try:
            existing = json.loads(SENT_STATE.read_text())
        except Exception:
            pass
    existing[today] = list(sent_pks)
    # Prune old dates (keep only last 2 days)
    keys = sorted(existing.keys())[-2:]
    SENT_STATE.write_text(json.dumps({k: existing[k] for k in keys}))


def games_starting_soon(games, minutes_lo=60, minutes_hi=90):
    """Return (game_pk list, filtered_games) for games starting in [lo, hi] min."""
    now_utc = datetime.now(timezone.utc)
    soon_pks = []
    soon_games = []
    for g in games:
        ct = g.get('commence_time') or g.get('game_date', '')
        try:
            start = datetime.fromisoformat(ct.replace('Z', '+00:00'))
            mins_away = (start - now_utc).total_seconds() / 60
            if minutes_lo <= mins_away <= minutes_hi:
                soon_pks.append(g.get('game_pk'))
                soon_games.append(g)
        except Exception:
            pass
    return soon_pks, soon_games


def detect_mode():
    """Determine run mode from env var or current UTC hour."""
    mode = (os.environ.get('RUN_MODE') or '').strip().lower()
    if mode in ('morning', 'pregame', 'full'):
        return mode
    # Auto-detect: morning if UTC hour == 14 (10 AM ET), else pregame
    now_et_hour = datetime.now(ET).hour
    return 'morning' if now_et_hour == 10 else 'pregame'


def build_pipeline(target_date):
    """Fetch all data and run model. Returns enriched games list."""
    logger.info('Fetching MLB schedule...')
    mlb_games = get_todays_games(target_date)
    logger.info(f'  {len(mlb_games)} scheduled games')

    logger.info('Fetching odds...')
    raw_odds = fetch_mlb_odds()
    odds_games = get_best_odds(raw_odds)
    logger.info(f'  {len(odds_games)} games with odds')

    games = merge_games(mlb_games, odds_games)
    logger.info(f'  {len(games)} merged games')

    logger.info('Fetching pitcher stats...')
    for g in games:
        g['home_pitcher_stats'] = get_pitcher_stats(g.get('home_pitcher_id'))
        g['away_pitcher_stats'] = get_pitcher_stats(g.get('away_pitcher_id'))

    logger.info('Fetching weather...')
    for g in games:
        g['weather'] = get_game_weather(
            g.get('home_team', ''),
            g.get('commence_time') or g.get('game_date', '')
        )

    logger.info('Running model + Monte Carlo (100k sims)...')
    records = get_team_standings()
    logger.info(f'  {len(records)} team records loaded')
    games = run_all_predictions(games, records)
    return games


def make_zip(games, target_date, detail_html):
    OUTPUT_DIR.mkdir(exist_ok=True)
    detail_path = OUTPUT_DIR / 'full_report.html'
    detail_path.write_text(detail_html, encoding='utf-8')
    csv_files = generate_csv_files(games, OUTPUT_DIR)
    (OUTPUT_DIR / 'raw_data.json').write_text(json.dumps(games, indent=2, default=str))

    zip_path = OUTPUT_DIR / f'mlb_report_{target_date}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(detail_path, 'full_report.html')
        for f in csv_files:
            zf.write(f, f.name)
    return zip_path


def send(games, email_html, zip_path, target_date, mode, from_email, password, soon_pks=None):
    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    high = [b for b in all_bets if b.get('confidence') == 'HIGH']
    label = {'morning': '☀️ MORNING SLATE', 'pregame': '🔔 PREGAME ALERT', 'full': '⚾ DAILY REPORT'}.get(mode, 'REPORT')
    subject = f"{label} {target_date} — {len(games)} Games | {len(all_bets)} Bets ({len(high)} HIGH)"
    if mode == 'pregame' and soon_pks:
        subject = f"🔔 PREGAME ALERT {target_date} — {len(soon_pks)} game(s) in ~1hr | {len(all_bets)} bets"
    send_daily_email(
        to_email='Vonthadon444@gmail.com',
        from_email=from_email,
        password=password,
        html_content=email_html,
        attachment_path=str(zip_path),
        date_str=target_date,
        predictions=games,
        subject_override=subject,
    )


def main():
    target_date = (os.environ.get('TARGET_DATE') or '').strip() or date.today().strftime('%Y-%m-%d')
    mode = detect_mode()
    OUTPUT_DIR.mkdir(exist_ok=True)
    logger.info(f'=== MLB Pipeline [{mode.upper()}] — {target_date} ===')

    from_email = os.environ.get('EMAIL_ADDRESS', '').strip()
    password = os.environ.get('EMAIL_PASSWORD', '').strip()

    games = build_pipeline(target_date)

    if mode == 'pregame':
        sent_pks = load_sent_state()
        soon_pks_all, soon_games = games_starting_soon(games, minutes_lo=60, minutes_hi=90)
        # Filter to games NOT yet emailed
        new_pks = [pk for pk in soon_pks_all if pk not in sent_pks]
        new_soon_games = [g for g in soon_games if g.get('game_pk') in new_pks]

        if not new_soon_games:
            logger.info('No new pregame windows found — exiting.')
            return

        logger.info(f'{len(new_soon_games)} game(s) entering 1-hour window: {[g["home_team"] for g in new_soon_games]}')

        email_html = generate_email_html(games, target_date, mode='pregame', soon_game_pks=set(new_pks))
        detail_html = generate_detail_html(games, target_date)
        zip_path = make_zip(games, target_date, detail_html)

        if from_email and password:
            send(games, email_html, zip_path, target_date, mode, from_email, password, new_pks)
            logger.info('Pregame email sent!')
            updated = sent_pks | set(new_pks)
            save_sent_state(updated)
        else:
            logger.warning('No email credentials — skipping send')

    else:
        # Morning / full mode — send for all games
        email_html = generate_email_html(games, target_date, mode=mode)
        detail_html = generate_detail_html(games, target_date)
        zip_path = make_zip(games, target_date, detail_html)

        if from_email and password:
            send(games, email_html, zip_path, target_date, mode, from_email, password)
            logger.info('Email sent!')
        else:
            logger.warning('No email credentials — skipping send')

    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    logger.info(f'=== DONE — {len(games)} games | {len(all_bets)} value bets ===')
    for b in sorted(all_bets, key=lambda x: x.get('edge_pct', 0), reverse=True):
        pfx = '+' if b['odds'] > 0 else ''
        logger.info(f"  [{b['confidence']}] {b['pick']} @ {pfx}{b['odds']} | Edge +{b['edge_pct']}% | Kelly {b['kelly_pct']}%")


if __name__ == '__main__':
    main()
