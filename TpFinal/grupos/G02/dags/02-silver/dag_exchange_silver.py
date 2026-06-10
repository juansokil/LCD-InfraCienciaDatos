from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import os
from sqlalchemy import create_engine, text


def transformar_bronze_a_silver():
    # 1. Credenciales del .env
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")


    # 2. Conexión a la base de datos
    engine = create_engine(f"postgresql://{db_user}:{db_pass}@data_warehouse:5432/{db_name}")
    
    # 3. Query mágica en SQL para desanidar el JSON de la capa Bronze
    # Usamos jsonb_each_text para convertir cada par "MONEDA": valor en una fila.
    query_crear_tabla = text("""
        CREATE TABLE IF NOT EXISTS silver.exchange_rates (
            id SERIAL PRIMARY KEY,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            api_timestamp TIMESTAMP,
            base_currency VARCHAR(10),
            currency_code VARCHAR(10),
            exchange_rate NUMERIC(18, 6)
        );
    """)
    
    query_procesar_datos = text("""
        INSERT INTO silver.exchange_rates (api_timestamp, base_currency, currency_code, exchange_rate)
        SELECT 
            TO_TIMESTAMP(api_timestamp) as api_timestamp,
            base_currency,
            key as currency_code,
            value::numeric as exchange_rate
        FROM bronze.exchange_rates_raw,
        jsonb_each_text(rates)
        -- Evitamos duplicados procesando solo lo que no insertamos antes (en base al timestamp)
        WHERE TO_TIMESTAMP(api_timestamp) NOT IN (SELECT DISTINCT api_timestamp FROM silver.exchange_rates);
    """)
    
    with engine.connect() as conn:
        # Aseguramos que la tabla Silver exista
        conn.execute(query_crear_tabla)
        # Procesamos y movemos los datos limpios
        conn.execute(query_procesar_datos)
        conn.commit()
        
    print("¡Transformación de Capa Silver completada con éxito!")


# Reglas del orquestador para Silver
with DAG(
    dag_id="02_silver_exchange_rates",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@hourly",
    catchup=False,
    is_paused_upon_creation=False
) as dag:
    
    tarea_silver = PythonOperator(
        task_id="limpieza_silver",
        python_callable=transformar_bronze_a_silver
    )
