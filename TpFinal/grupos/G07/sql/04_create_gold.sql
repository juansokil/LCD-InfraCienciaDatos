from airflow.providers.postgres.hooks.postgres import PostgresHook

def crear_tablas_gold():
    """
    DDL para la Capa Gold: Crea el esquema 'gold' y sus tablas dimensionales.
    """
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    sql_ddl = """
    CREATE SCHEMA IF NOT EXISTS gold;

    CREATE TABLE IF NOT EXISTS gold.dim_fecha (
        fecha_id INT PRIMARY KEY,
        fecha DATE NOT NULL UNIQUE,
        anio INT NOT NULL,
        mes INT NOT NULL,
        nombre_mes VARCHAR(20) NOT NULL,
        dia INT NOT NULL,
        dia_semana VARCHAR(20) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS gold.dim_region (
        region_id SERIAL PRIMARY KEY,
        nombre_region VARCHAR(255) NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS gold.fact_sismos (
        sismo_id VARCHAR(100) PRIMARY KEY,
        fecha_id INT NOT NULL REFERENCES gold.dim_fecha(fecha_id),
        region_id INT NOT NULL REFERENCES gold.dim_region(region_id),
        magnitud NUMERIC(4,2),
        profundidad_km NUMERIC(8,2),
        es_tsunami INT DEFAULT 0,
        cantidad INT DEFAULT 1
    );
    """
    
    print("Creando esquema y tablas de la capa Gold...")
    pg_hook.run(sql_ddl)
    print("¡Capa Gold creada exitosamente!")

if __name__ == '__main__':
    crear_tablas_gold()