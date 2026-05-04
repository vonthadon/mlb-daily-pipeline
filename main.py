import os
import sys
import json
import zipfile
import logging
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.fetch_odds import fetch_mlb_odds, get_best_odds
from scripts.fetch_lineups import get_todays_games, get_pitcher_stats
from scripts.fetch_weather import get_game_weather
from scripts.model import get_team_standings, run_all_predictions
from scripts.generate_report import generate_html_report, generate_csv_files
from scripts.send_email import send_daily_email

OUTPUT_DIR = Path('output')


def normalize(name):
    """Lowercase last word of team name for fuzzy matching."""
    return name.lower().split()[-1] if name else ''


def merge_games(mlb_games, odds_games):
    """Merge MLB Stats API games with Odds API games by team name."""
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

    # Add odds-only games (e.g. doubleheaders listed under different IDs)
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


def main():
    target_date = (os.environ.get('TARGET_DATE') or '').strip() or date.today().strftime('%Y-%m-%d')
    logger.info(f'=== MLB Pipeline — {target_date} ===')
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1. Schedule + lineups
    logger.info('Fetching MLB schedule...')
    mlb_games = get_todays_games(target_date)
    logger.info(f'  {len(mlb_games)} games on schedule')

    # 2. Odds
    logger.info('Fetching odds...')
    raw_odds = fetch_mlb_odds()
    odds_games = get_best_odds(raw_odds)
    logger.info(f'  {len(odds_games)} games with odds')

    # 3. Merge
    games = merge_games(mlb_games, odds_games)
    logger.info(f'  {len(games)} total games after merge')

    # 4. Pitcher stats
    logger.info('Fetching pitcher stats...')
    for g in games:
        g['home_pitcher_stats'] = get_pitcher_stats(g.get('home_pitcher_id'))
        g['away_pitcher_stats'] = get_pitcher_stats(g.get('away_pitcher_id'))

    # 5. Weather
    logger.info('Fetching weather...')
    for g in games:
        g['weather'] = get_game_weather(
            g.get('home_team', ''),
            g.get('commence_time') or g.get('game_date', '')
        )

    # 6. Model
    logger.info('Running model...')
    records = get_team_standings()
    logger.info(f'  Loaded {len(records)} team records')
    games = run_all_predictions(games, records)

    # 7. Reports
    logger.info('Generating reports...')
    html = generate_html_report(games, target_date)
    csv_files = generate_csv_files(games, OUTPUT_DIR)
    html_path = OUTPUT_DIR / 'full_report.html'
    html_path.write_text(html, encoding='utf-8')
    (OUTPUT_DIR / 'raw_data.json').write_text(json.dumps(games, indent=2, default=str))

    # 8. ZIP
    zip_path = OUTPUT_DIR / f'mlb_report_{target_date}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(html_path, 'full_report.html')
        for f in csv_files:
            zf.write(f, f.name)
    logger.info(f'ZIP created: {zip_path}')

    # 9. Email
    from_email = os.environ.get('EMAIL_ADDRESS', '').strip()
    password = os.environ.get('EMAIL_PASSWORD', '').strip()
    if from_email and password:
        logger.info('Sending email...')
        try:
            send_daily_email(
                to_email='Vonthadon444@gmail.com',
                from_email=from_email,
                password=password,
                html_content=html,
                attachment_path=str(zip_path),
                date_str=target_date,
                predictions=games,
            )
            logger.info('Email sent!')
        except Exception as e:
            logger.error(f'Email failed: {e}')
    else:
        logger.warning('EMAIL_ADDRESS or EMAIL_PASSWORD not set — skipping email')

    # Summary
    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    logger.info(f'=== DONE — {len(games)} games, {len(all_bets)} value bets ===')
    for b in sorted(all_bets, key=lambda x: x.get('edge_pct', 0), reverse=True):
        pfx = '+' if b['odds'] > 0 else ''
        logger.info(f"  [{b['confidence']}] {b['pick']} @ {pfx}{b['odds']} | Edge +{b['edge_pct']}% | Kelly {b['kelly_pct']}%")


if __name__ == '__main__':
    main()
