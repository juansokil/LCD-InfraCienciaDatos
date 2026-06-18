from sqlalchemy import create_engine

def get_engine():
    # Nos conectamos a la base de datos Postgres que corre en Docker
    return create_engine('postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db')
