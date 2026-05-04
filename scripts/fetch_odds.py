import os
import requests
import logging

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = 'https://api.the-odds-api.com/v4'

MARKET_GROUPS = [
    ['h2h', 'spreads', 'totals'],
    ['team_totals'],
    ['h2h_h1', 'spreads_h1', 'totals_h1'],
]


def fetch_mlb_odds():
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


def _better_price(new_price, old_price):
    if old_price is None:
        return True
    return new_price > old_price


def _extract_best_total(bookmakers, market_key='totals'):
    best_over = None
    best_under = None
    for bk_data in bookmakers.values():
        for outcome in bk_data['markets'].get(market_key, []):
            name = outcome.get('name')
            point = outcome.get('point')
            price = outcome.get('price')
            if point is None or price is None:
                continue
            row = {'price': price, 'point': point, 'bookmaker': bk_data['title']}
            if name == 'Over' and _better_price(price, None if best_over is None else best_over['price']):
                best_over = row
            elif name == 'Under' and _better_price(price, None if best_under is None else best_under['price']):
                best_under = row
    result = {}
    if best_over:
        result['Over'] = best_over
    if best_under:
        result['Under'] = best_under
    return result


def _extract_best_team_totals(bookmakers):
    best = {}
    for bk_data in bookmakers.values():
        for outcome in bk_data['markets'].get('team_totals', []):
            team = outcome.get('name')
            side = outcome.get('description')
            point = outcome.get('point')
            price = outcome.get('price')
            if not team or not side or point is None or price is None:
                continue
            key = f'{team}|{side}'
            if key not in best or _better_price(price, best[key]['price']):
                best[key] = {
                    'team': team,
                    'side': side,
                    'price': price,
                    'point': point,
                    'bookmaker': bk_data['title'],
                }
    return best


def get_best_odds(games):
    processed = []
    for game in games:
        entry = {
            'home_team': game['home_team'],
            'away_team': game['away_team'],
            'commence_time': game['commence_time'],
            'odds': {},
        }
        bookmakers = game.get('bookmakers', {})

        for mkt_key in ['h2h', 'spreads', 'h2h_h1', 'spreads_h1']:
            best = {}
            for bk_data in bookmakers.values():
                for outcome in bk_data['markets'].get(mkt_key, []):
                    name = outcome.get('name')
                    price = outcome.get('price')
                    point = outcome.get('point')
                    if not name or price is None:
                        continue
                    if name not in best or _better_price(price, best[name]['price']):
                        best[name] = {'price': price, 'point': point, 'bookmaker': bk_data['title']}
            if best:
                entry['odds'][mkt_key] = best

        totals = _extract_best_total(bookmakers, 'totals')
        if totals:
            entry['odds']['totals'] = totals

        f5_totals = _extract_best_total(bookmakers, 'totals_h1')
        if f5_totals:
            entry['odds']['totals_h1'] = f5_totals

        team_totals = _extract_best_team_totals(bookmakers)
        if team_totals:
            entry['odds']['team_totals'] = team_totals

        processed.append(entry)
    return processed
