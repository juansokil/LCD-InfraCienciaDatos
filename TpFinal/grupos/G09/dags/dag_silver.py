from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime
import pandas as pd
import sqlalchemy
import json

def limpiar_datos():
    # 1. Conectamos a la base de datos
    engine = sqlalchemy.create_engine('postgresql://admin:admin@data_warehouse:5432/InfraCienciaDatos')
    
    # 2. Leemos los datos crudos de Bronze
    print("Leyendo datos de Bronze...")
    query = "SELECT ciudad, raw_json FROM bronze.clima_raw"
    df_raw = pd.read_sql(query, engine)
    
    # 3. Procesamos el JSON de cada ciudad
    registros = []
    for index, row in df_raw.iterrows():
        ciudad = row['ciudad']
        # El raw_json de Postgres viene como string o dict, nos aseguramos de leerlo bien
        datos = row['raw_json'] if isinstance(row['raw_json'], dict) else json.loads(row['raw_json'])
        
        # Open-Meteo devuelve los datos por hora dentro de 'hourly'
        horas = datos.get('hourly', {})
        tiempos = horas.get('time', [])
        temps = horas.get('temperature_2m', [])
        lluvias = horas.get('precipitation', [])
        vientos = horas.get('wind_speed_10m', [])
        
        # Armamos una tabla plana (una fila por cada hora)
        for i in range(len(tiempos)):
            registros.append({
                'ciudad': ciudad,
                'fecha_hora': tiempos[i],
                'temperatura_c': temps[i],
                'lluvia_mm': lluvias[i],
                'viento_kmh': vientos[i]
            })
            
    df_clean = pd.DataFrame(registros)
    
    # 4. Convertimos la fecha a tipo DATE / TIMESTAMP
    df_clean['fecha_hora'] = pd.to_datetime(df_clean['fecha_hora'])
    
    # 5. Guardamos en la capa Silver (sobrescribimos para que no se dupliquen los datos al re-ejecutar)
    print(f"Guardando {len(df_clean)} registros en Silver...")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
    
    # Usamos el método to_sql de pandas para guardar la tabla limpia
    df_clean.to_sql('clima_clean', engine, schema='silver', if_exists='replace', index=False)
    print("¡Capa Silver completada!")

with DAG(
    dag_id='02_silver_clima',
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=['tp_final']
) as dag:

    tarea_limpiar = PythonOperator(
        task_id='limpiar_json_a_tabla',
        python_callable=limpiar_datos
    )

    # Disparamos el DAG de Gold
    disparar_gold = TriggerDagRunOperator(
        task_id='disparar_gold',
        trigger_dag_id='03_gold_clima', # Nombre del DAG que va a hacer tu compañero
        wait_for_completion=False
    )

    tarea_limpiar >> disparar_gold