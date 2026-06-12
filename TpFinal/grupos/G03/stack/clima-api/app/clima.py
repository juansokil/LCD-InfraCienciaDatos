import requests
import psycopg2

url = "https://api.open-meteo.com/v1/forecast"

params = {
    "latitude": -34.6131,
    "longitude": -58.3772,
    "current": [
        "temperature_2m",
        "windspeed_10m",
        "weathercode",
        "winddirection"
    ],
    "daily": [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
        "weathercode"
    ],
    "timezone": "auto"
}

respuesta = requests.get(url, params=params)
data = respuesta.json()

# ----------------------
# CURRENT WEATHER
# ----------------------
temperature = data["current"]["temperature_2m"]
windspeed = data["current"]["windspeed_10m"]
winddirection = data["current"]["winddirection"]
weather_current = data["current"]["weathercode"]

# ----------------------
# DAILY FORECAST
# ----------------------
fecha_pronostico = data["daily"]["time"]
temp_max = data["daily"]["temperature_2m_max"]
temp_min = data["daily"]["temperature_2m_min"]
prob_lluvia = data["daily"]["precipitation_probability_max"]
weather_forecast = data["daily"]["weathercode"]

try:
    conn = psycopg2.connect(
    host="g03_warehouse",
    database="weather_data",
    user="admin",
    password="admin123",
    port=5432)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO weather_current (temperature, windspeed, winddirection, weather_current) VALUES (%s, %s, %s, %s)""",
    (temperature, windspeed, winddirection, weather_current))

    for i in range(len(fecha_pronostico)):
        cur.execute("""
            INSERT INTO weather_forecast
            (fecha_pronostico, temp_max, temp_min, prob_lluvia, weather_forecast)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            fecha_pronostico[i],
            temp_max[i],
            temp_min[i],
            prob_lluvia[i],
            weather_forecast[i]
        ))
    conn.commit()

finally:
    if cur:
        cur.close()
    if conn:
        conn.close()