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
MAX_WIN_PCT = 0.78
MIN_WIN_PCT = 0.22
ERA_REGRESSION_IP = 80.0
RUN_ENV_SHRINK = 0.35
MC_SIMULATIONS = 25_000


def am_to_prob(odds):
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def remove_vig(p1, p2):
    t = p1 + p2
    return p1 / t, p2 / t


def prob_to_american(prob):
    prob = min(max(prob, 0.001), 0.999)
    if prob >= 0.5:
        return int(round(-(prob / (1 - prob)) * 100))
    return int(round(((1 - prob) / prob) * 100))


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


def _safe_ip(val, fallback=0.0):
    try:
        return float(str(val).replace(',', '.'))
    except (TypeError, ValueError):
        return fallback


def regress_era(raw_era, innings_pitched):
    ip = max(0.0, innings_pitched)
    weight = min(ip / ERA_REGRESSION_IP, 1.0)
    return round(raw_era * weight + LEAGUE_AVG_ERA * (1 - weight), 2)


def advanced_pitching_score(stats):
    xera = _safe_float(stats.get('xera'), LEAGUE_AVG_ERA)
    whip = _safe_float(stats.get('whip'), 1.30)
    k_pct = _safe_float(stats.get('k_pct'), 22.0)
    bb_pct = _safe_float(stats.get('bb_pct'), 8.0)
    hard_hit = _safe_float(stats.get('hard_hit_pct'), 39.0)
    barrel = _safe_float(stats.get('barrel_pct'), 8.0)
    whiff = _safe_float(stats.get('whiff_pct'), 24.0)
    score = xera
    score += (whip - 1.30) * 0.60
    score += (bb_pct - 8.0) * 0.035
    score += (hard_hit - 39.0) * 0.018
    score += (barrel - 8.0) * 0.055
    score -= (k_pct - 22.0) * 0.030
    score -= (whiff - 24.0) * 0.015
    return float(np.clip(score, 2.7, 6.3))


def shrink_lambda(team_rpg, opp_pitch_metric):
    raw = team_rpg * (opp_pitch_metric / LEAGUE_AVG_ERA)
    shrunk = LEAGUE_AVG_RPG + (raw - LEAGUE_AVG_RPG) * (1 - RUN_ENV_SHRINK)
    return float(np.clip(shrunk, 2.8, 6.2))


def get_team_standings():
    url = f'{MLB_API}/v1/standings'
    params = {'leagueId': '103,104', 'season': date.today().year, 'standingsTypes': 'regularSeason', 'hydrate': 'team,record'}
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
                records[name] = {'wins': w, 'losses': l, 'win_pct': _safe_float(tr.get('winningPercentage'), 0.5), 'pyth': pythagorean(rs, ra), 'run_diff': rs - ra, 'gp': gp, 'rs_per_g': rs / gp if rs else LEAGUE_AVG_RPG, 'ra_per_g': ra / gp if ra else LEAGUE_AVG_RPG}
    except Exception as e:
        logger.error(f'Standings fetch error: {e}')
    return records


def monte_carlo_game(home_rpg, away_rpg, home_pitch_metric, away_pitch_metric, n=MC_SIMULATIONS):
    rng = np.random.default_rng()
    home_lambda = shrink_lambda(home_rpg, away_pitch_metric)
    away_lambda = shrink_lambda(away_rpg, home_pitch_metric)
    home_runs = rng.poisson(home_lambda, n)
    away_runs = rng.poisson(away_lambda, n)
    ties = home_runs == away_runs
    if ties.any():
        extra_home = rng.random(ties.sum()) < 0.54
        idx = np.where(ties)[0]
        home_runs[idx[extra_home]] += 1
        away_runs[idx[~extra_home]] += 1
    totals = home_runs + away_runs
    home_wins_mask = home_runs > away_runs
    over_probs = {}
    for line in [6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5]:
        over_probs[str(line)] = round(float(np.mean(totals > line)) * 100, 1)
    return {'home_win_pct': round(float(np.mean(home_wins_mask)) * 100, 1), 'away_win_pct': round(float(np.mean(~home_wins_mask)) * 100, 1), 'avg_total': round(float(np.mean(totals)), 2), 'avg_home_runs': round(float(np.mean(home_runs)), 2), 'avg_away_runs': round(float(np.mean(away_runs)), 2), 'home_lambda': round(home_lambda, 2), 'away_lambda': round(away_lambda, 2), 'over_probs': over_probs, 'simulations': n}


def build_reasoning(game, hr, ar, reg_home_era, reg_away_era, home_metric, away_metric, mc, home_p, blended_home, vegas_home_pct):
    reasons = []
    rd_diff = hr['run_diff'] - ar['run_diff']
    if abs(rd_diff) >= 25:
        leader = game['home_team'] if rd_diff > 0 else game['away_team']
        reasons.append(f"Run differential favors {leader} by {abs(rd_diff)} runs on the season.")
    elif abs(rd_diff) >= 10:
        leader = game['home_team'] if rd_diff > 0 else game['away_team']
        reasons.append(f"Moderate run-differential edge to {leader} ({hr['run_diff']} vs {ar['run_diff']}).")
    else:
        reasons.append('Season run differential is fairly close, so no major team-strength edge.')
    metric_gap = round(away_metric - home_metric, 2)
    if abs(metric_gap) >= 0.60:
        leader = game['home_team'] if metric_gap > 0 else game['away_team']
        reasons.append(f"Advanced starting-pitcher edge to {leader}; adjusted run-prevention gap is {abs(metric_gap):.2f}.")
    else:
        reasons.append('Advanced starter inputs are relatively close after regression and Statcast adjustments.')
    reasons.append(f"Projected team totals: {game['away_team']} {mc['avg_away_runs']:.2f} runs, {game['home_team']} {mc['avg_home_runs']:.2f} runs — game total {mc['avg_total']:.2f}.")
    if mc['avg_away_runs'] > mc['avg_home_runs']:
        reasons.append(f"{game['away_team']} projected to score more because its offense baseline and opponent pitching profile create a higher run expectation (lambda {mc['away_lambda']:.2f} vs {mc['home_lambda']:.2f}).")
    elif mc['avg_home_runs'] > mc['avg_away_runs']:
        reasons.append(f"{game['home_team']} projected to score more because its offense baseline and opponent pitching profile create a higher run expectation (lambda {mc['home_lambda']:.2f} vs {mc['away_lambda']:.2f}).")
    else:
        reasons.append('Both teams project into almost identical scoring environments.')
    reasons.append('Pitching inputs used include ERA, xERA, WHIP, K%, BB%, Whiff%, Hard-Hit%, and Barrel% when available.')
    if vegas_home_pct is not None:
        edge = round(blended_home * 100 - vegas_home_pct, 1)
        if abs(edge) >= 3:
            reasons.append(f"Model-market gap on the home side is {edge:+.1f}% after blending analytical and Monte Carlo outputs.")
        else:
            reasons.append('Model and market are mostly aligned on the side.')
    reasons.append(f"Final home win probability: base/log5 + team strength + advanced pitching adjustment, then blended 55/45 with Monte Carlo to {blended_home*100:.1f}%.")
    return reasons


def _extract_book_total(odds):
    totals = odds.get('totals', {}) or {}
    over = totals.get('Over') or totals.get('over') or {}
    under = totals.get('Under') or totals.get('under') or {}
    return over.get('point') if over.get('point') is not None else under.get('point')


def _extract_team_total(team_totals, team_name, side='Over'):
    for row in (team_totals or {}).values():
        if row.get('team') == team_name and str(row.get('side', '')).lower() == side.lower():
            return {'line': row.get('point'), 'odds': row.get('price'), 'bookmaker': row.get('bookmaker')}
    return {}


def model_game(game, records):
    home = game.get('home_team', '')
    away = game.get('away_team', '')
    odds = game.get('odds', {})
    hr = records.get(home, {'pyth': 0.5, 'win_pct': 0.5, 'run_diff': 0, 'gp': 0, 'rs_per_g': LEAGUE_AVG_RPG, 'ra_per_g': LEAGUE_AVG_RPG, 'wins': 0, 'losses': 0})
    ar = records.get(away, {'pyth': 0.5, 'win_pct': 0.5, 'run_diff': 0, 'gp': 0, 'rs_per_g': LEAGUE_AVG_RPG, 'ra_per_g': LEAGUE_AVG_RPG, 'wins': 0, 'losses': 0})
    base_home = min(0.70, max(0.30, log5(hr['pyth'], ar['pyth']) + 0.035))
    home_pitcher_stats = game.get('home_pitcher_stats', {}) or {}
    away_pitcher_stats = game.get('away_pitcher_stats', {}) or {}
    home_era_raw = _safe_float(home_pitcher_stats.get('era'), LEAGUE_AVG_ERA)
    away_era_raw = _safe_float(away_pitcher_stats.get('era'), LEAGUE_AVG_ERA)
    home_ip = _safe_ip(home_pitcher_stats.get('ip'), 0.0)
    away_ip = _safe_ip(away_pitcher_stats.get('ip'), 0.0)
    home_era_reg = regress_era(home_era_raw, home_ip)
    away_era_reg = regress_era(away_era_raw, away_ip)
    home_pitch_metric = advanced_pitching_score({**home_pitcher_stats, 'xera': home_pitcher_stats.get('xera', home_era_reg), 'era': home_era_reg})
    away_pitch_metric = advanced_pitching_score({**away_pitcher_stats, 'xera': away_pitcher_stats.get('xera', away_era_reg), 'era': away_era_reg})
    era_adj = float(np.clip((away_pitch_metric - home_pitch_metric) * 0.022, -0.10, 0.10))
    home_p = min(0.74, max(0.26, base_home + era_adj))
    mc = monte_carlo_game(hr.get('rs_per_g', LEAGUE_AVG_RPG), ar.get('rs_per_g', LEAGUE_AVG_RPG), home_pitch_metric, away_pitch_metric)
    blended_home = min(MAX_WIN_PCT, max(MIN_WIN_PCT, home_p * 0.55 + (mc['home_win_pct'] / 100) * 0.45))
    blended_away = 1 - blended_home
    projected_winner = home if blended_home >= blended_away else away
    projected_loser = away if projected_winner == home else home
    value_bets = []

    def check_bet(bet_type, pick_label, am_odds, model_prob, mc_prob=None):
        if not am_odds:
            return
        impl = am_to_prob(am_odds)
        edge = model_prob - impl
        if edge >= EDGE_THRESHOLD:
            value_bets.append({'type': bet_type, 'pick': pick_label, 'odds': am_odds, 'model_prob_pct': round(model_prob * 100, 1), 'implied_prob_pct': round(impl * 100, 1), 'model_fair_odds': prob_to_american(model_prob), 'edge_pct': round(edge * 100, 1), 'kelly_pct': round(kelly(model_prob, am_odds) * 100, 2), 'confidence': 'HIGH' if edge >= HIGH_EDGE else 'MEDIUM', 'mc_pct': round((mc_prob if mc_prob is not None else model_prob) * 100, 1)})

    h2h = odds.get('h2h', {})
    home_ml = (h2h.get(home) or {}).get('price')
    away_ml = (h2h.get(away) or {}).get('price')
    vegas_home_pct = vegas_away_pct = None
    if home_ml and away_ml:
        hi, ai = am_to_prob(home_ml), am_to_prob(away_ml)
        hnv, anv = remove_vig(hi, ai)
        vegas_home_pct = round(hnv * 100, 1)
        vegas_away_pct = round(anv * 100, 1)
    if home_ml:
        check_bet('ML', f'{home} ML', home_ml, blended_home, mc['home_win_pct'] / 100)
    if away_ml:
        check_bet('ML', f'{away} ML', away_ml, blended_away, mc['away_win_pct'] / 100)
    hf5, af5 = blended_home, blended_away
    for name, d in odds.get('spreads', {}).items():
        adj = min(0.70, max(0.30, (blended_home if name == home else blended_away) * RL_CONV))
        if adj > 0.50:
            check_bet('RL', f'{name} {d.get("point", "")}'.strip(), d.get('price'), adj)
    f5 = odds.get('h2h_h1', {})
    if f5:
        hf5 = min(0.74, max(0.26, blended_home * 0.97 + F5_HFA))
        af5 = 1 - hf5
        check_bet('F5 ML', f'{home} F5 ML', (f5.get(home) or {}).get('price'), hf5)
        check_bet('F5 ML', f'{away} F5 ML', (f5.get(away) or {}).get('price'), af5)
    for name, d in odds.get('spreads_h1', {}).items():
        adj = min(0.68, max(0.32, (hf5 if name == home else af5) * RL_CONV))
        if adj > 0.50:
            check_bet('F5 RL', f'{name} F5 {d.get("point", "")}'.strip(), d.get('price'), adj)
    vegas_total_line = _extract_book_total(odds)
    team_totals_market = odds.get('team_totals', {}) or {}
    team_totals = {'away': _extract_team_total(team_totals_market, away, 'Over'), 'home': _extract_team_total(team_totals_market, home, 'Over')}
    reasons = build_reasoning(game, hr, ar, home_era_reg, away_era_reg, home_pitch_metric, away_pitch_metric, mc, home_p, blended_home, vegas_home_pct)
    return {'home_win_pct': round(blended_home * 100, 1), 'away_win_pct': round(blended_away * 100, 1), 'home_record': f"{hr.get('wins',0)}-{hr.get('losses',0)}", 'away_record': f"{ar.get('wins',0)}-{ar.get('losses',0)}", 'vegas_home_pct': vegas_home_pct, 'vegas_away_pct': vegas_away_pct, 'vegas_total_line': vegas_total_line, 'vegas_home_odds': home_ml, 'vegas_away_odds': away_ml, 'model_home_fair_odds': prob_to_american(blended_home), 'model_away_fair_odds': prob_to_american(blended_away), 'home_era_raw': round(home_era_raw, 2), 'away_era_raw': round(away_era_raw, 2), 'home_era_reg': home_era_reg, 'away_era_reg': away_era_reg, 'home_pitch_metric': round(home_pitch_metric, 2), 'away_pitch_metric': round(away_pitch_metric, 2), 'projected_winner': projected_winner, 'projected_loser': projected_loser, 'projected_away_runs': mc['avg_away_runs'], 'projected_home_runs': mc['avg_home_runs'], 'projected_total_runs': mc['avg_total'], 'team_totals_market': team_totals, 'monte_carlo': mc, 'reasoning': reasons, 'value_bets': value_bets}


def run_all_predictions(games, records):
    for game in games:
        game['predictions'] = model_game(game, records)
    return games
