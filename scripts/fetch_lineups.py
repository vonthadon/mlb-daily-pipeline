import requests
import logging
from datetime import date
import pandas as pd
from io import StringIO

logger = logging.getLogger(__name__)
MLB_API = 'https://statsapi.mlb.com/api'
SAVANT_EXPECTED_CSV = 'https://baseballsavant.mlb.com/leaderboard/expected_statistics.csv?type=pitcher&year={year}&position=&team=&min=1'
SAVANT_CUSTOM_CSV = 'https://baseballsavant.mlb.com/leaderboard/custom.csv?year={year}&type=pitcher&filter=&min=1&selections=player_name,pitcher,pa,k_percent,bb_percent,whiff_percent,hard_hit_percent,barrel_batted_rate,xera,xwoba,woba,avg_best_speed,spin_rate,fastball_avg_speed&chart=false&x=player_name&y=player_name&r=no'
_savant_cache = {}


def _name(p):
    if not isinstance(p, dict):
        return None
    return p.get('fullName') or (p.get('person') or {}).get('fullName') or (p.get('name') or {}).get('fullName') or p.get('nameFirstLast')


def _order(p):
    if not isinstance(p, dict):
        return 0
    raw = p.get('battingOrder') or (p.get('batting') or {}).get('battingOrder') or p.get('order') or 0
    try:
        return int(str(raw)[0]) if raw else 0
    except (ValueError, IndexError):
        return 0


def _parse_lineup(player_list):
    result = []
    for p in player_list:
        nm = _name(p)
        if nm:
            result.append({'name': nm, 'jersey': p.get('jerseyNumber', '') if isinstance(p, dict) else '', 'order': _order(p)})
    result.sort(key=lambda x: x['order'])
    return result


def _boxscore_lineup(game_pk):
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
                    lineup.append({'name': nm, 'jersey': pdata.get('jerseyNumber', ''), 'order': slot})
            result[f'{side}_lineup'] = lineup
        return result
    except Exception as e:
        logger.debug(f'Boxscore fallback failed for gamePk {game_pk}: {e}')
        return None


def get_todays_games(target_date=None):
    day = target_date or date.today().strftime('%Y-%m-%d')
    url = f'{MLB_API}/v1/schedule'
    params = {'sportId': 1, 'date': day, 'hydrate': 'probablePitcher,lineups,linescore,team'}
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
            info = {'game_pk': game_pk, 'game_date': g.get('gameDate', ''), 'status': status, 'home_team': g['teams']['home']['team']['name'], 'away_team': g['teams']['away']['team']['name'], 'venue': g.get('venue', {}).get('name', 'Unknown'), 'home_pitcher': 'TBD', 'away_pitcher': 'TBD', 'home_pitcher_id': None, 'away_pitcher_id': None, 'home_lineup': [], 'away_lineup': []}
            for side in ('home', 'away'):
                pp = g['teams'][side].get('probablePitcher') or {}
                if pp:
                    info[f'{side}_pitcher'] = pp.get('fullName', 'TBD')
                    info[f'{side}_pitcher_id'] = pp.get('id')
            lineups = g.get('lineups') or {}
            info['home_lineup'] = _parse_lineup(lineups.get('homePlayers') or [])
            info['away_lineup'] = _parse_lineup(lineups.get('awayPlayers') or [])
            if not info['home_lineup'] or not info['away_lineup']:
                bs = _boxscore_lineup(game_pk)
                if bs:
                    info['home_lineup'] = bs.get('home_lineup', info['home_lineup'])
                    info['away_lineup'] = bs.get('away_lineup', info['away_lineup'])
            games.append(info)
    return games


def _normalize_name(name):
    return ''.join(ch.lower() for ch in str(name) if ch.isalnum() or ch.isspace()).strip()


def _load_savant_pitching(year):
    if year in _savant_cache:
        return _savant_cache[year]
    frames = []
    for url in [SAVANT_EXPECTED_CSV.format(year=year), SAVANT_CUSTOM_CSV.format(year=year)]:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text))
            frames.append(df)
        except Exception as e:
            logger.warning(f'Savant CSV fetch failed ({url}): {e}')
    if not frames:
        _savant_cache[year] = pd.DataFrame()
        return _savant_cache[year]
    base = frames[0]
    for df in frames[1:]:
        join_cols = [c for c in ['player_id', 'pitcher', 'player_name', 'last_name, first_name'] if c in base.columns and c in df.columns]
        if not join_cols:
            continue
        base = base.merge(df, on=join_cols, how='outer', suffixes=('', '_dup'))
        dup_cols = [c for c in base.columns if c.endswith('_dup')]
        if dup_cols:
            base = base.drop(columns=dup_cols)
    _savant_cache[year] = base
    return base


def _match_savant_row(df, pitcher_id=None, pitcher_name=None):
    if df.empty:
        return None
    if pitcher_id is not None:
        for key in ['player_id', 'pitcher']:
            if key in df.columns:
                matches = df[df[key].astype(str) == str(pitcher_id)]
                if not matches.empty:
                    return matches.iloc[0]
    if pitcher_name:
        target = _normalize_name(pitcher_name)
        for key in ['player_name', 'last_name, first_name']:
            if key in df.columns:
                norm = df[key].astype(str).map(_normalize_name)
                matches = df[norm == target]
                if not matches.empty:
                    return matches.iloc[0]
    return None


def get_pitcher_stats(pitcher_id, pitcher_name=None, season=None):
    if not pitcher_id and not pitcher_name:
        return {}
    stats = {}
    try:
        resp = requests.get(f'{MLB_API}/v1/people/{pitcher_id}/stats', params={'stats': 'season', 'group': 'pitching', 'sportId': 1}, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get('stats', [{}])[0].get('splits', [])
        if splits:
            s = splits[0].get('stat', {})
            stats.update({'era': s.get('era', 'N/A'), 'whip': s.get('whip', 'N/A'), 'ip': s.get('inningsPitched', 'N/A'), 'k': s.get('strikeOuts', 'N/A'), 'bb': s.get('baseOnBalls', 'N/A'), 'w': s.get('wins', 0), 'l': s.get('losses', 0), 'qs': s.get('qualityStarts', 'N/A')})
    except Exception as e:
        logger.warning(f'Pitcher stats error for id {pitcher_id}: {e}')
    year = season or date.today().year
    try:
        df = _load_savant_pitching(year)
        row = _match_savant_row(df, pitcher_id=pitcher_id, pitcher_name=pitcher_name)
        if row is not None:
            def val(*cols):
                for c in cols:
                    if c in row and pd.notna(row[c]):
                        return row[c]
                return 'N/A'
            stats.update({'xera': val('xera', 'xERA'), 'xwoba': val('xwoba', 'xwOBA'), 'k_pct': val('k_percent', 'k%'), 'bb_pct': val('bb_percent', 'bb%'), 'whiff_pct': val('whiff_percent', 'Whiff%'), 'hard_hit_pct': val('hard_hit_percent', 'Hard Hit%'), 'barrel_pct': val('barrel_batted_rate', 'Barrel%'), 'avg_ev': val('avg_best_speed', 'avg_ev'), 'fastball_velo': val('fastball_avg_speed', 'fastball_avg_speed'), 'spin_rate': val('spin_rate', 'avg_spin')})
    except Exception as e:
        logger.warning(f'Savant stats enrich failed for {pitcher_name or pitcher_id}: {e}')
    return stats
