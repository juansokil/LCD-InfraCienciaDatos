import json
import pandas as pd
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine

def procesar_capa_silver():
    # 1. Nos conectamos a la base de datos
    engine = create_engine('postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db')
    
    # 2. Leemos los datos crudos que guardamos en la capa Bronze
    df_bronze = pd.read_sql("SELECT * FROM bronze.clima_raw", engine)
    
    filas_limpias = []
    
    # 3. Recorremos cada registro que trajo la API
    for index, row in df_bronze.iterrows():
        ciudad = row['ciudad']
        fecha_extraccion = row['fecha_extraccion']
        
        # Convertimos el texto JSON de vuelta a un diccionario de Python para poder leerlo
        datos = json.loads(row['datos_crudos'])
        
        # Extraemos las listas de datos del pronóstico
        fechas = datos['daily']['time']
        temp_max = datos['daily']['temperature_2m_max']
        temp_min = datos['daily']['temperature_2m_min']
        lluvia = datos['daily']['precipitation_sum']
        
        # 4. Como el pronóstico trae 7 días, armamos 7 filas separadas por cada ciudad
        for i in range(len(fechas)):
            filas_limpias.append({
                "ciudad": ciudad,
                "fecha_pronostico": fechas[i],
                "temp_max": temp_max[i],
                "temp_min": temp_min[i],
                "lluvia_mm": lluvia[i],
                "fecha_extraccion": fecha_extraccion
            })
            
    # 5. Convertimos todas esas filas en una tabla nueva
    df_silver = pd.DataFrame(filas_limpias)
    
    # 6. Validaciones de calidad (Requisito de la capa Silver)
    # Nos aseguramos de que la fecha sea realmente tipo fecha y eliminamos datos nulos
    df_silver['fecha_pronostico'] = pd.to_datetime(df_silver['fecha_pronostico'])
    df_silver = df_silver.dropna()
    
    # 7. Guardamos la tabla limpia en el esquema 'silver'
    df_silver.to_sql('clima_limpio', engine, schema='silver', if_exists='replace', index=False)
    print(f"¡Se guardaron {len(df_silver)} registros limpios en Silver!")

# 8. Configuramos el orquestador para este nuevo paso
with DAG(
    dag_id="02_silver_clima",
    start_date=datetime(2026, 6, 15),
    schedule_interval="@daily",
    catchup=False,
    is_paused_upon_creation=False
) as dag:

    tarea_silver = PythonOperator(
        task_id="limpiar_datos_openmeteo",
        python_callable=procesar_capa_silver
    )