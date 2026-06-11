import json
from datetime import datetime
import pandas as pd
from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

# Configuración básica del robot (DAG)
default_args = {
    'owner': 'grupo03',
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
}

# Declaramos el DAG de la capa Silver
with DAG(
    dag_id='weather_silver_pipeline',
    default_args=default_args,
    schedule_interval='@hourly',          # Se ejecuta cada una hora de forma automática
    is_paused_upon_creation=False,        # Arranca encendido por defecto como pide el enunciado
    catchup=False
) as dag:

    @task
    def orquestar_limpieza_silver():
        """Lee de Bronze, limpia con Pandas usando la lógica del grupo y guarda en Silver"""
        
        # 1. Conectarse a la base de datos del grupo
        pg_hook = PostgresHook(postgres_conn_id='postgres_default')
        conn = pg_hook.get_conn()
        cursor = conn.cursor()

        # 2. EXTRAER: Traer los datos crudos que guardó el equipo de Bronze
        query_select = "SELECT ciudad, raw_json FROM bronze.raw_weather_data;"
        cursor.execute(query_select)
        registros = cursor.fetchall()

        # Si todavía no hay datos en Bronze, avisamos y frenamos para no romper nada
        if not registros:
            print("La capa Bronze está vacía. No hay datos para limpiar todavía.")
            cursor.close()
            conn.close()
            return

        fecha_proceso_actual = datetime.now()
        datos_actuales_acumulados = []
        datos_forecast_acumulados = []

        # 3. TRANSFORMAR: Procesamiento con Pandas (Basado en el borrador de tus compañeros)
        for fila in registros:
            nombre_ciudad = fila[0]
            json_crudo = fila[1] # El bloque de datos de la API

            try:
                # --- Procesar Clima Actual ---
                # Buscamos la sección del clima de hoy dentro del JSON
                current = json_crudo.get("current", json_crudo.get("current_weather", {}))
                if current:
                    datos_actuales_acumulados.append({
                        "ciudad": nombre_ciudad,
                        "latitude": json_crudo.get("latitude"),
                        "longitude": json_crudo.get("longitude"),
                        "time": current.get("time"),
                        "temperature": current.get("temperature_2m", current.get("temperature")),
                        "windspeed": current.get("wind_speed_10m", current.get("windspeed", 0)),
                        "winddirection": current.get("wind_direction_10m", current.get("winddirection", 0)),
                        "is_day": current.get("is_day", 1),
                        "weather_current": current.get("weather_code", current.get("weathercode", 0)),
                        "timezone": json_crudo.get("timezone"),
                        "fecha_procesamiento": fecha_proceso_actual
                    })

                # --- Procesar Pronóstico Extendido (7 días) ---
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
                # Si una ciudad falla, este bloque evita que se caiga todo el pipeline (Robustez)
                print(f"Advertencia: No se pudo limpiar el registro de {nombre_ciudad}. Motivo: {str(e)}")
                continue

        # 4. CALIDAD DE DATOS: Aplicamos las reglas de limpieza con Pandas
        # Procesamos Clima Actual si hay datos
        if datos_actuales_acumulados:
            df_current = pd.DataFrame(datos_actuales_acumulados)
            df_current.dropna(subset=["time", "temperature"], inplace=True) # Manejo de nulos
            df_current.drop_duplicates(subset=["ciudad", "time"], inplace=True) # Eliminar duplicados
            
            # --- CARGAR EN TABLA WEATHER_CURRENT ---
            for _, fila in df_current.iterrows():
                # Para cumplir con la estrategia de no duplicar datos (Estrategia Upsert/Incremental)
                # Primero chequeamos si ese registro exacto ya existe en la tabla de Silver
                cursor.execute("""
                    SELECT 1 FROM silver.weather_current WHERE ciudad = %s AND time = %s;
                """, (fila["ciudad"], pd.to_datetime(fila["time"])))
                
                # Si no existe, lo guardamos
                if not cursor.fetchone():
                    query_insert_current = """
                        INSERT INTO silver.weather_current (ciudad, latitude, longitude, time, temperature, windspeed, winddirection, is_day, weather_current, timezone, fecha_procesamiento)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """
                    cursor.execute(query_insert_current, (
                        fila["ciudad"], fila["latitude"], fila["longitude"], pd.to_datetime(fila["time"]),
                        float(fila["temperature"]), float(fila["windspeed"]), float(fila["winddirection"]),
                        int(fila["is_day"]), int(fila["weather_current"]), fila["timezone"], fila["fecha_procesamiento"]
                    ))

        # Procesamos Pronóstico si hay datos
        if datos_forecast_acumulados:
            df_forecast = pd.DataFrame(datos_forecast_acumulados)
            df_forecast.dropna(subset=["fecha_pronostico", "temp_min", "temp_max"], inplace=True)
            df_forecast.drop_duplicates(subset=["ciudad", "fecha_pronostico"], inplace=True)

            # --- CARGAR EN TABLA WEATHER_FORECAST ---
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

        # 5. Guardar los cambios definitivos en la base de datos
        conn.commit()
        cursor.close()
        conn.close()
        print("¡Datos procesados y guardados en la capa Silver con éxito!")

    # Activamos la tarea dentro de Airflow
    orquestar_limpieza_silver()