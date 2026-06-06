import logging
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from sqlalchemy import create_engine, text

def get_engine():
    host     = os.environ.get("SOURCE_DB_HOST", "data_warehouse")
    user     = os.environ.get("SOURCE_DB_USER", "weather_user")
    password = os.environ.get("SOURCE_DB_PASS", "weather_pass")
    db       = os.environ.get("SOURCE_DB_NAME", "weather_dwh")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db}"
    )

PROVINCIAS = {
    "buenos_aires":     {"nombre": "Buenos Aires",     "lat": -34.6037, "lon": -58.3816},
    "cordoba":          {"nombre": "Córdoba",           "lat": -31.4135, "lon": -64.1811},
    "mendoza":          {"nombre": "Mendoza",           "lat": -32.8895, "lon": -68.8458},
    "salta":            {"nombre": "Salta",             "lat": -24.7859, "lon": -65.4117},
    "tierra_del_fuego": {"nombre": "Tierra del Fuego", "lat": -54.8019, "lon": -68.3030},
}

DIAS_ES = {
    "Monday": "Lunes",    "Tuesday": "Martes",    "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes",    "Saturday": "Sábado",
    "Sunday": "Domingo"
}

WMO_CODES = [
    (0,  "Cielo despejado",               "despejado", False),
    (1,  "Principalmente despejado",      "despejado", False),
    (2,  "Parcialmente nublado",          "nublado",   False),
    (3,  "Nublado",                       "nublado",   False),
    (45, "Niebla",                        "niebla",    False),
    (48, "Niebla con escarcha",           "niebla",    False),
    (51, "Llovizna leve",                 "llovizna",  False),
    (53, "Llovizna moderada",             "llovizna",  False),
    (55, "Llovizna densa",                "llovizna",  False),
    (61, "Lluvia leve",                   "lluvia",    False),
    (63, "Lluvia moderada",               "lluvia",    False),
    (65, "Lluvia intensa",                "lluvia",    True),
    (71, "Nevada leve",                   "nieve",     False),
    (73, "Nevada moderada",               "nieve",     False),
    (75, "Nevada intensa",                "nieve",     True),
    (77, "Granos de nieve",               "nieve",     False),
    (80, "Chubascos leves",               "lluvia",    False),
    (81, "Chubascos moderados",           "lluvia",    False),
    (82, "Chubascos violentos",           "lluvia",    True),
    (85, "Chubascos de nieve leves",      "nieve",     False),
    (86, "Chubascos de nieve intensos",   "nieve",     True),
    (95, "Tormenta eléctrica",            "tormenta",  True),
    (96, "Tormenta con granizo leve",     "tormenta",  True),
    (99, "Tormenta con granizo intenso",  "tormenta",  True),
]

default_args = {
    "owner": "G01",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

@dag(
    dag_id="open_meteo_gold",
    default_args=default_args,
    start_date=datetime(2026, 5, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["prod", "gold", "weather"],
    is_paused_upon_creation=False,
)
def open_meteo_pipeline_gold():

    @task()
    def cargar_dim_provincia():

        engine = get_engine()
        query = text("""
            INSERT INTO gold.dim_provincia
                (id_provincia, nombre_provincia, latitud, longitud)
            VALUES (:id, :nombre, :lat, :lon)
            ON CONFLICT (id_provincia) DO NOTHING
        """)
        with engine.begin() as conn:
            for prov_id, datos in PROVINCIAS.items():
                conn.execute(query, {
                    "id":     prov_id,
                    "nombre": datos["nombre"],
                    "lat":    datos["lat"],
                    "lon":    datos["lon"],
                })
        logging.info(f"dim_provincia → {len(PROVINCIAS)} filas verificadas")

    @task()
    def cargar_dim_weather_code():

        engine = get_engine()
        query = text("""
            INSERT INTO gold.dim_weather_code
                (code, descripcion, categoria, es_alerta)
            VALUES (:code, :descripcion, :categoria, :es_alerta)
            ON CONFLICT (code) DO NOTHING
        """)
        with engine.begin() as conn:
            for code, desc, cat, alerta in WMO_CODES:
                conn.execute(query, {
                    "code":        code,
                    "descripcion": desc,
                    "categoria":   cat,
                    "es_alerta":   alerta,
                })
        logging.info(f"dim_weather_code → {len(WMO_CODES)} códigos verificados")

    @task()
    def cargar_dim_tiempo():

        engine = get_engine()

        query_fechas = text("""
            SELECT DISTINCT fecha FROM (
                SELECT DATE(fecha_hora)   AS fecha FROM silver.clima_actual
                UNION
                SELECT fecha_pronostico   AS fecha FROM silver.clima_pronostico
            ) sub
            ORDER BY fecha
        """)

        query_insert = text("""
            INSERT INTO gold.dim_tiempo
                (fecha, anio, mes, dia, dia_semana, es_fin_de_semana)
            VALUES
                (:fecha, :anio, :mes, :dia, :dia_semana, :es_fin_de_semana)
            ON CONFLICT (fecha) DO NOTHING
        """)

        with engine.begin() as conn:
            fechas = [row[0] for row in conn.execute(query_fechas).fetchall()]
            for f in fechas:
                conn.execute(query_insert, {
                    "fecha":            f,
                    "anio":             f.year,
                    "mes":              f.month,
                    "dia":              f.day,
                    "dia_semana":       DIAS_ES[f.strftime("%A")],
                    "es_fin_de_semana": f.weekday() >= 5,
                })
        logging.info(f"dim_tiempo → {len(fechas)} fechas verificadas")

    @task()
    def cargar_fact_clima_diario():

        engine = get_engine()

        query_fechas = text("""
            SELECT DISTINCT DATE(fecha_hora) AS fecha
            FROM silver.clima_actual
            ORDER BY fecha
        """)

        query_delete = text("""
            DELETE FROM gold.fact_clima_diario WHERE fecha = :fecha
        """)

        query_insert = text("""
            INSERT INTO gold.fact_clima_diario (
                id_provincia, fecha,
                temp_promedio_c, temp_max_real_c, temp_min_real_c,
                lluvia_total_mm, confort_termico
            )
            SELECT
                id_provincia,
                DATE(fecha_hora)                        AS fecha,
                ROUND(AVG(temperatura_c)::NUMERIC, 2)  AS temp_promedio_c,
                ROUND(MAX(temperatura_c)::NUMERIC, 2)  AS temp_max_real_c,
                ROUND(MIN(temperatura_c)::NUMERIC, 2)  AS temp_min_real_c,
                ROUND(SUM(lluvia_mm)::NUMERIC, 2)      AS lluvia_total_mm,
                CASE
                    WHEN AVG(temperatura_c) < 0  THEN 'Frío extremo'
                    WHEN AVG(temperatura_c) < 10 THEN 'Frío'
                    WHEN AVG(temperatura_c) < 18 THEN 'Fresco'
                    WHEN AVG(temperatura_c) < 24 THEN 'Confortable'
                    WHEN AVG(temperatura_c) < 30 THEN 'Cálido'
                    ELSE                              'Calor extremo'
                END                                    AS confort_termico
            FROM silver.clima_actual
            WHERE DATE(fecha_hora) = :fecha
            GROUP BY id_provincia, DATE(fecha_hora)
        """)

        with engine.begin() as conn:
            fechas = [row[0] for row in conn.execute(query_fechas).fetchall()]
            total = 0
            for f in fechas:
                conn.execute(query_delete, {"fecha": f})
                result = conn.execute(query_insert, {"fecha": f})
                total += result.rowcount

        logging.info(
            f"fact_clima_diario → {total} filas para {len(fechas)} fechas"
        )

    @task()
    def cargar_fact_desvio_pronostico():

        engine = get_engine()

        query_fechas = text("""
            SELECT DISTINCT p.id_provincia, p.fecha_pronostico
            FROM silver.clima_pronostico p
            WHERE EXISTS (
                SELECT 1 FROM silver.clima_actual a
                WHERE a.id_provincia = p.id_provincia
                  AND DATE(a.fecha_hora) = p.fecha_pronostico
            )
            ORDER BY p.fecha_pronostico
        """)

        query_delete = text("""
            DELETE FROM gold.fact_desvio_pronostico
            WHERE id_provincia  = :id_provincia
              AND fecha_evaluada = :fecha
        """)

        query_insert = text("""
            INSERT INTO gold.fact_desvio_pronostico (
                id_provincia,
                fecha_evaluada,
                temp_max_pronosticada,
                temp_max_real,
                error_max_c,
                lluvio_pronostico,
                lluvio_real,
                acierto_lluvia,
                registro_at
            )
            SELECT
                p.id_provincia,
                p.fecha_pronostico                              AS fecha_evaluada,
                p.temp_max_c                                    AS temp_max_pronosticada,
                MAX(a.temperatura_c)                            AS temp_max_real,
                ROUND(ABS(p.temp_max_c - MAX(a.temperatura_c))
                      ::NUMERIC, 2)                             AS error_max_c,
                (p.lluvia_acumulada_mm > 0
                 OR p.precipitacion_prob_pct >= 50)             AS lluvio_pronostico,
                (SUM(a.lluvia_mm) > 0)                          AS lluvio_real,
                (p.lluvia_acumulada_mm > 0
                 OR p.precipitacion_prob_pct >= 50)
                = (SUM(a.lluvia_mm) > 0)                        AS acierto_lluvia,
                NOW()                                           AS registro_at
            FROM silver.clima_pronostico p
            JOIN silver.clima_actual a
              ON a.id_provincia   = p.id_provincia
             AND DATE(a.fecha_hora) = p.fecha_pronostico
            WHERE p.id_provincia    = :id_provincia
              AND p.fecha_pronostico = :fecha
            GROUP BY
                p.id_provincia, p.fecha_pronostico,
                p.temp_max_c, p.lluvia_acumulada_mm,
                p.precipitacion_prob_pct
        """)

        with engine.begin() as conn:
            pares = conn.execute(query_fechas).fetchall()
            total = 0
            for prov, fecha in pares:
                conn.execute(query_delete, {
                    "id_provincia": prov,
                    "fecha":        fecha,
                })
                result = conn.execute(query_insert, {
                    "id_provincia": prov,
                    "fecha":        fecha,
                })
                total += result.rowcount

        logging.info(
            f"fact_desvio_pronostico → {total} filas para "
            f"{len(pares)} combinaciones provincia/fecha"
        )

    prov  = cargar_dim_provincia()
    wcode = cargar_dim_weather_code()
    tiemp = cargar_dim_tiempo()
    fact  = cargar_fact_clima_diario()
    desv  = cargar_fact_desvio_pronostico()

    prov  >> tiemp
    [tiemp, wcode] >> fact
    tiemp >> desv


open_meteo_gold_dag = open_meteo_pipeline_gold()