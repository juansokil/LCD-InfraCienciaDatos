import uuid
from datetime import datetime, timezone
import requests
import json 
from pathlib import Path

def cargar_ciudades(): # Funcion para obtener las ciudades
    ruta = Path(__file__).resolve().parents[2] / "config" / "ciudades.json" # ruta es un objeto Path que representa la ruta al archivo ciudades.json (carpeta config), dos niveles por encima del archivo actual.

    with open(ruta, "r", encoding="utf-8") as archivo: # Abrimos el archivo en modo lectura 
        datos = json.load(archivo) # Cargamos el contenido del archivo JSON en un diccionario de Python llamado datos.

    return datos["ciudades"] #Devolvemos la lista de ciudades que se encuentra en el diccionario datos bajo la clave "ciudades".

def consultar_open_meteo(ciudad): # Funcion para consultar la API de Open-Meteo con los datos de la ciudad
    url = "https://api.open-meteo.com/v1/forecast"

    params = { # parametros para la consulta a la API, latitud, longitud, datos actuales y diarios, zona horaria y cantidad de dias de pronostico.
        "latitude": ciudad["latitud"], # de la ciudad que se pasa como argumento, se extraen las coordenadas de latitud y longitud para la consulta a la API.
        "longitude": ciudad["longitud"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": "America/Argentina/Buenos_Aires",
        "forecast_days": 7
    }

    respuesta = requests.get(url, params=params, timeout=30) # Realizamos la solicitud GET a la API de Open-Meteo con los parámetros definidos y un tiempo de espera de 30 segundos.
    respuesta.raise_for_status() # Si la respuesta de la API indica un error (código de estado HTTP 4xx o 5xx), se lanzará una excepción.

    datos = respuesta.json() ## Convertimos la respuesta de la API a un diccionario de Python utilizando el método .json().
    validar_respuesta(datos) ## Validamos la respuesta de la API (funcion de abajo) para asegurarnos de que contiene los datos esperados.

    return respuesta.content


def validar_respuesta(datos): # Validamos la respuesta de la API para asegurarnos de que contiene los datos esperados y que no hay errores en la estructura del JSON.
    if not isinstance(datos, dict):
        raise ValueError("La respuesta no es un objeto JSON")

    if "current" not in datos or "daily" not in datos:
        raise ValueError("Faltan current o daily")

    variables_actuales = [
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "wind_speed_10m"
    ]

    variables_diarias = [
        "time",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "wind_speed_10m_max"
    ]

    for variable in variables_actuales:
        if variable not in datos["current"]:
            raise ValueError(f"Falta la variable actual: {variable}")

    for variable in variables_diarias:
        if variable not in datos["daily"]:
            raise ValueError(f"Falta la variable diaria: {variable}")

        if len(datos["daily"][variable]) != 7:
            raise ValueError(f"Pronóstico incompleto: {variable}")

    return True


def generar_consulta_id(run_id, ciudad_id): # Generamos un ID para la consulta con run_id y ciudad_id. Es un ID para cada consulta realizada a la API de Open-Meteo.
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"open-meteo:{run_id}:{ciudad_id}"
        )
    )


def guardar_raw(payload_bytes, consulta_id, ingested_at): # Guardamos los datos obtenidos de la API en un JSON en carpeta data/raw/ds=YYYY-MM-DD, donde YYYY-MM-DD es la fecha de ingestión de los datos.
    ruta_base = Path(__file__).resolve().parents[2]

    carpeta = (
        ruta_base
        / "data"
        / "raw"
        / f"ds={ingested_at:%Y-%m-%d}"
    )

    carpeta.mkdir(parents=True, exist_ok=True)

    ruta = carpeta / f"{consulta_id}.json"

    try:
        with open(ruta, "xb") as archivo:
            archivo.write(payload_bytes)

    except FileExistsError:
        if ruta.read_bytes() != payload_bytes:
            raise ValueError("El archivo ya existe con otro contenido")

    return str(ruta)

if __name__ == "__main__":
    run_id = f"manual-{datetime.now(timezone.utc).isoformat()}"

    ciudades = cargar_ciudades()

    for ciudad in ciudades:
        ingested_at = datetime.now(timezone.utc)

        payload_bytes = consultar_open_meteo(ciudad)

        consulta_id = generar_consulta_id(
            run_id, ciudad["id"]
        )

        ruta = guardar_raw(
            payload_bytes, consulta_id, ingested_at
        )

        print(f"{ciudad['nombre']}: guardado en {ruta}")