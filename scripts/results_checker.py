import requests
import json
import logging
import csv
from datetime import date, datetime, timezone
from pathlib import Path
from jinja2 import Template

logger = logging.getLogger(__name__)
MLB_API = 'https://statsapi.mlb.com/api'
PICKS_FILE = Path('saved_picks.json')

RESULTS_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body{font-family:'Segoe UI',Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:16px;}
h1{color:#58a6ff;border-bottom:2px solid #21262d;padding-bottom:8px;font-size:1.4em;}
p{color:#8b949e;font-size:0.85em;margin:4px 0;}
table{width:100%;border-collapse:collapse;font-size:0.82em;margin-top:12px;}
th{background:#21262d;color:#8b949e;padding:7px 9px;text-align:left;}
td{padding:6px 9px;border-bottom:1px solid #21262d;vertical-align:middle;}
.win{color:#3fb950;font-weight:bold;}
.loss{color:#ff7b72;font-weight:bold;}
.push{color:#d2a8ff;font-weight:bold;}
.pending{color:#8b949e;}
.bH{background:#238636;color:#3fb950;padding:2px 7px;border-radius:10px;font-size:0.75em;font-weight:bold;}
.bM{background:#9e6a03;color:#d29922;padding:2px 7px;border-radius:10px;font-size:0.75em;font-weight:bold;}
.scorecard{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;margin-bottom:18px;}
.stats-row{display:flex;gap:20px;margin:10px 0;}
.stat{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px 16px;text-align:center;}
.stat .n{font-size:1.5em;font-weight:bold;}
.stat .l{font-size:0.72em;color:#8b949e;margin-top:2px;}
.footer{text-align:center;color:#484f58;font-size:0.75em;margin-top:20px;border-top:1px solid #21262d;padding-top:10px;}
</style></head><body>
<h1>&#128203; MLB Model Results &#8212; {{ date }}</h1>
<p>All games finished &nbsp;|&nbsp; {{ total_picks }} picks graded &nbsp;|&nbsp; Generated {{ generated_at }} ET</p>

<div class="scorecard">
  <div class="stats-row">
    <div class="stat"><div class="n win">{{ wins }}</div><div class="l">Wins</div></div>
    <div class="stat"><div class="n loss">{{ losses }}</div><div class="l">Losses</div></div>
    <div class="stat"><div class="n push">{{ pushes }}</div><div class="l">Pushes</div></div>
    <div class="stat"><div class="n">{{ pending }}</div><div class="l">Pending</div></div>
    <div class="stat"><div class="n" style="color:#58a6ff">{{ win_pct }}%</div><div class="l">Win %</div></div>
    <div class="stat"><div class="n" style="color:{% if roi >= 0 %}#3fb950{% else %}#ff7b72{% endif %}">{% if roi >= 0 %}+{% endif %}{{ roi }}%</div><div class="l">Est. ROI</div></div>
  </div>
</div>

<table>
  <tr><th>Pick</th><th>Type</th><th>Odds</th><th>Edge%</th><th>Kelly%</th><th>Conf</th><th>Final Score</th><th>Result</th><th>Reason</th></tr>
  {% for r in results %}
  <tr>
    <td><strong>{{ r.pick }}</strong></td>
    <td>{{ r.type }}</td>
    <td>{% if r.odds > 0 %}+{% endif %}{{ r.odds }}</td>
    <td style="color:#58a6ff">+{{ r.edge_pct }}%</td>
    <td>{{ r.kelly_pct }}%</td>
    <td><span class="b{{ r.confidence[0] }}">{{ r.confidence }}</span></td>
    <td>{{ r.final_score }}</td>
    <td class="{{ r.result_class }}">{{ r.result_emoji }} {{ r.result_label }}</td>
    <td style="color:#8b949e;font-size:0.78em">{{ r.reason }}</td>
  </tr>
  {% endfor %}
</table>
<div class="footer">&#9888;&#65039; For informational use only. Gamble responsibly. &mdash; vonthadon/mlb-daily-pipeline</div>
</body></html>
"""


def save_picks(games, target_date):
    picks = []
    for g in games:
        matchup = f"{g.get('away_team','')} @ {g.get('home_team','')}"
        game_pk = g.get('game_pk')
        for b in g.get('predictions', {}).get('value_bets', []):
            picks.append({
                'date': target_date,
                'game_pk': game_pk,
                'matchup': matchup,
                'home_team': g.get('home_team', ''),
                'away_team': g.get('away_team', ''),
                'commence_time': g.get('commence_time', ''),
                **b
            })
    existing = []
    if PICKS_FILE.exists():
        try:
            existing = json.loads(PICKS_FILE.read_text())
        except Exception:
            pass
    # Keep only last 7 days
    keep_date = target_date
    merged = [p for p in existing if p.get('date') != keep_date] + picks
    PICKS_FILE.write_text(json.dumps(merged, indent=2, default=str))
    logger.info(f'Saved {len(picks)} picks to {PICKS_FILE}')
    return picks


def load_picks(target_date):
    if not PICKS_FILE.exists():
        return []
    try:
        all_picks = json.loads(PICKS_FILE.read_text())
        return [p for p in all_picks if p.get('date') == target_date]
    except Exception:
        return []


def get_game_result(game_pk):
    """Return (away_score, home_score, status) for a game."""
    try:
        resp = requests.get(f'{MLB_API}/v1/game/{game_pk}/linescore', timeout=15)
        resp.raise_for_status()
        data = resp.json()
        away = data.get('teams', {}).get('away', {}).get('runs')
        home = data.get('teams', {}).get('home', {}).get('runs')
        # Get status
        resp2 = requests.get(f'{MLB_API}/v1/game/{game_pk}/feed/live?fields=gameData,status', timeout=15)
        resp2.raise_for_status()
        status = resp2.json().get('gameData', {}).get('status', {}).get('detailedState', 'Unknown')
        return away, home, status
    except Exception as e:
        logger.warning(f'Could not fetch result for gamePk {game_pk}: {e}')
        return None, None, 'Unknown'


def all_games_final(target_date):
    """Return True if every game on the slate is Final or Completed."""
    url = f'{MLB_API}/v1/schedule'
    params = {'sportId': 1, 'date': target_date, 'hydrate': 'linescore'}
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        games = []
        for d in resp.json().get('dates', []):
            games.extend(d.get('games', []))
        if not games:
            return False
        return all(
            g.get('status', {}).get('detailedState', '') in
            ('Final', 'Completed', 'Game Over', 'Completed Early')
            for g in games
        )
    except Exception as e:
        logger.error(f'all_games_final check failed: {e}')
        return False


def _grade_ml(pick_name, away_score, home_score, away_team, home_team):
    if away_score is None or home_score is None:
        return 'PENDING', ''
    pick_team = pick_name.replace(' ML', '').strip()
    is_home = pick_team.lower() in home_team.lower()
    won = (is_home and home_score > away_score) or (not is_home and away_score > home_score)
    if away_score == home_score:
        return 'PUSH', f'{away_score}-{home_score} (tie)'
    return ('WIN' if won else 'LOSS'), f'{away_score}-{home_score}'


def _grade_rl(pick_name, away_score, home_score, away_team, home_team):
    if away_score is None or home_score is None:
        return 'PENDING', ''
    # parse spread from pick e.g. "Dodgers -1.5"
    parts = pick_name.rsplit(' ', 1)
    team_part = parts[0].strip()
    spread = 0.0
    if len(parts) == 2:
        try:
            spread = float(parts[1])
        except ValueError:
            pass
    is_home = team_part.lower() in home_team.lower()
    team_score = home_score if is_home else away_score
    opp_score = away_score if is_home else home_score
    covered = (team_score + spread) > opp_score
    push = (team_score + spread) == opp_score
    if push:
        return 'PUSH', f'{away_score}-{home_score} (push)'
    return ('WIN' if covered else 'LOSS'), f'{away_score}-{home_score}'


def _grade_f5_ml(pick_name, game_pk):
    try:
        resp = requests.get(f'{MLB_API}/v1/game/{game_pk}/linescore', timeout=15)
        resp.raise_for_status()
        data = resp.json()
        innings = data.get('innings', [])
        away_f5 = sum(inn.get('away', {}).get('runs', 0) or 0 for inn in innings[:5])
        home_f5 = sum(inn.get('home', {}).get('runs', 0) or 0 for inn in innings[:5])
        score_str = f'F5: {away_f5}-{home_f5}'
        # resolve pick team
        away_team = data.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
        home_team = data.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
        pick_team = pick_name.replace(' F5 ML', '').strip()
        is_home = pick_team.lower() in home_team.lower()
        if away_f5 == home_f5:
            return 'PUSH', score_str
        won = (is_home and home_f5 > away_f5) or (not is_home and away_f5 > home_f5)
        return ('WIN' if won else 'LOSS'), score_str
    except Exception as e:
        logger.warning(f'F5 grade failed for {game_pk}: {e}')
        return 'PENDING', ''


def _grade_f5_rl(pick_name, game_pk):
    try:
        resp = requests.get(f'{MLB_API}/v1/game/{game_pk}/linescore', timeout=15)
        resp.raise_for_status()
        data = resp.json()
        innings = data.get('innings', [])
        away_f5 = sum(inn.get('away', {}).get('runs', 0) or 0 for inn in innings[:5])
        home_f5 = sum(inn.get('home', {}).get('runs', 0) or 0 for inn in innings[:5])
        score_str = f'F5: {away_f5}-{home_f5}'
        away_team = data.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
        home_team = data.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
        parts = pick_name.replace(' F5', '').rsplit(' ', 1)
        team_part = parts[0].strip()
        spread = float(parts[1]) if len(parts) == 2 else 0.0
        is_home = team_part.lower() in home_team.lower()
        ts = home_f5 if is_home else away_f5
        os_ = away_f5 if is_home else home_f5
        if (ts + spread) == os_:
            return 'PUSH', score_str
        return ('WIN' if (ts + spread) > os_ else 'LOSS'), score_str
    except Exception as e:
        logger.warning(f'F5 RL grade failed: {e}')
        return 'PENDING', ''


def grade_picks(picks):
    results = []
    game_cache = {}
    for p in picks:
        game_pk = p.get('game_pk')
        if game_pk not in game_cache:
            away_s, home_s, status = get_game_result(game_pk)
            game_cache[game_pk] = (away_s, home_s, status,
                                   p.get('away_team', ''), p.get('home_team', ''))
        away_s, home_s, status, away_tm, home_tm = game_cache[game_pk]
        bet_type = p.get('type', '')
        pick_name = p.get('pick', '')
        result, final_score = 'PENDING', f'{away_s}-{home_s}' if away_s is not None else 'In Progress'
        if 'F5 ML' in bet_type:
            result, final_score = _grade_f5_ml(pick_name, game_pk)
        elif 'F5 RL' in bet_type:
            result, final_score = _grade_f5_rl(pick_name, game_pk)
        elif 'RL' in bet_type:
            result, final_score = _grade_rl(pick_name, away_s, home_s, away_tm, home_tm)
        else:
            result, final_score = _grade_ml(pick_name, away_s, home_s, away_tm, home_tm)
        emoji = {'WIN': '\u2705', 'LOSS': '\u274c', 'PUSH': '\ud83d\udd35', 'PENDING': '\u23f3'}
        cls = {'WIN': 'win', 'LOSS': 'loss', 'PUSH': 'push', 'PENDING': 'pending'}
        odds = p.get('odds', 0)
        reason = ''
        if result == 'WIN':
            reason = f"Model edge {p.get('edge_pct','')}% proved correct."
        elif result == 'LOSS':
            reason = f"Book line held; model edge {p.get('edge_pct','')}% was not enough."
        elif result == 'PUSH':
            reason = 'Line pushed — no result.'
        results.append({**p, 'final_score': final_score or '—', 'result': result,
                        'result_label': result, 'result_emoji': emoji.get(result, ''),
                        'result_class': cls.get(result, 'pending'), 'reason': reason})
    return results


def _calc_roi(results):
    total_units = 0.0
    net = 0.0
    for r in results:
        if r['result'] == 'PENDING':
            continue
        k = r.get('kelly_pct', 1.0) / 100
        total_units += k
        odds = r.get('odds', 0)
        if r['result'] == 'WIN':
            if odds > 0:
                net += k * (odds / 100)
            else:
                net += k * (100 / abs(odds))
        elif r['result'] == 'LOSS':
            net -= k
    return round((net / total_units * 100) if total_units else 0, 1)


def generate_results_html(results, date_str):
    wins = sum(1 for r in results if r['result'] == 'WIN')
    losses = sum(1 for r in results if r['result'] == 'LOSS')
    pushes = sum(1 for r in results if r['result'] == 'PUSH')
    pending = sum(1 for r in results if r['result'] == 'PENDING')
    graded = wins + losses
    win_pct = round(wins / graded * 100, 1) if graded else 0
    roi = _calc_roi(results)
    return Template(RESULTS_TEMPLATE).render(
        date=date_str, total_picks=len(results),
        wins=wins, losses=losses, pushes=pushes, pending=pending,
        win_pct=win_pct, roi=roi, results=results,
        generated_at=datetime.now().strftime('%H:%M')
    )


def save_results_csv(results, path):
    path = Path(path)
    fields = ['date', 'matchup', 'pick', 'type', 'odds', 'model_prob_pct', 'implied_prob_pct',
              'edge_pct', 'kelly_pct', 'confidence', 'final_score', 'result', 'reason']
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(results)
    return path
