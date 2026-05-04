import requests
import logging
from datetime import date

logger = logging.getLogger(__name__)
MLB_API = 'https://statsapi.mlb.com/api'


def _name(p):
    """Extract player fullName from any MLB API player object shape."""
    if not isinstance(p, dict):
        return None
    return (
        p.get('fullName')
        or (p.get('person') or {}).get('fullName')
        or (p.get('name') or {}).get('fullName')
        or p.get('nameFirstLast')
    )


def _order(p):
    """Extract batting order from any MLB API player object shape."""
    if not isinstance(p, dict):
        return 0
    raw = (
        p.get('battingOrder')
        or (p.get('batting') or {}).get('battingOrder')
        or p.get('order')
        or 0
    )
    try:
        # battingOrder is sometimes '100', '200', etc (hundreds = slot)
        return int(str(raw)[0]) if raw else 0
    except (ValueError, IndexError):
        return 0


def _parse_lineup(player_list):
    result = []
    for p in player_list:
        nm = _name(p)
        if nm:   # skip entries with no name at all
            result.append({
                'name': nm,
                'jersey': p.get('jerseyNumber', '') if isinstance(p, dict) else '',
                'order': _order(p),
            })
    result.sort(key=lambda x: x['order'])
    return result


def _boxscore_lineup(game_pk):
    """Fallback: pull confirmed batting orders from the game boxscore."""
    try:
        resp = requests.get(f'{MLB_API}/v1/game/{game_pk}/boxscore', timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = {}
        for side in ('home', 'away'):
            team = data.get('teams', {}).get(side, {})
            order_ids = team.get('battingOrder', [])
            players = team.get('players', {})
            lineup = []
            for slot, pid in enumerate(order_ids, 1):
                pdata = players.get(f'ID{pid}', {})
                nm = _name(pdata) or _name(pdata.get('person', {}))
                if nm:
                    lineup.append({
                        'name': nm,
                        'jersey': pdata.get('jerseyNumber', ''),
                        'order': slot,
                    })
            result[f'{side}_lineup'] = lineup
        return result
    except Exception as e:
        logger.debug(f'Boxscore fallback failed for gamePk {game_pk}: {e}')
        return None


def get_todays_games(target_date=None):
    """Fetch today's MLB schedule with probable pitchers and lineups."""
    day = target_date or date.today().strftime('%Y-%m-%d')
    url = f'{MLB_API}/v1/schedule'
    params = {
        'sportId': 1,
        'date': day,
        'hydrate': 'probablePitcher,lineups,linescore,team',
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f'MLB schedule error: {e}')
        return []

    games = []
    for date_data in data.get('dates', []):
        for g in date_data.get('games', []):
            game_pk = g['gamePk']
            status = g.get('status', {}).get('detailedState', 'Scheduled')
            info = {
                'game_pk': game_pk,
                'game_date': g.get('gameDate', ''),
                'status': status,
                'home_team': g['teams']['home']['team']['name'],
                'away_team': g['teams']['away']['team']['name'],
                'venue': g.get('venue', {}).get('name', 'Unknown'),
                'home_pitcher': 'TBD', 'away_pitcher': 'TBD',
                'home_pitcher_id': None, 'away_pitcher_id': None,
                'home_lineup': [], 'away_lineup': [],
            }

            for side in ('home', 'away'):
                pp = g['teams'][side].get('probablePitcher') or {}
                if pp:
                    info[f'{side}_pitcher'] = pp.get('fullName', 'TBD')
                    info[f'{side}_pitcher_id'] = pp.get('id')

            # Parse schedule lineups first
            lineups = g.get('lineups') or {}
            home_raw = lineups.get('homePlayers') or []
            away_raw = lineups.get('awayPlayers') or []

            logger.debug(f'gamePk {game_pk} lineup sample home[0]={home_raw[0] if home_raw else "empty"}')

            info['home_lineup'] = _parse_lineup(home_raw)
            info['away_lineup'] = _parse_lineup(away_raw)

            # Fallback to boxscore if schedule lineups are empty or all-unknown
            if not info['home_lineup'] or not info['away_lineup']:
                bs = _boxscore_lineup(game_pk)
                if bs:
                    info['home_lineup'] = bs.get('home_lineup', info['home_lineup'])
                    info['away_lineup'] = bs.get('away_lineup', info['away_lineup'])

            games.append(info)
    return games


def get_pitcher_stats(pitcher_id):
    """Fetch season pitching stats for a given player ID."""
    if not pitcher_id:
        return {}
    try:
        resp = requests.get(
            f'{MLB_API}/v1/people/{pitcher_id}/stats',
            params={'stats': 'season', 'group': 'pitching', 'sportId': 1},
            timeout=15,
        )
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
        logger.warning(f'Pitcher stats error for id {pitcher_id}: {e}')
    return {}
