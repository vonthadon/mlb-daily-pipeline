import pandas as pd
from pathlib import Path
from datetime import datetime
from jinja2 import Template

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLB Betting Report — {{ date }}</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 20px; }
  h1 { color: #58a6ff; border-bottom: 2px solid #21262d; padding-bottom: 10px; }
  h2 { color: #f0883e; margin-top: 30px; }
  h3 { color: #79c0ff; }
  .game-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 24px; }
  .matchup { font-size: 1.4em; font-weight: bold; color: #e6edf3; margin-bottom: 6px; }
  .game-meta { color: #8b949e; font-size: 0.9em; margin-bottom: 14px; }
  .section-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .section-box { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; }
  .section-box h4 { color: #58a6ff; margin: 0 0 8px 0; font-size: 0.85em; text-transform: uppercase; letter-spacing: 1px; }
  .section-box p { margin: 3px 0; font-size: 0.88em; }
  .lineup-col { font-size: 0.82em; }
  .lineup-col span { display: block; padding: 2px 0; border-bottom: 1px solid #21262d; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.88em; }
  th { background: #21262d; color: #8b949e; padding: 8px 10px; text-align: left; }
  td { padding: 7px 10px; border-bottom: 1px solid #21262d; }
  .bet-row-HIGH { background: rgba(63,185,80,0.12); }
  .bet-row-MEDIUM { background: rgba(210,153,34,0.10); }
  .badge-HIGH { background: #238636; color: #3fb950; padding: 2px 8px; border-radius: 12px; font-size: 0.78em; font-weight: bold; }
  .badge-MEDIUM { background: #9e6a03; color: #d29922; padding: 2px 8px; border-radius: 12px; font-size: 0.78em; font-weight: bold; }
  .badge-ML { background: #1f6feb; color: #79c0ff; padding: 2px 7px; border-radius: 10px; font-size: 0.78em; }
  .badge-RL { background: #6e40c9; color: #d2a8ff; padding: 2px 7px; border-radius: 10px; font-size: 0.78em; }
  .badge-F5 { background: #da3633; color: #ffa198; padding: 2px 7px; border-radius: 10px; font-size: 0.78em; }
  .value-section { background: #0d1117; border: 2px solid #238636; border-radius: 8px; padding: 16px; margin-top: 12px; }
  .value-section h4 { color: #3fb950; margin: 0 0 10px 0; }
  .summary-box { background: #161b22; border: 2px solid #58a6ff; border-radius: 8px; padding: 20px; margin-bottom: 30px; }
  .summary-box h2 { color: #58a6ff; margin-top: 0; }
  .stat { display: inline-block; margin: 8px 16px 8px 0; }
  .stat .num { font-size: 2em; font-weight: bold; color: #3fb950; }
  .stat .lbl { font-size: 0.8em; color: #8b949e; }
  .odds-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; margin-top: 8px; }
  .odds-item { background: #0d1117; border: 1px solid #21262d; border-radius: 5px; padding: 8px; font-size: 0.82em; }
  .odds-item .market { color: #8b949e; font-size: 0.75em; text-transform: uppercase; }
  .odds-item .line { color: #e6edf3; font-weight: bold; }
  .no-lineup { color: #8b949e; font-style: italic; font-size: 0.85em; }
  .weather-icon { font-size: 1.2em; }
  footer { text-align: center; color: #8b949e; margin-top: 40px; font-size: 0.8em; border-top: 1px solid #21262d; padding-top: 16px; }
  .final-bets { background: #0f2f14; border: 2px solid #3fb950; border-radius: 10px; padding: 20px; margin: 30px 0; }
  .final-bets h2 { color: #3fb950; margin-top: 0; }
</style>
</head>
<body>
<h1>⚾ MLB Betting Report — {{ date }}</h1>
<p style="color:#8b949e">Generated: {{ generated_at }} ET &nbsp;|&nbsp; {{ total_games }} games on slate &nbsp;|&nbsp; {{ total_bets }} value bets found</p>

{% if all_value_bets %}
<div class="final-bets">
  <h2>🎯 Final Model Picks</h2>
  <table>
    <tr><th>Pick</th><th>Type</th><th>Odds</th><th>Model%</th><th>Implied%</th><th>Edge%</th><th>Kelly%</th><th>Confidence</th></tr>
    {% for bet in all_value_bets %}
    <tr class="bet-row-{{ bet.confidence }}">
      <td><strong>{{ bet.pick }}</strong></td>
      <td><span class="badge-{% if 'F5' in bet.type %}F5{% elif 'RL' in bet.type %}RL{% else %}ML{% endif %}">{{ bet.type }}</span></td>
      <td>{% if bet.odds > 0 %}+{% endif %}{{ bet.odds }}</td>
      <td>{{ bet.model_prob_pct }}%</td>
      <td>{{ bet.implied_prob_pct }}%</td>
      <td><strong>+{{ bet.edge_pct }}%</strong></td>
      <td>{{ bet.kelly_pct }}%</td>
      <td><span class="badge-{{ bet.confidence }}">{{ bet.confidence }}</span></td>
    </tr>
    {% endfor %}
  </table>
</div>
{% else %}
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:24px">
  <p style="color:#8b949e">No value bets found today above the edge threshold.</p>
</div>
{% endif %}

<h2>📋 Today's Slate</h2>
{% for game in games %}
<div class="game-card">
  <div class="matchup">{{ game.away_team }} @ {{ game.home_team }}</div>
  <div class="game-meta">
    🕐 {{ game.game_time_et }}&nbsp;&nbsp;
    📍 {{ game.weather.stadium if game.weather else game.venue }}
    {% if game.predictions %} &nbsp;|&nbsp; Model: {{ game.away_team }} {{ game.predictions.away_win_pct }}% / {{ game.home_team }} {{ game.predictions.home_win_pct }}% {% endif %}
  </div>

  <div class="section-grid">
    <!-- Pitchers -->
    <div class="section-box">
      <h4>⚾ Probable Pitchers</h4>
      <p><strong>{{ game.away_team.split()[-1] }}:</strong> {{ game.away_pitcher or 'TBD' }}</p>
      {% if game.away_pitcher_stats %}
        <p style="color:#8b949e;font-size:0.82em">ERA {{ game.away_pitcher_stats.era }} &bull; WHIP {{ game.away_pitcher_stats.whip }} &bull; {{ game.away_pitcher_stats.ip }} IP &bull; {{ game.away_pitcher_stats.k }}K</p>
      {% endif %}
      <p style="margin-top:8px"><strong>{{ game.home_team.split()[-1] }}:</strong> {{ game.home_pitcher or 'TBD' }}</p>
      {% if game.home_pitcher_stats %}
        <p style="color:#8b949e;font-size:0.82em">ERA {{ game.home_pitcher_stats.era }} &bull; WHIP {{ game.home_pitcher_stats.whip }} &bull; {{ game.home_pitcher_stats.ip }} IP &bull; {{ game.home_pitcher_stats.k }}K</p>
      {% endif %}
    </div>

    <!-- Weather -->
    <div class="section-box">
      <h4>🌤 Weather @ Game Time</h4>
      {% if game.weather %}
        {% if game.weather.dome %}
          <p>🏟️ Indoor / Retractable Roof</p>
          <p style="color:#8b949e">{{ game.weather.city }}</p>
        {% elif game.weather.error is defined %}
          <p style="color:#8b949e">{{ game.weather.error }}</p>
        {% else %}
          <p>🌡️ {{ game.weather.temp_f }}°F — {{ game.weather.condition }}</p>
          <p>💨 {{ game.weather.wind_mph }} mph {{ game.weather.wind_dir }}</p>
          <p>🌧️ Precip chance: {{ game.weather.precip_pct }}%</p>
          <p style="color:#8b949e">{{ game.weather.city }}</p>
        {% endif %}
      {% else %}
        <p style="color:#8b949e">Weather unavailable</p>
      {% endif %}
    </div>

    <!-- Records -->
    <div class="section-box">
      <h4>📊 Team Records</h4>
      {% if game.predictions %}
        <p>{{ game.away_team.split()[-1] }}: <strong>{{ game.predictions.away_record }}</strong></p>
        <p>{{ game.home_team.split()[-1] }}: <strong>{{ game.predictions.home_record }}</strong></p>
      {% else %}
        <p style="color:#8b949e">Records unavailable</p>
      {% endif %}
      <p style="margin-top:8px;color:#8b949e;font-size:0.82em">Status: {{ game.status }}</p>
    </div>
  </div>

  <!-- Lineups -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px">
    <div class="section-box lineup-col">
      <h4>📋 {{ game.away_team }} Lineup</h4>
      {% if game.away_lineup %}
        {% for p in game.away_lineup %}
          <span>{{ loop.index }}. {{ p.name }}</span>
        {% endfor %}
      {% else %}
        <p class="no-lineup">Lineup not yet posted</p>
      {% endif %}
    </div>
    <div class="section-box lineup-col">
      <h4>📋 {{ game.home_team }} Lineup</h4>
      {% if game.home_lineup %}
        {% for p in game.home_lineup %}
          <span>{{ loop.index }}. {{ p.name }}</span>
        {% endfor %}
      {% else %}
        <p class="no-lineup">Lineup not yet posted</p>
      {% endif %}
    </div>
  </div>

  <!-- Odds Display -->
  <div class="section-box">
    <h4>💰 Best Available Odds</h4>
    <div class="odds-grid">
      {% for mkt, outcomes in game.odds.items() %}
        {% for team, data in outcomes.items() %}
          <div class="odds-item">
            <div class="market">{{ mkt|upper }}</div>
            <div class="line">{{ team.split()[-1] }} {% if data.point is not none %}{{ data.point }} {% endif %}{% if data.price > 0 %}+{% endif %}{{ data.price }}</div>
          </div>
        {% endfor %}
      {% endfor %}
    </div>
  </div>

  <!-- Value Bets for this game -->
  {% if game.predictions and game.predictions.value_bets %}
  <div class="value-section">
    <h4>🟢 Value Bets This Game</h4>
    <table>
      <tr><th>Pick</th><th>Type</th><th>Odds</th><th>Model%</th><th>Edge%</th><th>Kelly%</th><th>Conf</th></tr>
      {% for bet in game.predictions.value_bets %}
      <tr class="bet-row-{{ bet.confidence }}">
        <td>{{ bet.pick }}</td>
        <td><span class="badge-{% if 'F5' in bet.type %}F5{% elif 'RL' in bet.type %}RL{% else %}ML{% endif %}">{{ bet.type }}</span></td>
        <td>{% if bet.odds > 0 %}+{% endif %}{{ bet.odds }}</td>
        <td>{{ bet.model_prob_pct }}%</td>
        <td>+{{ bet.edge_pct }}%</td>
        <td>{{ bet.kelly_pct }}%</td>
        <td><span class="badge-{{ bet.confidence }}">{{ bet.confidence }}</span></td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
</div>
{% endfor %}

<footer>
  ⚠️ This report is for informational purposes. Always gamble responsibly.<br>
  HR Edge Pipeline &mdash; vonthadon/mlb-daily-pipeline
</footer>
</body>
</html>
"""


def _fmt_time_et(iso_str):
    """Convert ISO UTC time string to ET display string."""
    try:
        from datetime import timezone, timedelta
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        et = dt.astimezone(timezone(timedelta(hours=-4)))  # EDT
        return et.strftime('%I:%M %p ET')
    except Exception:
        return iso_str


def generate_html_report(games, date_str):
    all_bets = []
    for g in games:
        all_bets.extend(g.get('predictions', {}).get('value_bets', []))
    all_bets.sort(key=lambda x: x.get('edge_pct', 0), reverse=True)

    for g in games:
        g['game_time_et'] = _fmt_time_et(g.get('commence_time') or g.get('game_date', ''))
        if 'weather' not in g:
            g['weather'] = None
        if 'odds' not in g:
            g['odds'] = {}

    tmpl = Template(HTML_TEMPLATE)
    return tmpl.render(
        date=date_str,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        total_games=len(games),
        total_bets=len(all_bets),
        games=games,
        all_value_bets=all_bets,
    )


def generate_csv_files(games, output_dir):
    output_dir = Path(output_dir)
    files = []

    # Slate CSV
    slate_rows = []
    for g in games:
        slate_rows.append({
            'Game Time ET': g.get('game_time_et', ''),
            'Away Team': g.get('away_team', ''),
            'Home Team': g.get('home_team', ''),
            'Venue': g.get('weather', {}).get('stadium', g.get('venue', '')),
            'Status': g.get('status', ''),
            'Away Pitcher': g.get('away_pitcher', 'TBD'),
            'Home Pitcher': g.get('home_pitcher', 'TBD'),
            'Away ERA': g.get('away_pitcher_stats', {}).get('era', 'N/A'),
            'Home ERA': g.get('home_pitcher_stats', {}).get('era', 'N/A'),
            'Away Record': g.get('predictions', {}).get('away_record', ''),
            'Home Record': g.get('predictions', {}).get('home_record', ''),
            'Away Win%': g.get('predictions', {}).get('away_win_pct', ''),
            'Home Win%': g.get('predictions', {}).get('home_win_pct', ''),
        })
    slate_path = output_dir / 'slate.csv'
    pd.DataFrame(slate_rows).to_csv(slate_path, index=False)
    files.append(slate_path)

    # Weather CSV
    weather_rows = []
    for g in games:
        w = g.get('weather', {})
        if w:
            weather_rows.append({
                'Matchup': f"{g.get('away_team','')} @ {g.get('home_team','')}",
                'Stadium': w.get('stadium', ''),
                'City': w.get('city', ''),
                'Dome': w.get('dome', False),
                'Temp (F)': w.get('temp_f', 'N/A'),
                'Condition': w.get('condition', w.get('note', 'N/A')),
                'Wind (mph)': w.get('wind_mph', 'N/A'),
                'Wind Dir': w.get('wind_dir', 'N/A'),
                'Precip %': w.get('precip_pct', 'N/A'),
            })
    weather_path = output_dir / 'weather.csv'
    pd.DataFrame(weather_rows).to_csv(weather_path, index=False)
    files.append(weather_path)

    # Odds CSV
    odds_rows = []
    mkt_labels = {'h2h':'ML','spreads':'RL','totals':'Total','team_totals':'Team Total','h2h_h1':'F5 ML','spreads_h1':'F5 RL','totals_h1':'F5 Total'}
    for g in games:
        for mkt, outcomes in g.get('odds', {}).items():
            for team, data in outcomes.items():
                odds_rows.append({
                    'Matchup': f"{g.get('away_team','')} @ {g.get('home_team','')}",
                    'Market': mkt_labels.get(mkt, mkt),
                    'Side': team,
                    'Line': data.get('point', ''),
                    'Odds': data.get('price', ''),
                    'Bookmaker': data.get('bookmaker', ''),
                })
    odds_path = output_dir / 'odds.csv'
    pd.DataFrame(odds_rows).to_csv(odds_path, index=False)
    files.append(odds_path)

    # Lineups CSV
    lineup_rows = []
    for g in games:
        matchup = f"{g.get('away_team','')} @ {g.get('home_team','')}"
        for i, p in enumerate(g.get('away_lineup', []), 1):
            lineup_rows.append({'Matchup': matchup, 'Team': g.get('away_team',''), 'Order': i, 'Player': p.get('name',''), 'Jersey': p.get('jersey','')})
        for i, p in enumerate(g.get('home_lineup', []), 1):
            lineup_rows.append({'Matchup': matchup, 'Team': g.get('home_team',''), 'Order': i, 'Player': p.get('name',''), 'Jersey': p.get('jersey','')})
    lineup_path = output_dir / 'lineups.csv'
    pd.DataFrame(lineup_rows).to_csv(lineup_path, index=False)
    files.append(lineup_path)

    # Value Bets CSV
    bet_rows = []
    for g in games:
        for bet in g.get('predictions', {}).get('value_bets', []):
            bet_rows.append({
                'Matchup': f"{g.get('away_team','')} @ {g.get('home_team','')}",
                'Game Time ET': g.get('game_time_et', ''),
                'Pick': bet['pick'],
                'Type': bet['type'],
                'Odds': bet['odds'],
                'Model Prob%': bet['model_prob_pct'],
                'Implied Prob%': bet['implied_prob_pct'],
                'Edge%': bet['edge_pct'],
                'Kelly%': bet['kelly_pct'],
                'Confidence': bet['confidence'],
            })
    bets_path = output_dir / 'value_bets.csv'
    pd.DataFrame(bet_rows).to_csv(bets_path, index=False)
    files.append(bets_path)

    return files
