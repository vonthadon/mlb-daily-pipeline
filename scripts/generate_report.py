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
  table{width:100%;border-collapse:collapse;font-size:0.8em;margin-bottom:16px;}
  th{background:#21262d;color:#8b949e;padding:7px 8px;text-align:left;white-space:nowrap;}
  td{padding:6px 8px;border-bottom:1px solid #21262d;vertical-align:top;}
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
  .dim{color:#8b949e;}
  .edge{color:#58a6ff;font-weight:bold;}
  .footer{text-align:center;color:#484f58;font-size:0.75em;margin-top:20px;border-top:1px solid #21262d;padding-top:10px;}
  .tag-mode{background:#1f6feb;color:#79c0ff;padding:3px 10px;border-radius:12px;font-size:0.78em;font-weight:bold;vertical-align:middle;}
  .no-bets{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;color:#8b949e;font-style:italic;margin-bottom:20px;}
  .pregame-alert{background:#2d1f0f;border:2px solid #f0883e;border-radius:8px;padding:14px;margin-bottom:20px;}
  .pregame-alert h2{color:#f0883e;margin-top:0;}
</style>
</head>
<body>
<h1>⚾ MLB {{ mode_label }} &nbsp;<span class="tag-mode">{{ mode_tag }}</span></h1>
<p>{{ date }} &nbsp;|&nbsp; Generated {{ generated_at }} ET &nbsp;|&nbsp; {{ total_games }} games &nbsp;|&nbsp; {{ total_bets }} value bets</p>

{% if mode == 'pregame' %}
<div class="pregame-alert">
  <h2>🔔 Pregame Alert — First Pitch in ~1 Hour</h2>
  <p>Games starting soon highlighted below. Full detail in attached ZIP.</p>
</div>
{% endif %}

{% if all_value_bets %}
<div class="picks">
  <h2>🎯 Final Model Picks</h2>
  <table>
    <tr><th>Pick</th><th>Type</th><th>Book</th><th>Model Fair</th><th>MC%</th><th>Model%</th><th>Vegas%</th><th>Edge%</th><th>Kelly%</th><th>Conf</th></tr>
    {% for b in all_value_bets %}
    <tr class="g-{{ b.confidence }}">
      <td><strong>{{ b.pick }}</strong></td>
      <td><span class="b{% if 'F5' in b.type %}F5{% elif 'RL' in b.type %}RL{% else %}ML{% endif %}">{{ b.type }}</span></td>
      <td>{% if b.odds > 0 %}+{% endif %}{{ b.odds }}</td>
      <td>{% if b.model_fair_odds > 0 %}+{% endif %}{{ b.model_fair_odds }}</td>
      <td class="val">{{ b.mc_pct }}%</td>
      <td>{{ b.model_prob_pct }}%</td>
      <td class="dim">{{ b.implied_prob_pct }}%</td>
      <td class="edge">+{{ b.edge_pct }}%</td>
      <td>{{ b.kelly_pct }}%</td>
      <td><span class="b{{ b.confidence[0] }}">{{ b.confidence }}</span></td>
    </tr>
    {% endfor %}
  </table>
</div>
{% else %}
<div class="no-bets">No value bets above threshold today.</div>
{% endif %}

<div class="slate">
  <h2>📋 Full Slate</h2>
  <table>
    <tr>
      <th>Time ET</th>
      <th>Matchup</th>
      <th>Away SP</th>
      <th>Home SP</th>
      <th>Books ML</th>
      <th>Model Fair ML</th>
      <th>O/U</th>
      <th>MC Proj</th>
      <th>Why the Lean</th>
    </tr>
    {% for g in games %}
    <tr{% if g.is_soon %} style="background:rgba(240,136,62,0.10);"{% endif %}>
      <td><strong>{{ g.game_time_et }}</strong>{% if g.is_soon %}<br><span style="color:#f0883e;font-size:0.73em;">🔔 SOON</span>{% endif %}</td>
      <td><strong>{{ g.away_team_short }} @ {{ g.home_team_short }}</strong><br><small class="dim">{{ g.weather_disp }}</small></td>
      <td>{{ g.away_pitcher_disp }}</td>
      <td>{{ g.home_pitcher_disp }}</td>
      <td>{{ g.ml_disp }}</td>
      <td>{{ g.fair_ml_disp }}</td>
      <td class="dim">{{ g.total_disp }}</td>
      <td class="val">{{ g.mc_disp }}</td>
      <td>{{ g.lean_disp }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="footer">
  📎 Full game cards, model reasoning, lineups, Monte Carlo breakdown, books vs model — in attached ZIP<br>
  ⚠️ For informational use only. Gamble responsibly. &mdash; vonthadon/mlb-daily-pipeline
</div>
</body>
</html>
"""

DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>MLB Detail Report — {{ date }}</title>
<style>
  body{font-family:'Segoe UI',Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px;}
  h1{color:#58a6ff;border-bottom:2px solid #21262d;padding-bottom:10px;}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px;margin-bottom:22px;}
  .matchup{font-size:1.3em;font-weight:bold;margin-bottom:4px;}
  .meta{color:#8b949e;font-size:0.88em;margin-bottom:12px;}
  .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px;}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
  .box{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;}
  .box h4{color:#58a6ff;margin:0 0 7px;font-size:0.82em;text-transform:uppercase;letter-spacing:1px;}
  .box p, .box li{margin:2px 0;font-size:0.84em;}
  .lineup span{display:block;padding:2px 0;border-bottom:1px solid #21262d;font-size:0.82em;}
  .no-lineup{color:#8b949e;font-style:italic;font-size:0.83em;}
  table{width:100%;border-collapse:collapse;font-size:0.84em;margin-top:8px;}
  th{background:#21262d;color:#8b949e;padding:7px 9px;text-align:left;}
  td{padding:6px 9px;border-bottom:1px solid #21262d;}
  .reason-list{padding-left:18px;margin:6px 0 0 0;}
  .reason-list li{margin-bottom:6px;}
  .vbet{background:#0d1117;border:2px solid #238636;border-radius:7px;padding:12px;margin-top:10px;}
  .mc-box{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;margin-top:10px;}
  .mc-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;}
  .mc-stat{text-align:center;}
  .mc-stat .n{font-size:1.2em;font-weight:bold;color:#3fb950;}
  .mc-stat .l{font-size:0.72em;color:#8b949e;}
  .odds-wrap{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px;}
  .odds-pill{background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:6px 8px;font-size:0.8em;}
  footer{text-align:center;color:#484f58;margin-top:30px;font-size:0.78em;border-top:1px solid #21262d;padding-top:14px;}
</style>
</head>
<body>
<h1>⚾ MLB Detail Report — {{ date }}</h1>
<p style="color:#8b949e">{{ total_games }} games &nbsp;|&nbsp; {{ total_bets }} value bets &nbsp;|&nbsp; Monte Carlo: 100,000 sims/game</p>

{% for game in games %}
<div class="card">
  <div class="matchup">{{ game.away_team }} @ {{ game.home_team }}</div>
  <div class="meta">
    🕐 {{ game.game_time_et }} &nbsp;|&nbsp; {{ game.weather.stadium if game.weather else game.venue }} &nbsp;|&nbsp; Status: {{ game.status }}
  </div>

  <div class="grid3">
    <div class="box">
      <h4>Side Market</h4>
      <p><strong>Books ML:</strong> {{ game.ml_disp }}</p>
      <p><strong>Model Fair ML:</strong> {{ game.fair_ml_disp }}</p>
      <p><strong>Books No-Vig %:</strong> {{ game.books_pct_disp }}</p>
      <p><strong>Model %:</strong> {{ game.model_pct_disp }}</p>
    </div>
    <div class="box">
      <h4>Pitcher Adjustment</h4>
      <p><strong>{{ game.away_team.split()[-1] }} raw/reg ERA:</strong> {{ game.predictions.away_era_raw }} / {{ game.predictions.away_era_reg }}</p>
      <p><strong>{{ game.home_team.split()[-1] }} raw/reg ERA:</strong> {{ game.predictions.home_era_raw }} / {{ game.predictions.home_era_reg }}</p>
      <p style="color:#8b949e">Small-sample ERAs are regressed toward league average.</p>
    </div>
    <div class="box">
      <h4>Weather + Records</h4>
      <p>{{ game.weather_disp }}</p>
      <p><strong>Records:</strong> {{ game.predictions.away_record }} / {{ game.predictions.home_record }}</p>
      <p><strong>O/U:</strong> {{ game.total_disp }}</p>
    </div>
  </div>

  {% if game.predictions and game.predictions.monte_carlo %}
  {% set mc = game.predictions.monte_carlo %}
  <div class="mc-box">
    <h4 style="margin:0 0 8px;color:#d2a8ff;">🎲 Monte Carlo (100,000 sims)</h4>
    <div class="mc-grid">
      <div class="mc-stat"><div class="n">{{ mc.away_win_pct }}%</div><div class="l">Away Win%</div></div>
      <div class="mc-stat"><div class="n">{{ mc.home_win_pct }}%</div><div class="l">Home Win%</div></div>
      <div class="mc-stat"><div class="n">{{ mc.avg_total }}</div><div class="l">Proj Total</div></div>
      <div class="mc-stat"><div class="n">{{ mc.avg_away_runs }} / {{ mc.avg_home_runs }}</div><div class="l">Away / Home Runs</div></div>
    </div>
  </div>
  {% endif %}

  <div class="box" style="margin-top:12px;">
    <h4>Why the model leans this way</h4>
    <ul class="reason-list">
      {% for reason in game.predictions.reasoning %}
      <li>{{ reason }}</li>
      {% endfor %}
    </ul>
  </div>

  <div class="grid2">
    <div class="box lineup">
      <h4>{{ game.away_team }} Lineup</h4>
      {% if game.away_lineup %}{% for p in game.away_lineup %}<span>{{ loop.index }}. {{ p.name }}</span>{% endfor %}{% else %}<p class="no-lineup">Not yet posted</p>{% endif %}
    </div>
    <div class="box lineup">
      <h4>{{ game.home_team }} Lineup</h4>
      {% if game.home_lineup %}{% for p in game.home_lineup %}<span>{{ loop.index }}. {{ p.name }}</span>{% endfor %}{% else %}<p class="no-lineup">Not yet posted</p>{% endif %}
    </div>
  </div>

  {% if game.predictions and game.predictions.value_bets %}
  <div class="vbet">
    <h4 style="margin:0 0 8px;color:#3fb950;">Value Bets</h4>
    <table>
      <tr><th>Pick</th><th>Type</th><th>Book</th><th>Model Fair</th><th>Model%</th><th>Vegas%</th><th>Edge%</th><th>Kelly%</th></tr>
      {% for b in game.predictions.value_bets %}
      <tr>
        <td>{{ b.pick }}</td>
        <td>{{ b.type }}</td>
        <td>{% if b.odds > 0 %}+{% endif %}{{ b.odds }}</td>
        <td>{% if b.model_fair_odds > 0 %}+{% endif %}{{ b.model_fair_odds }}</td>
        <td>{{ b.model_prob_pct }}%</td>
        <td>{{ b.implied_prob_pct }}%</td>
        <td>+{{ b.edge_pct }}%</td>
        <td>{{ b.kelly_pct }}%</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
</div>
{% endfor %}

<footer>⚠️ For informational use only. Gamble responsibly.<br>vonthadon/mlb-daily-pipeline</footer>
</body>
</html>
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
    return f'+{price}' if price > 0 else str(price)


def _prep_games(games, soon_game_pks=None):
    soon_game_pks = soon_game_pks or set()
    for g in games:
        g['game_time_et'] = _fmt_et(g.get('commence_time') or g.get('game_date', ''))
        g.setdefault('weather', None)
        g.setdefault('odds', {})
        g['is_soon'] = g.get('game_pk') in soon_game_pks

        p = g.get('predictions', {})
        mc = p.get('monte_carlo', {})
        g['away_team_short'] = ' '.join(g.get('away_team', '').split()[-2:])
        g['home_team_short'] = ' '.join(g.get('home_team', '').split()[-2:])

        def _sp(pitcher, stats):
            nm = pitcher or 'TBD'
            era = (stats or {}).get('era', '')
            return f"{nm} ({era})" if era and era != 'N/A' else nm

        g['away_pitcher_disp'] = _sp(g.get('away_pitcher'), g.get('away_pitcher_stats'))
        g['home_pitcher_disp'] = _sp(g.get('home_pitcher'), g.get('home_pitcher_stats'))

        w = g.get('weather') or {}
        if w.get('dome'):
            g['weather_disp'] = '🏟️ Dome'
        elif w.get('temp_f'):
            g['weather_disp'] = f"🌡️{w['temp_f']}°F {w.get('wind_mph','')}mph {w.get('wind_dir','')}"
        else:
            g['weather_disp'] = w.get('note', w.get('error', '—'))

        away_ml = p.get('vegas_away_odds')
        home_ml = p.get('vegas_home_odds')
        g['ml_disp'] = f"{_pfx(away_ml)} / {_pfx(home_ml)}"
        g['fair_ml_disp'] = f"{_pfx(p.get('model_away_fair_odds'))} / {_pfx(p.get('model_home_fair_odds'))}"
        g['books_pct_disp'] = f"{p.get('vegas_away_pct','-')}% / {p.get('vegas_home_pct','-')}%"
        g['model_pct_disp'] = f"{p.get('away_win_pct','-')}% / {p.get('home_win_pct','-')}%"
        g['total_disp'] = str(p.get('vegas_total_line') or '—')

        if mc:
            g['mc_disp'] = f"{mc.get('away_win_pct','')}% / {mc.get('home_win_pct','')}%<br><small style='color:#8b949e'>Proj {mc.get('avg_total','')} runs</small>"
        else:
            g['mc_disp'] = '—'

        reasons = p.get('reasoning', [])
        g['lean_disp'] = reasons[0] if reasons else '—'

    return games


def generate_email_html(games, date_str, mode='morning', soon_game_pks=None):
    games = _prep_games(games, soon_game_pks)
    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    all_bets.sort(key=lambda x: x.get('edge_pct', 0), reverse=True)
    mode_labels = {'morning': ('Morning Slate', 'MORNING'), 'pregame': ('Pregame Alert', 'PREGAME'), 'full': ('Daily Report', 'FULL')}
    label, tag = mode_labels.get(mode, ('Report', 'REPORT'))
    return Template(EMAIL_TEMPLATE).render(date=date_str, generated_at=datetime.now().strftime('%H:%M'), total_games=len(games), total_bets=len(all_bets), games=games, all_value_bets=all_bets, mode=mode, mode_label=label, mode_tag=tag)


def generate_detail_html(games, date_str):
    games = _prep_games(games)
    all_bets = [b for g in games for b in g.get('predictions', {}).get('value_bets', [])]
    return Template(DETAIL_TEMPLATE).render(date=date_str, total_games=len(games), total_bets=len(all_bets), games=games)


def generate_csv_files(games, output_dir):
    output_dir = Path(output_dir)
    files = []
    def _write(path, rows):
        pd.DataFrame(rows).to_csv(path, index=False)
        files.append(path)

    slate_rows, weather_rows, odds_rows, lineup_rows, bet_rows, mc_rows, reasoning_rows = [], [], [], [], [], [], []
    mkt_labels = {'h2h': 'ML', 'spreads': 'RL', 'totals': 'Total', 'team_totals': 'Team Total', 'h2h_h1': 'F5 ML', 'spreads_h1': 'F5 RL', 'totals_h1': 'F5 Total'}

    for g in games:
        p = g.get('predictions', {})
        mc = p.get('monte_carlo', {})
        matchup = f"{g.get('away_team', '')} @ {g.get('home_team', '')}"
        w = g.get('weather') or {}

        slate_rows.append({
            'Time ET': g.get('game_time_et', ''),
            'Matchup': matchup,
            'Away SP': g.get('away_pitcher', 'TBD'),
            'Home SP': g.get('home_pitcher', 'TBD'),
            'Books Away ML': p.get('vegas_away_odds', ''),
            'Books Home ML': p.get('vegas_home_odds', ''),
            'Model Away Fair ML': p.get('model_away_fair_odds', ''),
            'Model Home Fair ML': p.get('model_home_fair_odds', ''),
            'Books Away %': p.get('vegas_away_pct', ''),
            'Books Home %': p.get('vegas_home_pct', ''),
            'Model Away %': p.get('away_win_pct', ''),
            'Model Home %': p.get('home_win_pct', ''),
            'Vegas Total': p.get('vegas_total_line', ''),
            'MC Proj Total': mc.get('avg_total', ''),
        })

        if w:
            weather_rows.append({'Matchup': matchup, 'Stadium': w.get('stadium', ''), 'City': w.get('city', ''), 'Dome': w.get('dome', False), 'Temp F': w.get('temp_f', 'N/A'), 'Condition': w.get('condition', w.get('note', 'N/A')), 'Wind mph': w.get('wind_mph', 'N/A'), 'Wind Dir': w.get('wind_dir', 'N/A'), 'Precip %': w.get('precip_pct', 'N/A')})

        for mkt, outcomes in g.get('odds', {}).items():
            for team, data in outcomes.items():
                odds_rows.append({'Matchup': matchup, 'Market': mkt_labels.get(mkt, mkt), 'Side': team, 'Line': data.get('point', ''), 'Odds': data.get('price', ''), 'Book': data.get('bookmaker', '')})

        for side in ('away', 'home'):
            team_name = g.get(f'{side}_team', '')
            for i, player in enumerate(g.get(f'{side}_lineup', []), 1):
                lineup_rows.append({'Matchup': matchup, 'Team': team_name, 'Order': i, 'Player': player.get('name', ''), 'Jersey': player.get('jersey', '')})

        for b in p.get('value_bets', []):
            bet_rows.append({'Matchup': matchup, 'Pick': b['pick'], 'Type': b['type'], 'Book Odds': b['odds'], 'Model Fair Odds': b['model_fair_odds'], 'Model %': b['model_prob_pct'], 'Vegas %': b['implied_prob_pct'], 'Edge %': b['edge_pct'], 'Kelly %': b['kelly_pct'], 'Confidence': b['confidence']})

        if mc:
            over_probs = mc.get('over_probs', {})
            mc_rows.append({'Matchup': matchup, 'Simulations': mc.get('simulations', 0), 'Away Win%': mc.get('away_win_pct', ''), 'Home Win%': mc.get('home_win_pct', ''), 'Proj Total': mc.get('avg_total', ''), 'Away Proj Runs': mc.get('avg_away_runs', ''), 'Home Proj Runs': mc.get('avg_home_runs', ''), 'Away Lambda': mc.get('away_lambda', ''), 'Home Lambda': mc.get('home_lambda', ''), 'Vegas Total': p.get('vegas_total_line', ''), 'O6.5%': over_probs.get('6.5', ''), 'O7.0%': over_probs.get('7.0', ''), 'O7.5%': over_probs.get('7.5', ''), 'O8.0%': over_probs.get('8.0', ''), 'O8.5%': over_probs.get('8.5', ''), 'O9.0%': over_probs.get('9.0', ''), 'O9.5%': over_probs.get('9.5', '')})

        for idx, reason in enumerate(p.get('reasoning', []), 1):
            reasoning_rows.append({'Matchup': matchup, 'Step': idx, 'Reason': reason})

    _write(output_dir / 'slate.csv', slate_rows)
    _write(output_dir / 'weather.csv', weather_rows)
    _write(output_dir / 'odds.csv', odds_rows)
    _write(output_dir / 'lineups.csv', lineup_rows)
    _write(output_dir / 'value_bets.csv', bet_rows)
    _write(output_dir / 'monte_carlo.csv', mc_rows)
    _write(output_dir / 'model_reasoning.csv', reasoning_rows)
    return files
