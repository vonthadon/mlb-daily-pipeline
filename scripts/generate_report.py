import pandas as pd
from pathlib import Path
from datetime import datetime
from jinja2 import Template

EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body{font-family:'Segoe UI',Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:16px;}
  h1{color:#58a6ff;border-bottom:2px solid #21262d;padding-bottom:8px;font-size:1.4em;}
  h2{color:#f0883e;font-size:1.1em;margin:20px 0 8px;}
  p{color:#8b949e;font-size:0.85em;margin:4px 0;}
  table{width:100%;border-collapse:collapse;font-size:0.79em;margin-bottom:16px;}
  th{background:#21262d;color:#8b949e;padding:7px 8px;text-align:left;white-space:nowrap;}
  td{padding:6px 8px;border-bottom:1px solid #21262d;vertical-align:top;}
  .win{color:#3fb950;font-weight:bold;}
  .lose{color:#ff7b72;font-weight:bold;}
  .g-HIGH{background:rgba(63,185,80,0.12);}
  .g-MEDIUM{background:rgba(210,153,34,0.08);}
  .bH{background:#238636;color:#3fb950;padding:2px 7px;border-radius:10px;font-size:0.75em;font-weight:bold;}
  .bM{background:#9e6a03;color:#d29922;padding:2px 7px;border-radius:10px;font-size:0.75em;font-weight:bold;}
  .bML{background:#1f6feb;color:#79c0ff;padding:2px 6px;border-radius:8px;font-size:0.73em;}
  .bRL{background:#6e40c9;color:#d2a8ff;padding:2px 6px;border-radius:8px;font-size:0.73em;}
  .bF5{background:#da3633;color:#ffa198;padding:2px 6px;border-radius:8px;font-size:0.73em;}
  .picks{background:#0f2f14;border:2px solid #3fb950;border-radius:8px;padding:14px;margin-bottom:20px;}
  .picks h2{color:#3fb950;margin-top:0;}
  .slate{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;}
  .val{color:#3fb950;font-weight:bold;}
  .dim{color:#8b949e;font-size:0.78em;}
  .edge{color:#58a6ff;font-weight:bold;}
  .footer{text-align:center;color:#484f58;font-size:0.75em;margin-top:20px;border-top:1px solid #21262d;padding-top:10px;}
  .tag-mode{background:#1f6feb;color:#79c0ff;padding:3px 10px;border-radius:12px;font-size:0.78em;font-weight:bold;}
  .no-bets{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;color:#8b949e;font-style:italic;margin-bottom:20px;}
  .pregame-alert{background:#2d1f0f;border:2px solid #f0883e;border-radius:8px;padding:14px;margin-bottom:20px;}
  .pregame-alert h2{color:#f0883e;margin-top:0;}
</style>
</head>
<body>
<h1>&#9918; MLB {{ mode_label }} &nbsp;<span class="tag-mode">{{ mode_tag }}</span></h1>
<p>{{ date }} &nbsp;|&nbsp; Generated {{ generated_at }} ET &nbsp;|&nbsp; {{ total_games }} games &nbsp;|&nbsp; {{ total_bets }} value bets</p>
{% if mode == 'pregame' %}<div class="pregame-alert"><h2>&#128276; Pregame Alert &mdash; First Pitch in ~1 Hour</h2><p>Games starting soon highlighted below. Full detail in attached ZIP.</p></div>{% endif %}
{% if all_value_bets %}
<div class="picks"><h2>&#127919; Final Model Picks</h2>
<table><tr><th>Pick</th><th>Type</th><th>Book Odds</th><th>Model Fair</th><th>Model%</th><th>Vegas%</th><th>Edge%</th><th>Kelly%</th><th>Conf</th></tr>
{% for b in all_value_bets %}<tr class="g-{{ b.confidence }}"><td><strong>{{ b.pick }}</strong></td><td><span class="b{% if 'F5' in b.type %}F5{% elif 'RL' in b.type %}RL{% else %}ML{% endif %}">{{ b.type }}</span></td><td>{% if b.odds > 0 %}+{% endif %}{{ b.odds }}</td><td>{% if b.model_fair_odds > 0 %}+{% endif %}{{ b.model_fair_odds }}</td><td class="val">{{ b.model_prob_pct }}%</td><td class="dim">{{ b.implied_prob_pct }}%</td><td class="edge">+{{ b.edge_pct }}%</td><td>{{ b.kelly_pct }}%</td><td><span class="b{{ b.confidence[0] }}">{{ b.confidence }}</span></td></tr>
{% endfor %}</table></div>
{% else %}<div class="no-bets">No value bets above threshold today.</div>{% endif %}
<div class="slate">
<h2>&#128203; Full Slate</h2>
<table>
<tr><th>Time ET</th><th>Matchup</th><th>Pitchers</th><th>Weather</th><th>Books ML</th><th>Fair ML</th><th>Game Total</th><th>Projected Score</th><th>Team Totals</th><th>Why</th></tr>
{% for g in games %}
<tr{% if g.is_soon %} style="background:rgba(240,136,62,0.10);"{% endif %}>
  <td><strong>{{ g.game_time_et }}</strong>{% if g.is_soon %}<br><span style="color:#f0883e;font-size:0.72em;">&#128276; SOON</span>{% endif %}</td>
  <td>{{ g.matchup_color|safe }}</td>
  <td><span class="dim">{{ g.away_pitcher_disp }}<br>{{ g.home_pitcher_disp }}</span></td>
  <td class="dim">{{ g.weather_disp }}</td>
  <td>{{ g.ml_disp }}</td>
  <td>{{ g.fair_ml_disp }}</td>
  <td>{{ g.total_disp }}</td>
  <td>{{ g.score_disp|safe }}</td>
  <td>{{ g.team_totals_disp|safe }}</td>
  <td class="dim">{{ g.lean_disp }}</td>
</tr>
{% endfor %}
</table>
</div>
<div class="footer">&#128206; Full game cards, lineups, reasoning, MC breakdown &mdash; in attached ZIP<br>&#9888;&#65039; For informational use only. Gamble responsibly. &mdash; vonthadon/mlb-daily-pipeline</div>
</body></html>
"""

DETAIL_TEMPLATE = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><title>MLB Detail &mdash; {{ date }}</title><style>
body{font-family:'Segoe UI',Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px;}
h1{color:#58a6ff;border-bottom:2px solid #21262d;padding-bottom:10px;}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px;margin-bottom:22px;}
.matchup{font-size:1.3em;font-weight:bold;margin-bottom:4px;}
.meta{color:#8b949e;font-size:0.88em;margin-bottom:12px;}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
.box{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;}
.box h4{color:#58a6ff;margin:0 0 7px;font-size:0.82em;text-transform:uppercase;letter-spacing:1px;}
.box p,.box li{margin:3px 0;font-size:0.84em;}
.lineup span{display:block;padding:2px 0;border-bottom:1px solid #21262d;font-size:0.82em;}
.no-lineup{color:#8b949e;font-style:italic;font-size:0.83em;}
table{width:100%;border-collapse:collapse;font-size:0.84em;margin-top:8px;}
th{background:#21262d;color:#8b949e;padding:7px 9px;text-align:left;}
td{padding:6px 9px;border-bottom:1px solid #21262d;}
.win{color:#3fb950;font-weight:bold;}
.lose{color:#ff7b72;font-weight:bold;}
.reason-list{padding-left:18px;margin:6px 0 0;}
.reason-list li{margin-bottom:6px;}
.vbet{background:#0d1117;border:2px solid #238636;border-radius:7px;padding:12px;margin-top:10px;}
.mc-box{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;margin-top:10px;}
.mc-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;}
.mc-stat{text-align:center;}
.mc-stat .n{font-size:1.2em;font-weight:bold;}
.mc-stat .l{font-size:0.72em;color:#8b949e;}
.score-box{background:#0d1117;border:2px solid #30363d;border-radius:6px;padding:12px;margin:10px 0;display:flex;justify-content:space-around;text-align:center;}
.score-team .runs{font-size:2em;font-weight:bold;}
.score-team .label{font-size:0.78em;color:#8b949e;margin-top:2px;}
.score-vs{font-size:1.2em;color:#8b949e;align-self:center;}
footer{text-align:center;color:#484f58;margin-top:30px;font-size:0.78em;border-top:1px solid #21262d;padding-top:14px;}
</style></head><body>
<h1>&#9918; MLB Detail Report &mdash; {{ date }}</h1>
<p style="color:#8b949e">{{ total_games }} games &nbsp;|&nbsp; {{ total_bets }} value bets &nbsp;|&nbsp; Monte Carlo: {{ simulations }} sims/game</p>
{% for game in games %}
{% set p = game.predictions %}
{% set mc = p.monte_carlo if p else {} %}
<div class="card">
<div class="matchup">{{ game.matchup_color|safe }}</div>
<div class="meta">&#128336; {{ game.game_time_et }} &nbsp;|&nbsp; {{ game.weather.stadium if game.weather else game.venue }} &nbsp;|&nbsp; {{ game.status }}</div>
<div class="score-box">
  <div class="score-team">
    <div class="runs {{ 'win' if p and p.projected_winner == game.away_team else 'lose' }}">{{ p.projected_away_runs if p else '—' }}</div>
    <div class="label">{{ game.away_team }}<br><small>Book TT: {{ p.team_totals_market.away.line if p and p.team_totals_market and p.team_totals_market.away else '—' }}</small></div>
  </div>
  <div class="score-vs">vs</div>
  <div class="score-team">
    <div class="runs {{ 'win' if p and p.projected_winner == game.home_team else 'lose' }}">{{ p.projected_home_runs if p else '—' }}</div>
    <div class="label">{{ game.home_team }}<br><small>Book TT: {{ p.team_totals_market.home.line if p and p.team_totals_market and p.team_totals_market.home else '—' }}</small></div>
  </div>
  <div class="score-team">
    <div class="runs" style="color:#d2a8ff">{{ p.projected_total_runs if p else '—' }}</div>
    <div class="label">Total Runs<br><small>Book O/U: {{ p.vegas_total_line if p else '—' }}</small></div>
  </div>
</div>
<div class="grid3">
  <div class="box"><h4>Side Market</h4><p><strong>Books ML:</strong> {{ game.ml_disp }}</p><p><strong>Model Fair ML:</strong> {{ game.fair_ml_disp }}</p><p><strong>Books % (no-vig):</strong> {{ game.books_pct_disp }}</p><p><strong>Model %:</strong> {{ game.model_pct_disp }}</p></div>
  <div class="box"><h4>Pitcher ERA (raw &#8594; regressed)</h4>{% if p %}<p>&#9992;&#65039; {{ game.away_team.split()[-1] }}: {{ p.away_era_raw }} &#8594; {{ p.away_era_reg }} ({{ game.away_pitcher or 'TBD' }})</p><p>&#127968; {{ game.home_team.split()[-1] }}: {{ p.home_era_raw }} &#8594; {{ p.home_era_reg }} ({{ game.home_pitcher or 'TBD' }})</p><p class="dim" style="color:#8b949e">ERAs regressed toward 4.20 avg by IP.</p>{% endif %}</div>
  <div class="box"><h4>Weather &amp; Records</h4><p>{{ game.weather_disp }}</p>{% if p %}<p>{{ game.away_team.split()[-1] }}: <strong>{{ p.away_record }}</strong> &nbsp; {{ game.home_team.split()[-1] }}: <strong>{{ p.home_record }}</strong></p>{% endif %}</div>
</div>
{% if mc %}
<div class="mc-box"><h4 style="margin:0 0 8px;color:#d2a8ff;">&#127922; Monte Carlo ({{ mc.simulations }} sims)</h4>
<div class="mc-grid">
  <div class="mc-stat"><div class="n {{ 'win' if p and p.projected_winner == game.away_team else 'lose' }}">{{ mc.away_win_pct }}%</div><div class="l">{{ game.away_team.split()[-1] }} Win%</div></div>
  <div class="mc-stat"><div class="n {{ 'win' if p and p.projected_winner == game.home_team else 'lose' }}">{{ mc.home_win_pct }}%</div><div class="l">{{ game.home_team.split()[-1] }} Win%</div></div>
  <div class="mc-stat"><div class="n" style="color:#d2a8ff">{{ mc.avg_total }}</div><div class="l">Proj Total (Book: {{ p.vegas_total_line if p else '—' }})</div></div>
  <div class="mc-stat"><div class="n" style="color:#58a6ff">{{ mc.avg_away_runs }} / {{ mc.avg_home_runs }}</div><div class="l">Away / Home Runs</div></div>
</div>
<p style="margin-top:8px;font-size:0.78em;color:#8b949e">Over probs &mdash; 6.5: {{ mc.over_probs['6.5'] }}% &nbsp; 7.0: {{ mc.over_probs['7.0'] }}% &nbsp; 7.5: {{ mc.over_probs['7.5'] }}% &nbsp; 8.0: {{ mc.over_probs['8.0'] }}% &nbsp; 8.5: {{ mc.over_probs['8.5'] }}% &nbsp; 9.0: {{ mc.over_probs['9.0'] }}% &nbsp; 9.5: {{ mc.over_probs['9.5'] }}%</p>
</div>
{% endif %}
<div class="box" style="margin-top:12px;"><h4>Why the model leans this way</h4><ul class="reason-list">{% if p %}{% for reason in p.reasoning %}<li>{{ reason }}</li>{% endfor %}{% endif %}</ul></div>
<div class="grid2">
  <div class="box lineup"><h4>{{ game.away_team }} Lineup</h4>{% if game.away_lineup %}{% for pl in game.away_lineup %}<span>{{ loop.index }}. {{ pl.name }}</span>{% endfor %}{% else %}<p class="no-lineup">Not yet posted</p>{% endif %}</div>
  <div class="box lineup"><h4>{{ game.home_team }} Lineup</h4>{% if game.home_lineup %}{% for pl in game.home_lineup %}<span>{{ loop.index }}. {{ pl.name }}</span>{% endfor %}{% else %}<p class="no-lineup">Not yet posted</p>{% endif %}</div>
</div>
{% if p and p.value_bets %}
<div class="vbet"><h4 style="margin:0 0 8px;color:#3fb950;">&#9989; Value Bets</h4>
<table><tr><th>Pick</th><th>Type</th><th>Book Odds</th><th>Model Fair</th><th>Model%</th><th>Vegas%</th><th>Edge%</th><th>Kelly%</th><th>Conf</th></tr>
{% for b in p.value_bets %}<tr><td>{{ b.pick }}</td><td>{{ b.type }}</td><td>{% if b.odds > 0 %}+{% endif %}{{ b.odds }}</td><td>{% if b.model_fair_odds > 0 %}+{% endif %}{{ b.model_fair_odds }}</td><td style="color:#3fb950">{{ b.model_prob_pct }}%</td><td style="color:#8b949e">{{ b.implied_prob_pct }}%</td><td style="color:#58a6ff">+{{ b.edge_pct }}%</td><td>{{ b.kelly_pct }}%</td><td>{{ b.confidence }}</td></tr>
{% endfor %}</table></div>
{% endif %}
</div>
{% endfor %}
<footer>&#9888;&#65039; For informational use only. Gamble responsibly.<br>vonthadon/mlb-daily-pipeline</footer>
</body></html>
"""


def _fmt_et(iso_str):
    try:
        from datetime import timezone, timedelta
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        et = dt.astimezone(timezone(timedelta(hours=-4)))
        return et.strftime('%I:%M %p ET')
    except Exception:
        return iso_str


def _pfx(price):
    if price is None or price == '':
        return '-'
    return f'+{int(price)}' if price > 0 else str(int(price))


def _sp(pitcher, stats):
    nm = pitcher or 'TBD'
    era = (stats or {}).get('era', '')
    return f"{nm} ({era} ERA)" if era and era != 'N/A' else nm


def _prep_games(games, soon_game_pks=None):
    soon_game_pks = soon_game_pks or set()
    for g in games:
        g['game_time_et'] = _fmt_et(g.get('commence_time') or g.get('game_date', ''))
        g.setdefault('weather', None)
        g.setdefault('odds', {})
        g['is_soon'] = g.get('game_pk') in soon_game_pks
        p = g.get('predictions', {})
        mc = p.get('monte_carlo', {})
        away = g.get('away_team', '')
        home = g.get('home_team', '')
        away_win = float(p.get('away_win_pct', 0) or 0)
        home_win = float(p.get('home_win_pct', 0) or 0)
        away_cls = 'win' if away_win >= home_win else 'lose'
        home_cls = 'win' if home_win > away_win else 'lose'
        g['matchup_color'] = f"<span class='{away_cls}'>{away}</span> @ <span class='{home_cls}'>{home}</span>"
        w = g.get('weather') or {}
        if w.get('dome'):
            g['weather_disp'] = '&#127965;&#65039; Dome'
        elif w.get('temp_f'):
            g['weather_disp'] = f"&#127777;&#65039;{w['temp_f']}&#176;F {w.get('wind_mph','')}mph {w.get('wind_dir','')}"
        else:
            g['weather_disp'] = w.get('note', w.get('error', '&#8212;'))
        g['away_pitcher_disp'] = _sp(g.get('away_pitcher'), g.get('away_pitcher_stats'))
        g['home_pitcher_disp'] = _sp(g.get('home_pitcher'), g.get('home_pitcher_stats'))
        away_ml = p.get('vegas_away_odds')
        home_ml = p.get('vegas_home_odds')
        g['ml_disp'] = f"{_pfx(away_ml)} / {_pfx(home_ml)}"
        g['fair_ml_disp'] = f"{_pfx(p.get('model_away_fair_odds'))} / {_pfx(p.get('model_home_fair_odds'))}"
        g['books_pct_disp'] = f"{p.get('vegas_away_pct','-')}% / {p.get('vegas_home_pct','-')}%"
        g['model_pct_disp'] = f"{p.get('away_win_pct','-')}% / {p.get('home_win_pct','-')}%"
        vegas_total = p.get('vegas_total_line') or '&#8212;'
        proj_total = p.get('projected_total_runs', mc.get('avg_total', '&#8212;'))
        g['total_disp'] = f"Book {vegas_total} / Model {proj_total}"
        away_proj = p.get('projected_away_runs', '&#8212;')
        home_proj = p.get('projected_home_runs', '&#8212;')
        g['score_disp'] = (f"<span class='{away_cls}'>{away_proj}</span> "
                           f"<span style='color:#8b949e'>-</span> "
                           f"<span class='{home_cls}'>{home_proj}</span>")
        tt = p.get('team_totals_market', {})
        away_tt_line = (tt.get('away') or {}).get('line', '&#8212;')
        home_tt_line = (tt.get('home') or {}).get('line', '&#8212;')
        g['team_totals_disp'] = (f"<span class='{away_cls}'>{away.split()[-1]} {away_proj}</span> (bk {away_tt_line})<br>"
                                 f"<span class='{home_cls}'>{home.split()[-1]} {home_proj}</span> (bk {home_tt_line})")
        reasons = p.get('reasoning', [])
        g['lean_disp'] = reasons[0] if reasons else '&#8212;'
    return games


def generate_email_html(games, date_str, mode='morning', soon_game_pks=None):
    games = _prep_games(games, soon_game_pks)
    all_bets = sorted([b for g in games for b in g.get('predictions', {}).get('value_bets', [])],
                      key=lambda x: x.get('edge_pct', 0), reverse=True)
    mode_labels = {'morning': ('Morning Slate', 'MORNING'), 'pregame': ('Pregame Alert', 'PREGAME'), 'full': ('Daily Report', 'FULL')}
    label, tag = mode_labels.get(mode, ('Report', 'REPORT'))
    return Template(EMAIL_TEMPLATE).render(date=date_str, generated_at=datetime.now().strftime('%H:%M'),
                                           total_games=len(games), total_bets=len(all_bets),
                                           games=games, all_value_bets=all_bets,
                                           mode=mode, mode_label=label, mode_tag=tag)


def generate_detail_html(games, date_str):
    games = _prep_games(games)
    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    sims = 0
    if games:
        sims = (games[0].get('predictions') or {}).get('monte_carlo', {}).get('simulations', 0)
    return Template(DETAIL_TEMPLATE).render(date=date_str, total_games=len(games),
                                            total_bets=len(all_bets), games=games, simulations=sims)


def generate_csv_files(games, output_dir):
    output_dir = Path(output_dir)
    files = []

    def _write(path, rows):
        pd.DataFrame(rows).to_csv(path, index=False)
        files.append(path)

    slate_rows, weather_rows, odds_rows, lineup_rows, bet_rows, mc_rows, reason_rows = [], [], [], [], [], [], []
    mkt_labels = {'h2h': 'ML', 'spreads': 'RL', 'totals': 'Total', 'team_totals': 'Team Total',
                  'h2h_h1': 'F5 ML', 'spreads_h1': 'F5 RL', 'totals_h1': 'F5 Total'}

    for g in games:
        p = g.get('predictions', {})
        mc = p.get('monte_carlo', {})
        matchup = f"{g.get('away_team','')} @ {g.get('home_team','')}"
        w = g.get('weather') or {}
        tt = p.get('team_totals_market', {})
        slate_rows.append({
            'Time ET': g.get('game_time_et', ''), 'Matchup': matchup,
            'Projected Winner': p.get('projected_winner', ''), 'Projected Loser': p.get('projected_loser', ''),
            'Books Away ML': p.get('vegas_away_odds', ''), 'Books Home ML': p.get('vegas_home_odds', ''),
            'Model Away Fair ML': p.get('model_away_fair_odds', ''), 'Model Home Fair ML': p.get('model_home_fair_odds', ''),
            'Books Away %': p.get('vegas_away_pct', ''), 'Books Home %': p.get('vegas_home_pct', ''),
            'Model Away %': p.get('away_win_pct', ''), 'Model Home %': p.get('home_win_pct', ''),
            'Vegas Game Total': p.get('vegas_total_line', ''), 'Model Game Total': p.get('projected_total_runs', ''),
            'Away Proj Runs': p.get('projected_away_runs', ''), 'Home Proj Runs': p.get('projected_home_runs', ''),
            'Book Away Team Total': (tt.get('away') or {}).get('line', ''),
            'Book Home Team Total': (tt.get('home') or {}).get('line', ''),
        })
        if w:
            weather_rows.append({'Matchup': matchup, 'Stadium': w.get('stadium', ''), 'City': w.get('city', ''),
                                  'Dome': w.get('dome', False), 'Temp F': w.get('temp_f', 'N/A'),
                                  'Condition': w.get('condition', w.get('note', 'N/A')),
                                  'Wind mph': w.get('wind_mph', 'N/A'), 'Wind Dir': w.get('wind_dir', 'N/A'),
                                  'Precip %': w.get('precip_pct', 'N/A')})
        for mkt, outcomes in g.get('odds', {}).items():
            for team, data in outcomes.items():
                odds_rows.append({'Matchup': matchup, 'Market': mkt_labels.get(mkt, mkt), 'Side': team,
                                  'Line': data.get('point', ''), 'Odds': data.get('price', ''),
                                  'Book': data.get('bookmaker', '')})
        for side in ('away', 'home'):
            for i, player in enumerate(g.get(f'{side}_lineup', []), 1):
                lineup_rows.append({'Matchup': matchup, 'Team': g.get(f'{side}_team', ''), 'Order': i,
                                    'Player': player.get('name', ''), 'Jersey': player.get('jersey', '')})
        for b in p.get('value_bets', []):
            bet_rows.append({'Matchup': matchup, 'Pick': b['pick'], 'Type': b['type'],
                             'Book Odds': b['odds'], 'Model Fair Odds': b['model_fair_odds'],
                             'Model %': b['model_prob_pct'], 'Vegas %': b['implied_prob_pct'],
                             'Edge %': b['edge_pct'], 'Kelly %': b['kelly_pct'], 'Confidence': b['confidence']})
        if mc:
            op = mc.get('over_probs', {})
            mc_rows.append({'Matchup': matchup, 'Simulations': mc.get('simulations', 0),
                            'Away Win%': mc.get('away_win_pct', ''), 'Home Win%': mc.get('home_win_pct', ''),
                            'Away Lambda': mc.get('away_lambda', ''), 'Home Lambda': mc.get('home_lambda', ''),
                            'Proj Total': mc.get('avg_total', ''), 'Away Proj Runs': mc.get('avg_away_runs', ''),
                            'Home Proj Runs': mc.get('avg_home_runs', ''), 'Vegas Total': p.get('vegas_total_line', ''),
                            'O6.5%': op.get('6.5',''), 'O7.0%': op.get('7.0',''), 'O7.5%': op.get('7.5',''),
                            'O8.0%': op.get('8.0',''), 'O8.5%': op.get('8.5',''), 'O9.0%': op.get('9.0',''),
                            'O9.5%': op.get('9.5','')})
        for idx, reason in enumerate(p.get('reasoning', []), 1):
            reason_rows.append({'Matchup': matchup, 'Step': idx, 'Reason': reason})

    _write(output_dir / 'slate.csv', slate_rows)
    _write(output_dir / 'weather.csv', weather_rows)
    _write(output_dir / 'odds.csv', odds_rows)
    _write(output_dir / 'lineups.csv', lineup_rows)
    _write(output_dir / 'value_bets.csv', bet_rows)
    _write(output_dir / 'monte_carlo.csv', mc_rows)
    _write(output_dir / 'model_reasoning.csv', reason_rows)
    return files
