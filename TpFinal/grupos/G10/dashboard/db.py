import psycopg2
import pandas as pd

DB_CONFIG = {
    "host": "postgres",
    "database": "airflow_db",
    "user": "airflow",
    "password": "airflow",
    "port": 5432
}

def run_query(query: str) -> pd.DataFrame:
    conn = psycopg2.connect(**DB_CONFIG)

    try:
        df = pd.read_sql(query, conn)
        return df

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()