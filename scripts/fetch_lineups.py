import requests
import logging
from datetime import date

logger = logging.getLogger(__name__)
MLB_API = 'https://statsapi.mlb.com/api'


def get_todays_games(target_date=None):
    """Fetch today's MLB schedule with probable pitchers and lineups."""
    day = target_date or date.today().strftime('%Y-%m-%d')
    url = f'{MLB_API}/v1/schedule'
    params = {
        'sportId': 1,
        'date': day,
        'hydrate': 'probablePitcher,lineups,team',
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f'Error fetching MLB schedule: {e}')
        return []

    games = []
    for date_data in data.get('dates', []):
        for g in date_data.get('games', []):
            info = {
                'game_pk': g['gamePk'],
                'game_date': g.get('gameDate', ''),
                'status': g.get('status', {}).get('detailedState', 'Scheduled'),
                'home_team': g['teams']['home']['team']['name'],
                'away_team': g['teams']['away']['team']['name'],
                'venue': g.get('venue', {}).get('name', 'Unknown'),
                'home_pitcher': 'TBD',
                'away_pitcher': 'TBD',
                'home_pitcher_id': None,
                'away_pitcher_id': None,
                'home_lineup': [],
                'away_lineup': [],
            }
            for side in ('home', 'away'):
                pp = g['teams'][side].get('probablePitcher', {})
                if pp:
                    info[f'{side}_pitcher'] = pp.get('fullName', 'TBD')
                    info[f'{side}_pitcher_id'] = pp.get('id')

            lineups = g.get('lineups', {})
            for side in ('home', 'away'):
                key = f'{side}Players'
                for p in lineups.get(key, []):
                    info[f'{side}_lineup'].append({
                        'name': p.get('person', {}).get('fullName', 'Unknown'),
                        'jersey': p.get('jerseyNumber', ''),
                        'order': p.get('batting', {}).get('battingOrder', 0),
                    })
                info[f'{side}_lineup'].sort(key=lambda x: x.get('order', 0))

            games.append(info)
    return games


def get_pitcher_stats(pitcher_id):
    """Fetch season pitching stats for a given player ID."""
    if not pitcher_id:
        return {}
    url = f'{MLB_API}/v1/people/{pitcher_id}/stats'
    params = {'stats': 'season', 'group': 'pitching', 'sportId': 1}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get('stats', [{}])[0].get('splits', [])
        if splits:
            s = splits[0].get('stat', {})
            return {
                'era': s.get('era', 'N/A'),
                'whip': s.get('whip', 'N/A'),
                'ip': s.get('inningsPitched', 'N/A'),
                'k': s.get('strikeOuts', 'N/A'),
                'bb': s.get('baseOnBalls', 'N/A'),
                'w': s.get('wins', 0),
                'l': s.get('losses', 0),
                'qs': s.get('qualityStarts', 'N/A'),
            }
    except Exception as e:
        logger.warning(f'Could not fetch pitcher stats for id {pitcher_id}: {e}')
    return {}
