import json
from datetime import datetime
import pandas as pd
from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    'owner': 'grupo03',
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
}

with DAG(
    dag_id='weather_silver_pipeline',
    default_args=default_args,
    schedule_interval='@hourly',
    is_paused_upon_creation=False,
    catchup=False
) as dag:

    @task
    def orquestar_limpieza_silver():
        pg_hook = PostgresHook(postgres_conn_id='postgres_default')
        conn = pg_hook.get_conn()
        cursor = conn.cursor()

        query_select = "SELECT ciudad, raw_json FROM bronze.raw_weather_data;"
        cursor.execute(query_select)
        registros = cursor.fetchall()

        if not registros:
            print("La capa Bronze está vacía.")
            cursor.close()
            conn.close()
            return

        fecha_proceso_actual = datetime.now()
        datos_actuales_acumulados = []
        datos_forecast_acumulados = []

        for fila in registros:
            nombre_ciudad = fila[0]
            json_crudo = fila[1]

            try:
                hourly = json_crudo.get("hourly", {})
                if hourly and "time" in hourly:
                    for i in range(len(hourly["time"])):
                        datos_actuales_acumulados.append({
                            "ciudad": nombre_ciudad,
                            "latitude": json_crudo.get("latitude"),
                            "longitude": json_crudo.get("longitude"),
                            "time": hourly["time"][i],
                            "temperature": hourly["temperature_2m"][i],
                            "windspeed": hourly["wind_speed_10m"][i],
                            "winddirection": hourly["wind_direction_10m"][i],
                            "precipitation": hourly["precipitation"][i], 
                            "is_day": hourly["is_day"][i],
                            "weather_current": hourly["weather_code"][i],
                            "timezone": json_crudo.get("timezone"),
                            "fecha_procesamiento": fecha_proceso_actual
                        })

                daily = json_crudo.get("daily", {})
                if daily and "time" in daily:
                    for i in range(len(daily["time"])):
                        datos_forecast_acumulados.append({
                            "ciudad": nombre_ciudad,
                            "fecha_pronostico": daily["time"][i],
                            "temp_min": daily["temperature_2m_min"][i],
                            "temp_max": daily["temperature_2m_max"][i],
                            "prob_lluvia": daily.get("precipitation_probability_max", [0]*7)[i],
                            "weather_forecast": daily.get("weather_code", [0]*7)[i],
                            "fecha_procesamiento": fecha_proceso_actual
                        })

            except Exception as e:
                print(f"Advertencia: Error procesando {nombre_ciudad}: {str(e)}")
                continue

        if datos_actuales_acumulados:
            df_current = pd.DataFrame(datos_actuales_acumulados)
            df_current.dropna(subset=["time", "temperature"], inplace=True)
            df_current.drop_duplicates(subset=["ciudad", "time"], inplace=True)
            
            for _, fila in df_current.iterrows():
                cursor.execute("""
                    SELECT 1 FROM silver.weather_current WHERE ciudad = %s AND time = %s;
                """, (fila["ciudad"], pd.to_datetime(fila["time"])))
                
                if not cursor.fetchone():
                    query_insert_current = """
                        INSERT INTO silver.weather_current (ciudad, latitude, longitude, time, temperature, windspeed, winddirection, precipitation, is_day, weather_current, timezone, fecha_procesamiento)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """
                    cursor.execute(query_insert_current, (
                        fila["ciudad"], fila["latitude"], fila["longitude"], pd.to_datetime(fila["time"]),
                        float(fila["temperature"]), float(fila["windspeed"]), float(fila["winddirection"]),
                        float(fila["precipitation"]), int(fila["is_day"]), int(fila["weather_current"]), 
                        fila["timezone"], fila["fecha_procesamiento"]
                    ))

        if datos_forecast_acumulados:
            df_forecast = pd.DataFrame(datos_forecast_acumulados)
            df_forecast.dropna(subset=["fecha_pronostico", "temp_min", "temp_max"], inplace=True)
            df_forecast.drop_duplicates(subset=["ciudad", "fecha_pronostico"], inplace=True)

            for _, fila in df_forecast.iterrows():
                cursor.execute("""
                    SELECT 1 FROM silver.weather_forecast WHERE ciudad = %s AND fecha_pronostico = %s;
                """, (fila["ciudad"], pd.to_datetime(fila["fecha_pronostico"]).date()))
                
                if not cursor.fetchone():
                    query_insert_forecast = """
                        INSERT INTO silver.weather_forecast (ciudad, fecha_pronostico, temp_min, temp_max, prob_lluvia, weather_forecast, fecha_procesamiento)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """
                    cursor.execute(query_insert_forecast, (
                        fila["ciudad"], pd.to_datetime(fila["fecha_pronostico"]).date(), 
                        float(fila["temp_min"]), float(fila["temp_max"]),
                        float(fila["prob_lluvia"]), int(fila["weather_forecast"]), fila["fecha_procesamiento"]
                    ))

        conn.commit()
        cursor.close()
        conn.close()
        print("¡Datos históricos y actuales procesados en Silver!")

    trigger_gold = TriggerDagRunOperator(
    task_id="trigger_weather_gold",
    trigger_dag_id="weather_gold_pipeline",
)

limpieza = orquestar_limpieza_silver()
limpieza >> trigger_gold