python_code = """from airflow.providers.postgres.hooks.postgres import PostgresHook

def transformar_y_cargar_gold():
    \"\"\"
    Paso 2 (DML): Puebla las dimensiones y la tabla de hechos Gold a partir de los datos limpios en 'silver.sismos'.
    \"\"\"
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    sql_dml = \"\"\"
    -- 1. Poblado de Dimensión Fecha
    INSERT INTO gold.dim_fecha (fecha_id, fecha, anio, mes, nombre_mes, dia, dia_semana)
    SELECT DISTINCT
        CAST(TO_CHAR(fecha_utc, 'YYYYMMDD') AS INT) AS fecha_id,
        DATE(fecha_utc) AS fecha,
        EXTRACT(YEAR FROM fecha_utc) AS anio,
        EXTRACT(MONTH FROM fecha_utc) AS mes,
        TO_CHAR(fecha_utc, 'TMMonth') AS nombre_mes,
        EXTRACT(DAY FROM fecha_utc) AS dia,
        TO_CHAR(fecha_utc, 'TMDay') AS dia_semana
    FROM silver.sismos
    ON CONFLICT (fecha_id) DO NOTHING;

    -- 2. Poblado de Dimensión Región
    INSERT INTO gold.dim_region (nombre_region)
    SELECT DISTINCT COALESCE(lugar, 'Desconocido') AS nombre_region
    FROM silver.sismos
    WHERE lugar IS NOT NULL
    ON CONFLICT (nombre_region) DO NOTHING;

    -- 3. Poblado de Tabla de Hechos (fact_sismos)
    INSERT INTO gold.fact_sismos (sismo_id, fecha_id, region_id, magnitud, profundidad_km, es_tsunami, cantidad)
    SELECT
        s.event_id AS sismo_id,
        f.fecha_id,
        r.region_id,
        s.magnitud,
        s.profundidad_km,
        0 AS es_tsunami, -- Asumiendo 0 ya que silver.sismos no tiene columna tsunami según el DDL previo
        1 AS cantidad
    FROM silver.sismos s
    JOIN gold.dim_fecha f ON DATE(s.fecha_utc) = f.fecha
    JOIN gold.dim_region r ON COALESCE(s.lugar, 'Desconocido') = r.nombre_region
    ON CONFLICT (sismo_id) DO UPDATE SET
        magnitud = EXCLUDED.magnitud,
        profundidad_km = EXCLUDED.profundidad_km,
        es_tsunami = EXCLUDED.es_tsunami;
    \"\"\"
    
    print("Ejecutando DML: Transformación y carga en la capa Gold...")
    pg_hook.run(sql_dml)
    print("¡Transformación a la capa Gold completada exitosamente!")

if __name__ == '__main__':
    transformar_y_cargar_gold()
"""

with open("transformar_y_cargar_gold.py", "w", encoding="utf-8") as f:
    f.write(python_code)
    
print("File created")