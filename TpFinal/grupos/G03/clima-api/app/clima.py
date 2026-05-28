import requests
import psycopg2

url = "https://api.open-meteo.com/v1/forecast"

params = {
    "latitude": -34.6131,
    "longitude": -58.3772,
    "current": "temperature_2m",
    "timezone": "auto"
}

respuesta = requests.get(url, params=params)

data = respuesta.json()

temperatura = data["current"]["temperature_2m"]

print("Temperatura:", temperatura)

conn = psycopg2.connect(
    host="db",
    database="clima",
    user="admin",
    password="admin123"
)

cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS clima (
    id SERIAL PRIMARY KEY,
    temperatura FLOAT
)
""")

cur.execute(
    "INSERT INTO clima (temperatura) VALUES (%s)",
    (temperatura,)
)

conn.commit()

cur.close()
conn.close()