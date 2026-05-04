import requests
import logging
from datetime import date

logger = logging.getLogger(__name__)
MLB_API = 'https://statsapi.mlb.com/api'


# ── Probability helpers ────────────────────────────────────────────────────────

def am_to_prob(odds):
    """American odds → raw implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def remove_vig(p1, p2):
    total = p1 + p2
    return p1 / total, p2 / total


def kelly(prob, am_odds, fraction=0.25):
    """Fractional Kelly bet size as a decimal of bankroll."""
    dec = (am_odds / 100 + 1) if am_odds > 0 else (100 / abs(am_odds) + 1)
    b = dec - 1
    raw = (b * prob - (1 - prob)) / b
    return max(0.0, raw * fraction)


def pythagorean(rs, ra, exp=1.83):
    if rs == 0 and ra == 0:
        return 0.5
    if ra == 0:
        return 1.0
    return (rs ** exp) / ((rs ** exp) + (ra ** exp))


def log5(pa, pb):
    """Log5 head-to-head probability for team A vs team B."""
    denom = pa + pb - 2 * pa * pb
    if denom == 0:
        return 0.5
    return (pa - pa * pb) / denom


# ── Data fetching ──────────────────────────────────────────────────────────────

def get_team_standings():
    """Return dict of team_name -> record dict."""
    url = f'{MLB_API}/v1/standings'
    params = {
        'leagueId': '103,104',
        'season': date.today().year,
        'standingsTypes': 'regularSeason',
        'hydrate': 'team,record',
    }
    records = {}
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        for div in resp.json().get('records', []):
            for tr in div.get('teamRecords', []):
                name = tr['team']['name']
                w, l = tr['wins'], tr['losses']
                rs = tr.get('runsScored', 0)
                ra = tr.get('runsAllowed', 0)
                records[name] = {
                    'wins': w, 'losses': l,
                    'win_pct': float(tr.get('winningPercentage', 0.5) or 0.5),
                    'pyth': pythagorean(rs, ra),
                    'run_diff': rs - ra,
                    'gp': w + l,
                }
    except Exception as e:
        logger.error(f'Standings fetch error: {e}')
    return records


# ── Model core ─────────────────────────────────────────────────────────────────

def _safe_era(stats, fallback=4.20):
    raw = stats.get('era', fallback)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


EDGE_THRESHOLD = 0.03   # minimum edge to flag a bet
HIGH_EDGE = 0.06        # threshold for HIGH confidence
RL_CONV = 0.72          # rough full-game -> run-line win prob conversion
F5_HFA = 0.025          # reduced home-field adjustment for F5


def model_game(game, records):
    home = game.get('home_team', '')
    away = game.get('away_team', '')
    odds = game.get('odds', {})

    hr = records.get(home, {'pyth': 0.5, 'win_pct': 0.5, 'run_diff': 0, 'gp': 0})
    ar = records.get(away, {'pyth': 0.5, 'win_pct': 0.5, 'run_diff': 0, 'gp': 0})

    # Base: Log5 on Pythagorean win %
    home_p = min(0.92, max(0.08, log5(hr['pyth'], ar['pyth']) + 0.04))

    # ERA adjustment
    home_era = _safe_era(game.get('home_pitcher_stats', {}))
    away_era = _safe_era(game.get('away_pitcher_stats', {}))
    era_adj = (away_era - home_era) * 0.03
    home_p = min(0.92, max(0.08, home_p + era_adj))
    away_p = 1 - home_p

    value_bets = []

    def check_bet(bet_type, pick_label, am_odds, model_prob):
        if not am_odds:
            return
        impl = am_to_prob(am_odds)
        edge = model_prob - impl
        if edge >= EDGE_THRESHOLD:
            value_bets.append({
                'type': bet_type,
                'pick': pick_label,
                'odds': am_odds,
                'model_prob_pct': round(model_prob * 100, 1),
                'implied_prob_pct': round(impl * 100, 1),
                'edge_pct': round(edge * 100, 1),
                'kelly_pct': round(kelly(model_prob, am_odds) * 100, 2),
                'confidence': 'HIGH' if edge >= HIGH_EDGE else 'MEDIUM',
            })

    # Moneyline
    h2h = odds.get('h2h', {})
    if h2h:
        home_ml = h2h.get(home, {}).get('price')
        away_ml = h2h.get(away, {}).get('price')
        if home_ml and away_ml:
            hi, ai = am_to_prob(home_ml), am_to_prob(away_ml)
            hnv, anv = remove_vig(hi, ai)
            check_bet('ML', f'{home} ML', home_ml, home_p)
            check_bet('ML', f'{away} ML', away_ml, away_p)

    # Run Line
    for name, d in odds.get('spreads', {}).items():
        adj = (home_p if name == home else away_p) * RL_CONV
        if adj > 0.50:
            check_bet('RL', f'{name} {d.get("point","")}'.strip(), d.get('price'), adj)

    # Game Total — no directional model, skip value check
    # (reported for info only via odds display)

    # Team Totals — informational
    # F5 Moneyline
    f5 = odds.get('h2h_h1', {})
    if f5:
        hf5 = min(0.90, home_p * 0.95 + F5_HFA)
        af5 = 1 - hf5
        check_bet('F5 ML', f'{home} F5 ML', f5.get(home, {}).get('price'), hf5)
        check_bet('F5 ML', f'{away} F5 ML', f5.get(away, {}).get('price'), af5)

    # F5 Run Line
    for name, d in odds.get('spreads_h1', {}).items():
        adj = (hf5 if 'hf5' in dir() and name == home else (af5 if 'af5' in dir() else 0.5)) * RL_CONV
        if adj > 0.50:
            check_bet('F5 RL', f'{name} F5 {d.get("point","")}'.strip(), d.get('price'), adj)

    return {
        'home_win_pct': round(home_p * 100, 1),
        'away_win_pct': round(away_p * 100, 1),
        'home_record': f"{hr.get('wins',0)}-{hr.get('losses',0)}",
        'away_record': f"{ar.get('wins',0)}-{ar.get('losses',0)}",
        'value_bets': value_bets,
    }


def run_all_predictions(games, records):
    for game in games:
        game['predictions'] = model_game(game, records)
    return games
