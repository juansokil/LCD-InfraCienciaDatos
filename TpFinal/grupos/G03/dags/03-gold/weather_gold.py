from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import psycopg2

# Configuración de conexión
DB_CONFIG = "dbname=weather_data user=admin password=admin123 host=g03_warehouse port=5432"

def normalizar_ciudad(columna):
    return f"REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM({columna})), 'Á', 'A'), 'É', 'E'), 'Í', 'I'), 'Ó', 'O'), 'Ú', 'U')"

def cargar_fact_clima_real():
    conn = psycopg2.connect(DB_CONFIG)
    cur = conn.cursor()
    
    query = f"""
    INSERT INTO gold.fact_clima_real (
        fecha, ciudad_id, temp_promedio, temp_max, temp_min, lluvia_acumulada, viento_promedio
    )
    SELECT 
        DATE(w.time) AS fecha, 
        c.id AS ciudad_id, 
        AVG(w.temperature) AS temp_promedio, 
        MAX(w.temperature) AS temp_max, 
        MIN(w.temperature) AS temp_min, 
        SUM(COALESCE(w.precipitation,0)) AS lluvia_acumulada, 
        AVG(w.windspeed) AS viento_promedio 
    FROM silver.weather_current w 
    JOIN gold.dim_ciudad c ON {normalizar_ciudad('w.ciudad')} = {normalizar_ciudad('c.ciudad')} 
    GROUP BY DATE(w.time), c.id
    ON CONFLICT (fecha, ciudad_id) DO NOTHING;
    """
    cur.execute(query)
    conn.commit()
    cur.close()
    conn.close()

def cargar_fact_pronostico():
    conn = psycopg2.connect(DB_CONFIG)
    cur = conn.cursor()
    
    query = f"""
    INSERT INTO gold.fact_pronostico (
        fecha_pronostico, ciudad_id, temp_min_esperada, temp_max_esperada, prob_lluvia
    )
    SELECT 
        w.fecha_pronostico, 
        c.id AS ciudad_id, 
        w.temp_min, 
        w.temp_max, 
        w.prob_lluvia 
    FROM silver.weather_forecast w 
    JOIN gold.dim_ciudad c ON {normalizar_ciudad('w.ciudad')} = {normalizar_ciudad('c.ciudad')}
    ON CONFLICT (fecha_pronostico, ciudad_id) DO NOTHING;
    """
    cur.execute(query)
    conn.commit()
    cur.close()
    conn.close()

# Definición del DAG con el nombre nuevo
with DAG('weather_gold_pipeline', start_date=datetime(2025, 1, 1), schedule='@daily', catchup=False) as dag:
    
    task_clima = PythonOperator(
        task_id='cargar_fact_clima_real',
        python_callable=cargar_fact_clima_real
    )
    
    task_pronostico = PythonOperator(
        task_id='cargar_fact_pronostico',
        python_callable=cargar_fact_pronostico
    )
    
    task_clima >> task_pronostico