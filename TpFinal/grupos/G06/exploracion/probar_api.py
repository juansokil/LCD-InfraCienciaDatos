import json
import time
import requests

destinos = {
    "purmamarca": (-23.74, -65.50),
    "bariloche": (-41.13, -71.31),
    "iguazu": (-25.60, -54.57),
}

nombres = list(destinos.keys())
lats = ",".join(str(lat) for lat, lon in destinos.values())
lons = ",".join(str(lon) for lat, lon in destinos.values())

params = {
    "latitude": lats,      # "-23.74,-41.13,-25.6"
    "longitude": lons,     # "-65.5,-71.31,-54.57"
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "daily": ",".join([
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        "precipitation_sum",
        "daylight_duration",
        "wind_gusts_10m_max",
    ]),
    "timezone": "America/Argentina/Buenos_Aires",
}

inicio = time.perf_counter()
r = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params, timeout=120)
r.raise_for_status()
duracion = time.perf_counter() - inicio

respuesta = r.json()   # ahora es una lista: un objeto por destino
print(f"Tardó {duracion:.1f} s | destinos devueltos: {len(respuesta)}")

for nombre, datos in zip(nombres, respuesta):
    dias = len(datos["daily"]["time"])
    print(f"{nombre}: pedido {destinos[nombre]} -> grilla ({datos['latitude']}, {datos['longitude']}) | {dias} días")

with open("exploracion/ejemplo_3_destinos.json", "w", encoding="utf-8") as f:
    json.dump(respuesta, f, indent=2, ensure_ascii=False)