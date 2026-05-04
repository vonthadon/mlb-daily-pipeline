import requests
import logging
from datetime import datetime
from scripts.stadiums import STADIUMS

logger = logging.getLogger(__name__)

WMO_CODES = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Icy fog',
    51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Heavy drizzle',
    61: 'Light rain', 63: 'Moderate rain', 65: 'Heavy rain',
    71: 'Light snow', 73: 'Moderate snow', 75: 'Heavy snow',
    80: 'Light showers', 81: 'Moderate showers', 82: 'Heavy showers',
    95: 'Thunderstorm', 96: 'Thunderstorm w/ hail', 99: 'Severe thunderstorm',
}

CARDINALS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']


def degrees_to_cardinal(deg):
    return CARDINALS[round(deg / 22.5) % 16]


def get_game_weather(home_team, game_time_str):
    """Fetch weather for a game using Open-Meteo (free, no key needed)."""
    stadium = STADIUMS.get(home_team)
    if not stadium:
        return {'stadium': 'Unknown', 'city': 'Unknown', 'error': 'Stadium not found'}

    base = {'stadium': stadium['name'], 'city': stadium['city'], 'dome': stadium.get('dome', False)}

    if stadium.get('dome'):
        base['note'] = 'Indoor/Retractable roof — weather n/a'
        return base

    try:
        game_dt = datetime.fromisoformat(game_time_str.replace('Z', '+00:00'))
        game_date = game_dt.date()
        game_hour = game_dt.hour
    except Exception:
        return {**base, 'error': 'Could not parse game time'}

    url = 'https://api.open-meteo.com/v1/forecast'
    params = {
        'latitude': stadium['lat'],
        'longitude': stadium['lon'],
        'hourly': 'temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_direction_10m,weather_code',
        'temperature_unit': 'fahrenheit',
        'wind_speed_unit': 'mph',
        'precipitation_unit': 'inch',
        'forecast_days': 3,
        'timezone': 'auto',
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        hourly = resp.json().get('hourly', {})
        times = hourly.get('time', [])

        idx = None
        for i, t in enumerate(times):
            t_dt = datetime.fromisoformat(t)
            if t_dt.date() == game_date and t_dt.hour == game_hour:
                idx = i
                break
        if idx is None:
            for i, t in enumerate(times):
                if datetime.fromisoformat(t).date() == game_date:
                    idx = i
                    break

        if idx is not None:
            return {
                **base,
                'temp_f': round(hourly['temperature_2m'][idx], 1),
                'precip_pct': hourly['precipitation_probability'][idx],
                'precip_in': round(hourly['precipitation'][idx], 2),
                'wind_mph': round(hourly['wind_speed_10m'][idx], 1),
                'wind_dir': degrees_to_cardinal(hourly['wind_direction_10m'][idx]),
                'condition': WMO_CODES.get(hourly['weather_code'][idx], 'Unknown'),
            }
    except Exception as e:
        logger.warning(f'Weather fetch failed for {home_team}: {e}')
        return {**base, 'error': str(e)}

    return {**base, 'error': 'No matching hour found'}
