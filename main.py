import os
import sys
import json
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
from scripts.send_email import send_daily_email, send_results_email
from scripts.results_checker import (
    save_picks, load_picks, grade_picks, all_games_final,
    generate_results_html, save_results_csv
)

OUTPUT_DIR = Path('output')
SENT_STATE = Path('sent_pregame.json')
ET = timezone(timedelta(hours=-4))


def normalize(name):
    return name.lower().split()[-1] if name else ''


def merge_games(mlb_games, odds_games):
    merged = list(mlb_games)
    odds_map = {}
    for og in odds_games:
        odds_map[(normalize(og['home_team']), normalize(og['away_team']))] = og
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
                'game_date': og.get('commence_time', ''),
                'status': 'Scheduled', 'venue': '',
                'home_pitcher': 'TBD', 'away_pitcher': 'TBD',
                'home_pitcher_id': None, 'away_pitcher_id': None,
                'home_lineup': [], 'away_lineup': [],
                'odds': og.get('odds', {}),
                'home_pitcher_stats': {}, 'away_pitcher_stats': {}
            })
    return merged


def load_sent_state():
    if SENT_STATE.exists():
        try:
            data = json.loads(SENT_STATE.read_text())
            return set(data.get(date.today().isoformat(), []))
        except Exception:
            pass
    return set()


def save_sent_state(sent_pks):
    today = date.today().isoformat()
    existing = {}
    if SENT_STATE.exists():
        try:
            existing = json.loads(SENT_STATE.read_text())
        except Exception:
            pass
    existing[today] = list(sent_pks)
    keys = sorted(existing.keys())[-2:]
    SENT_STATE.write_text(json.dumps({k: existing[k] for k in keys}))


def games_starting_soon(games, minutes_lo=60, minutes_hi=90):
    now_utc = datetime.now(timezone.utc)
    soon_pks, soon_games = [], []
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
    mode = (os.environ.get('RUN_MODE') or '').strip().lower()
    if mode in ('morning', 'pregame', 'results', 'full'):
        return mode
    now_et = datetime.now(ET)
    if now_et.hour == 10:
        return 'morning'
    # After 11 PM ET check if all games done -> results mode
    if now_et.hour >= 23 or now_et.hour < 6:
        return 'results'
    return 'pregame'


def build_pipeline(target_date):
    logger.info('Fetching MLB schedule...')
    mlb_games = get_todays_games(target_date)
    logger.info(f'  {len(mlb_games)} scheduled games')
    logger.info('Fetching odds...')
    raw_odds = fetch_mlb_odds()
    odds_games = get_best_odds(raw_odds)
    logger.info(f'  {len(odds_games)} games with odds')
    games = merge_games(mlb_games, odds_games)
    logger.info(f'  {len(games)} merged games')
    logger.info('Fetching pitcher stats + Savant advanced metrics...')
    for g in games:
        g['home_pitcher_stats'] = get_pitcher_stats(g.get('home_pitcher_id'), pitcher_name=g.get('home_pitcher'))
        g['away_pitcher_stats'] = get_pitcher_stats(g.get('away_pitcher_id'), pitcher_name=g.get('away_pitcher'))
    logger.info('Fetching weather...')
    for g in games:
        g['weather'] = get_game_weather(g.get('home_team', ''), g.get('commence_time') or g.get('game_date', ''))
    logger.info('Running model + Monte Carlo (25k sims)...')
    records = get_team_standings()
    logger.info(f'  {len(records)} team records loaded')
    return run_all_predictions(games, records)


def make_output(games, target_date):
    OUTPUT_DIR.mkdir(exist_ok=True)
    detail_html = generate_detail_html(games, target_date)
    detail_path = OUTPUT_DIR / 'full_report.html'
    detail_path.write_text(detail_html, encoding='utf-8')
    generate_csv_files(games, OUTPUT_DIR)
    (OUTPUT_DIR / 'raw_data.json').write_text(json.dumps(games, indent=2, default=str))
    return OUTPUT_DIR / f'mlb_report_{target_date}.csv'


def run_results_mode(target_date, from_email, password):
    logger.info(f'=== RESULTS MODE --- {target_date} ===')
    if not all_games_final(target_date):
        logger.info('Not all games finished yet --- skipping results email.')
        return
    picks = load_picks(target_date)
    if not picks:
        logger.info('No saved picks found for today --- nothing to grade.')
        return
    results = grade_picks(picks)
    wins = sum(1 for r in results if r['result'] == 'WIN')
    losses = sum(1 for r in results if r['result'] == 'LOSS')
    logger.info(f'Graded {len(results)} picks: {wins}W {losses}L')
    OUTPUT_DIR.mkdir(exist_ok=True)
    csv_path = OUTPUT_DIR / f'results_{target_date}.csv'
    save_results_csv(results, csv_path)
    html = generate_results_html(results, target_date)
    subject = (
        f"\ud83d\udccb MLB Results {target_date} \u2014 "
        f"{wins}W / {losses}L on {len(results)} model picks"
    )
    if from_email and password:
        send_results_email(
            to_email='Vonthadon444@gmail.com',
            from_email=from_email,
            password=password,
            html_content=html,
            csv_path=str(csv_path),
            date_str=target_date,
            subject_override=subject
        )
    else:
        logger.warning('No email credentials --- skipping results send')


def main():
    target_date = (os.environ.get('TARGET_DATE') or '').strip() or date.today().strftime('%Y-%m-%d')
    mode = detect_mode()
    OUTPUT_DIR.mkdir(exist_ok=True)
    logger.info(f'=== MLB Pipeline [{mode.upper()}] \u2014 {target_date} ===')
    from_email = os.environ.get('EMAIL_ADDRESS', '').strip()
    password = os.environ.get('EMAIL_PASSWORD', '').strip()

    if mode == 'results':
        run_results_mode(target_date, from_email, password)
        return

    games = build_pipeline(target_date)

    if mode == 'pregame':
        sent_pks = load_sent_state()
        soon_pks_all, _ = games_starting_soon(games, minutes_lo=60, minutes_hi=90)
        new_pks = [pk for pk in soon_pks_all if pk not in sent_pks]
        new_soon_games = [g for g in games if g.get('game_pk') in new_pks]
        if not new_soon_games:
            logger.info('No new pregame windows found \u2014 exiting.')
            return
        email_html = generate_email_html(games, target_date, mode='pregame', soon_game_pks=set(new_pks))
        csv_ref = make_output(games, target_date)
        save_picks(games, target_date)
        if from_email and password:
            send_daily_email(
                to_email='Vonthadon444@gmail.com', from_email=from_email,
                password=password, html_content=email_html,
                attachment_path=str(csv_ref), date_str=target_date,
                predictions=games,
                subject_override=(
                    f"\ud83d\udd14 PREGAME ALERT {target_date} \u2014 "
                    f"{len(new_pks)} game(s) in ~1hr"
                )
            )
            save_sent_state(sent_pks | set(new_pks))
        else:
            logger.warning('No email credentials \u2014 skipping send')
    else:
        email_html = generate_email_html(games, target_date, mode=mode)
        csv_ref = make_output(games, target_date)
        save_picks(games, target_date)
        if from_email and password:
            send_daily_email(
                to_email='Vonthadon444@gmail.com', from_email=from_email,
                password=password, html_content=email_html,
                attachment_path=str(csv_ref), date_str=target_date,
                predictions=games
            )
        else:
            logger.warning('No email credentials \u2014 skipping send')

    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    logger.info(f'=== DONE \u2014 {len(games)} games | {len(all_bets)} value bets ===')


if __name__ == '__main__':
    main()
