import pandas as pd
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine

def procesar_capa_gold():
    # 1. Nos conectamos a la base de datos
    engine = create_engine('postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db')
    
    # 2. Leemos la tabla limpia que creamos recién en Silver
    df_silver = pd.read_sql("SELECT * FROM silver.clima_limpio", engine)
    
    # 3. TRANSFORMACIONES DE NEGOCIO (KPIs)
    
    # KPI 1: Calculamos la amplitud térmica (diferencia entre máxima y mínima)
    df_silver['amplitud_termica'] = df_silver['temp_max'] - df_silver['temp_min']
    
    # KPI 2: Creamos reglas para catalogar si el día es extremo o no
    def generar_alerta(row):
        if row['temp_max'] > 30:
            return 'Alerta Calor'
        elif row['temp_min'] < 5:
            return 'Alerta Frío'
        elif row['lluvia_mm'] > 10:
            return 'Alerta Lluvia'
        else:
            return 'Normal'
            
    # Aplicamos la regla a todas las filas para crear la nueva columna
    df_silver['alerta_climatica'] = df_silver.apply(generar_alerta, axis=1)
    
    # 4. Guardamos la tabla definitiva en el esquema 'gold'
    df_silver.to_sql('clima_kpis', engine, schema='gold', if_exists='replace', index=False)
    print("¡Capa Gold finalizada! Datos listos para el dashboard.")

# 5. Configuramos el orquestador
with DAG(
    dag_id="03_gold_clima",
    start_date=datetime(2026, 6, 15),
    schedule_interval="@daily",
    catchup=False,
    is_paused_upon_creation=False
) as dag:

    tarea_gold = PythonOperator(
        task_id="generar_kpis_negocio",
        python_callable=procesar_capa_gold
    )