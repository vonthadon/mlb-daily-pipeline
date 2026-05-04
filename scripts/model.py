import requests
import logging
import numpy as np
from datetime import date

logger = logging.getLogger(__name__)
MLB_API = 'https://statsapi.mlb.com/api'

LEAGUE_AVG_ERA = 4.20
LEAGUE_AVG_RPG = 4.50
EDGE_THRESHOLD = 0.03
HIGH_EDGE = 0.06
RL_CONV = 0.72
F5_HFA = 0.025


# ── Helpers ───────────────────────────────────────────────────────────────────

def am_to_prob(odds):
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def remove_vig(p1, p2):
    t = p1 + p2
    return p1 / t, p2 / t


def kelly(prob, am_odds, fraction=0.25):
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
    denom = pa + pb - 2 * pa * pb
    if denom == 0:
        return 0.5
    return (pa - pa * pb) / denom


def _safe_float(val, fallback):
    try:
        return float(val)
    except (TypeError, ValueError):
        return fallback


# ── Data fetching ─────────────────────────────────────────────────────────────

def get_team_standings():
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
                gp = w + l or 1
                rs = tr.get('runsScored', 0) or 0
                ra = tr.get('runsAllowed', 0) or 0
                records[name] = {
                    'wins': w, 'losses': l,
                    'win_pct': _safe_float(tr.get('winningPercentage'), 0.5),
                    'pyth': pythagorean(rs, ra),
                    'run_diff': rs - ra,
                    'gp': gp,
                    'rs_per_g': rs / gp if rs else LEAGUE_AVG_RPG,
                    'ra_per_g': ra / gp if ra else LEAGUE_AVG_RPG,
                }
    except Exception as e:
        logger.error(f'Standings fetch error: {e}')
    return records


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def monte_carlo_game(home_rpg, away_rpg, home_pitcher_era, away_pitcher_era, n=100_000):
    """
    Simulate a game n times using Poisson run-scoring.
    Pitcher ERA adjusts each team's expected run total.
    Returns win%, projected total, over probabilities.
    """
    rng = np.random.default_rng(seed=42)

    # Pitcher quality multipliers: high ERA opponent = more runs scored
    home_lambda = float(np.clip(home_rpg * (away_pitcher_era / LEAGUE_AVG_ERA), 1.5, 12.0))
    away_lambda = float(np.clip(away_rpg * (home_pitcher_era / LEAGUE_AVG_ERA), 1.5, 12.0))

    home_runs = rng.poisson(home_lambda, n)
    away_runs = rng.poisson(away_lambda, n)

    # Extra innings for ties — home wins ~54% of extra-inning games
    ties = home_runs == away_runs
    extra_home = rng.random(n) < 0.54
    home_runs = home_runs.copy()
    away_runs = away_runs.copy()
    home_runs[ties & extra_home] += 1
    away_runs[ties & ~extra_home] += 1

    totals = home_runs + away_runs
    home_wins_mask = home_runs > away_runs

    over_probs = {}
    for line in [6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5]:
        over_probs[str(line)] = round(float(np.mean(totals > line)) * 100, 1)

    return {
        'home_win_pct': round(float(np.mean(home_wins_mask)) * 100, 1),
        'away_win_pct': round(float(np.mean(~home_wins_mask)) * 100, 1),
        'avg_total': round(float(np.mean(totals)), 2),
        'avg_home_runs': round(float(np.mean(home_runs)), 2),
        'avg_away_runs': round(float(np.mean(away_runs)), 2),
        'home_lambda': round(home_lambda, 2),
        'away_lambda': round(away_lambda, 2),
        'over_probs': over_probs,
        'simulations': n,
    }


# ── Model core ────────────────────────────────────────────────────────────────

def model_game(game, records):
    home = game.get('home_team', '')
    away = game.get('away_team', '')
    odds = game.get('odds', {})

    hr = records.get(home, {'pyth': 0.5, 'win_pct': 0.5, 'run_diff': 0, 'gp': 0, 'rs_per_g': LEAGUE_AVG_RPG, 'ra_per_g': LEAGUE_AVG_RPG})
    ar = records.get(away, {'pyth': 0.5, 'win_pct': 0.5, 'run_diff': 0, 'gp': 0, 'rs_per_g': LEAGUE_AVG_RPG, 'ra_per_g': LEAGUE_AVG_RPG})

    # Log5 base probability + home field
    home_p = min(0.92, max(0.08, log5(hr['pyth'], ar['pyth']) + 0.04))

    # ERA adjustments
    home_era = _safe_float(game.get('home_pitcher_stats', {}).get('era'), LEAGUE_AVG_ERA)
    away_era = _safe_float(game.get('away_pitcher_stats', {}).get('era'), LEAGUE_AVG_ERA)
    home_p = min(0.92, max(0.08, home_p + (away_era - home_era) * 0.03))
    away_p = 1 - home_p

    # Monte Carlo
    mc = monte_carlo_game(
        home_rpg=hr.get('rs_per_g', LEAGUE_AVG_RPG),
        away_rpg=ar.get('rs_per_g', LEAGUE_AVG_RPG),
        home_pitcher_era=home_era,
        away_pitcher_era=away_era,
    )

    # Blend model with Monte Carlo (60/40)
    blended_home = round(home_p * 0.60 + (mc['home_win_pct'] / 100) * 0.40, 4)
    blended_away = 1 - blended_home

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
    home_ml = (h2h.get(home) or {}).get('price')
    away_ml = (h2h.get(away) or {}).get('price')
    if home_ml:
        check_bet('ML', f'{home} ML', home_ml, blended_home)
    if away_ml:
        check_bet('ML', f'{away} ML', away_ml, blended_away)

    # Vegas implied (vig-removed)
    vegas_home_pct, vegas_away_pct = None, None
    if home_ml and away_ml:
        hi, ai = am_to_prob(home_ml), am_to_prob(away_ml)
        hnv, anv = remove_vig(hi, ai)
        vegas_home_pct = round(hnv * 100, 1)
        vegas_away_pct = round(anv * 100, 1)

    # Run Line
    hf5, af5 = blended_home, blended_away
    for name, d in odds.get('spreads', {}).items():
        adj = (blended_home if name == home else blended_away) * RL_CONV
        if adj > 0.50:
            check_bet('RL', f'{name} {d.get("point", "")}'.strip(), d.get('price'), adj)

    # F5 Moneyline
    f5 = odds.get('h2h_h1', {})
    if f5:
        hf5 = min(0.90, blended_home * 0.95 + F5_HFA)
        af5 = 1 - hf5
        check_bet('F5 ML', f'{home} F5 ML', (f5.get(home) or {}).get('price'), hf5)
        check_bet('F5 ML', f'{away} F5 ML', (f5.get(away) or {}).get('price'), af5)

    # F5 Run Line
    for name, d in odds.get('spreads_h1', {}).items():
        adj = (hf5 if name == home else af5) * RL_CONV
        if adj > 0.50:
            check_bet('F5 RL', f'{name} F5 {d.get("point", "")}'.strip(), d.get('price'), adj)

    # Game total — MC projected total vs Vegas line
    game_total_odds = odds.get('totals', {})
    vegas_total_line = None
    for k, v in game_total_odds.items():
        if v.get('point') is not None:
            vegas_total_line = v['point']
            break

    return {
        'home_win_pct': round(blended_home * 100, 1),
        'away_win_pct': round(blended_away * 100, 1),
        'home_record': f"{hr.get('wins', 0)}-{hr.get('losses', 0)}",
        'away_record': f"{ar.get('wins', 0)}-{ar.get('losses', 0)}",
        'vegas_home_pct': vegas_home_pct,
        'vegas_away_pct': vegas_away_pct,
        'vegas_total_line': vegas_total_line,
        'monte_carlo': mc,
        'value_bets': value_bets,
    }


def run_all_predictions(games, records):
    for game in games:
        game['predictions'] = model_game(game, records)
    return games
