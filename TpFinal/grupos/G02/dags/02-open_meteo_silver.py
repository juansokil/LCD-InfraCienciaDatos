import logging

import pendulum

from airflow.sdk import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

import json
from datetime import datetime, timedelta, timezone





CONN_ID = "warehouse"

BRONZE_TABLE = "bronze.open_meteo_raw"

SILVER_CURRENT_TABLE = "silver.clima_actual"

SILVER_FORECAST_TABLE = "silver.pronostico_diario"

GOLD_DAG_ID = "open_meteo_gold"








@task
def create_silver_tables():
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    sql = """
    CREATE SCHEMA IF NOT EXISTS silver;

    CREATE TABLE IF NOT EXISTS silver.clima_actual (
        source_id BIGINT PRIMARY KEY
            REFERENCES bronze.open_meteo_raw(id),

        city_code VARCHAR(10) NOT NULL,
        valid_at TIMESTAMPTZ,

        temperature_c NUMERIC(5,2),
        apparent_temperature_c NUMERIC(5,2),
        humidity_pct INTEGER,
        precipitation_mm NUMERIC(8,2),
        weather_code INTEGER,
        weather_description TEXT,
        wind_speed_kmh NUMERIC(8,2),
        wind_direction_deg INTEGER,
        cloud_cover_pct INTEGER
    );

    CREATE TABLE IF NOT EXISTS silver.pronostico_diario (
        source_id BIGINT
            REFERENCES bronze.open_meteo_raw(id),

        city_code VARCHAR(10) NOT NULL,
        forecast_date DATE NOT NULL,

        temperature_max_c NUMERIC(5,2),
        temperature_min_c NUMERIC(5,2),
        precipitation_sum_mm NUMERIC(8,2),
        wind_speed_max_kmh NUMERIC(8,2),
        weather_code INTEGER,
        weather_description TEXT,

        PRIMARY KEY (source_id, forecast_date)
    );
    """

    hook.run(sql)
    logging.info("Tablas Silver creadas o verificadas correctamente.")








@task
def extract_bronze_records():
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    sql = f"""
        SELECT
            b.id,
            b.city_code,
            b.payload
        FROM {BRONZE_TABLE} AS b
        WHERE
            b.http_status = 200
            AND b.payload IS NOT NULL
            AND b.error_message IS NULL
            AND NOT EXISTS (
                SELECT 1
                FROM {SILVER_CURRENT_TABLE} AS s
                WHERE s.source_id = b.id
            )
        ORDER BY b.id;
    """

    rows = hook.get_records(sql)

    records = [
        {
            "source_id": row[0],
            "city_code": row[1],
            "payload": row[2]
        }
        for row in rows
    ]

    logging.info("Registros Bronze pendientes de procesar: %s", len(records))

    return records







def get_weather_description(code):
    descriptions = {
        0: "Despejado",
        1: "Mayormente despejado",
        2: "Parcialmente nublado",
        3: "Cubierto",
        45: "Niebla",
        48: "Niebla",
        51: "Llovizna",
        53: "Llovizna",
        55: "Llovizna",
        56: "Llovizna",
        57: "Llovizna",
        61: "Lluvia",
        63: "Lluvia",
        65: "Lluvia",
        66: "Lluvia",
        67: "Lluvia",
        71: "Nieve",
        73: "Nieve",
        75: "Nieve",
        77: "Nieve",
        80: "Chaparrones",
        81: "Chaparrones",
        82: "Chaparrones",
        85: "Chaparrones de nieve",
        86: "Chaparrones de nieve",
        95: "Tormenta",
        96: "Tormenta",
        97: "Tormenta",
        99: "Tormenta"
    }

    if code is None:
        return None

    return descriptions.get(int(code), "Sin clasificar")









def validate_current(current):

    if not isinstance(current, dict):
        raise ValueError("El objeto current no es válido.")

    required_fields = [
        "time",
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
        "wind_direction_10m",
        "cloud_cover"
    ]

    for field in required_fields:
        if field not in current:
            raise ValueError(
                f"Falta el campo obligatorio: {field}"
            )

    if not current["time"]:
        raise ValueError("La hora del clima actual está vacía.")

    numeric_fields = [
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
        "wind_direction_10m",
        "cloud_cover"
    ]

    for field in numeric_fields:
        value = current[field]

        if value is None:
            continue

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"El campo {field} debe ser numérico."
            )

    temperature = current["temperature_2m"]
    apparent_temperature = current["apparent_temperature"]
    humidity = current["relative_humidity_2m"]
    precipitation = current["precipitation"]
    wind_speed = current["wind_speed_10m"]
    wind_direction = current["wind_direction_10m"]
    cloud_cover = current["cloud_cover"]
    weather_code = current["weather_code"]

    if temperature is not None and not -60 <= temperature <= 60:
        raise ValueError("Temperatura fuera del rango permitido.")

    if apparent_temperature is not None and not -60 <= apparent_temperature <= 60:
        raise ValueError("Sensación térmica fuera del rango permitido.")

    if humidity is not None and not 0 <= humidity <= 100:
        raise ValueError("Humedad fuera del rango permitido.")

    if precipitation is not None and precipitation < 0:
        raise ValueError("La precipitación no puede ser negativa.")

    if wind_speed is not None and wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    if wind_direction is not None and not 0 <= wind_direction <= 360:
        raise ValueError("Dirección del viento fuera del rango permitido.")

    if cloud_cover is not None and not 0 <= cloud_cover <= 100:
        raise ValueError("Nubosidad fuera del rango permitido.")

    if weather_code is not None and not isinstance(weather_code, int):
        raise ValueError("El código meteorológico debe ser entero.")











def transform_current(record):
    payload = record["payload"]

    if isinstance(payload, str):
        payload = json.loads(payload)

    current = payload.get("current", {})

    validate_current(current)

    weather_code = current.get("weather_code")

    # Interpretar la hora local usando el desplazamiento UTC
    valid_at = current.get("time")

    if valid_at is not None:
        valid_at = datetime.fromisoformat(valid_at)

        if valid_at.tzinfo is None:
            offset_seconds = int(payload.get("utc_offset_seconds", 0))
            local_timezone = timezone(
                timedelta(seconds=offset_seconds)
            )
            valid_at = valid_at.replace(tzinfo=local_timezone)

    return {
        "source_id": record["source_id"],
        "city_code": record["city_code"],
        "valid_at": valid_at,
        "temperature_c": current.get("temperature_2m"),
        "apparent_temperature_c": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "weather_code": weather_code,
        "weather_description": get_weather_description(weather_code),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "cloud_cover_pct": current.get("cloud_cover")
    }









def transform_forecast(record):
    payload = record["payload"]

    if isinstance(payload, str):
        payload = json.loads(payload)

    daily = payload.get("daily", {})

    required_fields = [
        "time",
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "wind_speed_10m_max"
    ]

    # Verificar que todos los campos existan y sean listas
    for field in required_fields:
        if field not in daily or not isinstance(daily[field], list):
            raise ValueError(
                f"Campo diario ausente o inválido: {field}"
            )

    # Verificar que todos los arrays tengan igual longitud
    lengths = [len(daily[field]) for field in required_fields]

    if len(set(lengths)) != 1:
        raise ValueError(
            "Los arrays del pronóstico tienen distintas longitudes."
        )

    dates = daily["time"]

    if not dates:
        raise ValueError(
            "El pronóstico diario no contiene fechas."
        )

    forecast_records = []
    seen_dates = set()

    for i, forecast_date in enumerate(dates):

        # Validar formato de fecha
        try:
            datetime.strptime(forecast_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            raise ValueError(
                f"Fecha del pronóstico inválida: {forecast_date}"
            )

        # Evitar fechas duplicadas
        if forecast_date in seen_dates:
            raise ValueError(
                f"Fecha duplicada en el pronóstico: {forecast_date}"
            )

        seen_dates.add(forecast_date)

        temperature_max = daily["temperature_2m_max"][i]
        temperature_min = daily["temperature_2m_min"][i]
        precipitation = daily["precipitation_sum"][i]
        wind_speed = daily["wind_speed_10m_max"][i]
        weather_code = daily["weather_code"][i]

        # Validar tipos numéricos
        numeric_values = {
            "temperature_max": temperature_max,
            "temperature_min": temperature_min,
            "precipitation": precipitation,
            "wind_speed": wind_speed,
            "weather_code": weather_code
        }

        for field, value in numeric_values.items():
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(
                        f"El campo {field} debe ser numérico."
                    )

        # Validar temperaturas
        for temperature in [temperature_max, temperature_min]:
            if temperature is not None and not -60 <= temperature <= 60:
                raise ValueError(
                    "Temperatura del pronóstico fuera del rango permitido."
                )

        # Validar relación entre máxima y mínima
        if (
            temperature_max is not None
            and temperature_min is not None
            and temperature_max < temperature_min
        ):
            raise ValueError(
                "La temperatura máxima no puede ser menor que la mínima."
            )

        # Validar precipitación
        if precipitation is not None and precipitation < 0:
            raise ValueError(
                "La precipitación del pronóstico no puede ser negativa."
            )

        # Validar viento
        if wind_speed is not None and wind_speed < 0:
            raise ValueError(
                "La velocidad máxima del viento no puede ser negativa."
            )

        # Validar código meteorológico
        if weather_code is not None and (
            isinstance(weather_code, bool) or not isinstance(weather_code, int)
        ):
            raise ValueError(
                "El código meteorológico del pronóstico debe ser entero."
            )

        # Agregar el registro validado
        forecast_records.append({
            "source_id": record["source_id"],
            "city_code": record["city_code"],
            "forecast_date": forecast_date,
            "temperature_max_c": temperature_max,
            "temperature_min_c": temperature_min,
            "precipitation_sum_mm": precipitation,
            "wind_speed_max_kmh": wind_speed,
            "weather_code": weather_code,
            "weather_description": get_weather_description(weather_code)
        })

    return forecast_records









@task
def load_silver(records):
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    if not records:
        logging.info("No hay registros para cargar en Silver.")
        return

    current_sql = f"""
        INSERT INTO {SILVER_CURRENT_TABLE} (
            source_id,
            city_code,
            valid_at,
            temperature_c,
            apparent_temperature_c,
            humidity_pct,
            precipitation_mm,
            weather_code,
            weather_description,
            wind_speed_kmh,
            wind_direction_deg,
            cloud_cover_pct
        )
        VALUES (
            %(source_id)s,
            %(city_code)s,
            %(valid_at)s,
            %(temperature_c)s,
            %(apparent_temperature_c)s,
            %(humidity_pct)s,
            %(precipitation_mm)s,
            %(weather_code)s,
            %(weather_description)s,
            %(wind_speed_kmh)s,
            %(wind_direction_deg)s,
            %(cloud_cover_pct)s
        )
        ON CONFLICT (source_id) DO NOTHING;
    """

    forecast_sql = f"""
        INSERT INTO {SILVER_FORECAST_TABLE} (
            source_id,
            city_code,
            forecast_date,
            temperature_max_c,
            temperature_min_c,
            precipitation_sum_mm,
            wind_speed_max_kmh,
            weather_code,
            weather_description
        )
        VALUES (
            %(source_id)s,
            %(city_code)s,
            %(forecast_date)s,
            %(temperature_max_c)s,
            %(temperature_min_c)s,
            %(precipitation_sum_mm)s,
            %(wind_speed_max_kmh)s,
            %(weather_code)s,
            %(weather_description)s
        )
        ON CONFLICT (source_id, forecast_date) DO NOTHING;
    """

    with hook.get_conn() as conn:
        with conn.cursor() as cursor:
            for record in records:
                current = transform_current(record)
                forecast = transform_forecast(record)

                cursor.execute(current_sql, current)

                cursor.executemany(forecast_sql, forecast)

    logging.info(
        "Carga Silver finalizada para %s registros Bronze.",
        len(records)
    )














@dag(
    dag_id="open_meteo_silver",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False
)
def open_meteo_silver():

    tables = create_silver_tables()

    records = extract_bronze_records()

    loaded = load_silver(records)

    trigger_gold = TriggerDagRunOperator(
        task_id="trigger_gold",
        trigger_dag_id=GOLD_DAG_ID,
        wait_for_completion=False
    )

    tables >> records >> loaded >> trigger_gold


open_meteo_silver()