import os
import requests
import logging

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = 'https://api.the-odds-api.com/v4'

# Markets to fetch grouped to minimize API calls
MARKET_GROUPS = [
    ['h2h', 'spreads', 'totals'],
    ['team_totals'],
    ['h2h_h1', 'spreads_h1', 'totals_h1'],
]

MARKET_LABELS = {
    'h2h': 'Moneyline',
    'spreads': 'Run Line',
    'totals': 'Game Total',
    'team_totals': 'Team Totals',
    'h2h_h1': 'F5 Moneyline',
    'spreads_h1': 'F5 Run Line',
    'totals_h1': 'F5 Total',
}


def fetch_mlb_odds():
    """Fetch all MLB odds across all required markets."""
    if not ODDS_API_KEY:
        logger.warning('ODDS_API_KEY not set — skipping odds fetch')
        return []

    games = {}
    url = f'{BASE_URL}/sports/baseball_mlb/odds/'

    for markets in MARKET_GROUPS:
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': ','.join(markets),
            'oddsFormat': 'american',
            'dateFormat': 'iso',
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            remaining = resp.headers.get('x-requests-remaining', 'unknown')
            logger.info(f'Odds API requests remaining: {remaining}')
            for game in resp.json():
                gid = game['id']
                if gid not in games:
                    games[gid] = {
                        'id': gid,
                        'commence_time': game['commence_time'],
                        'home_team': game['home_team'],
                        'away_team': game['away_team'],
                        'bookmakers': {},
                    }
                for bm in game.get('bookmakers', []):
                    bk = bm['key']
                    if bk not in games[gid]['bookmakers']:
                        games[gid]['bookmakers'][bk] = {'title': bm['title'], 'markets': {}}
                    for mkt in bm.get('markets', []):
                        games[gid]['bookmakers'][bk]['markets'][mkt['key']] = mkt.get('outcomes', [])
        except Exception as e:
            logger.error(f'Error fetching markets {markets}: {e}')

    return list(games.values())


def get_best_odds(games):
    """Extract best available lines across all bookmakers for each market."""
    processed = []
    for game in games:
        entry = {
            'home_team': game['home_team'],
            'away_team': game['away_team'],
            'commence_time': game['commence_time'],
            'odds': {},
        }
        bookmakers = game.get('bookmakers', {})
        for mkt_key in ['h2h', 'spreads', 'totals', 'team_totals', 'h2h_h1', 'spreads_h1', 'totals_h1']:
            best = {}
            for bk_data in bookmakers.values():
                for outcome in bk_data['markets'].get(mkt_key, []):
                    name = outcome['name']
                    price = outcome.get('price', 0)
                    point = outcome.get('point')
                    if name not in best or price > best[name]['price']:
                        best[name] = {'price': price, 'point': point, 'bookmaker': bk_data['title']}
            if best:
                entry['odds'][mkt_key] = best
        processed.append(entry)
    return processed
