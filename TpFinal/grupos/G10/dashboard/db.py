
import os
from contextlib import closing

import pandas as pd
import psycopg2


def conectar_warehouse():
    return psycopg2.connect(
        host=os.environ["WAREHOUSE_HOST"],
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
        port=5432,
        connect_timeout=10
    )


def obtener_pronosticos():

    sql = """
        SELECT
            c.ciudad_id,
            c.ciudad,
            c.latitud,
            c.longitud,

            f.fecha_pronostico,

            d.anio,
            d.mes,
            d.dia,
            d.dia_semana,

            f.temperatura_max,
            f.temperatura_min,
            f.probabilidad_lluvia,
            f.precipitacion_mm,
            f.weather_code,

            f.nivel_alerta_lluvia,
            f.incentivo_lluvia,

            f.nivel_alerta_calor,
            f.incentivo_calor,

            f.nivel_alerta,
            f.incentivo_recomendado,

            f.ingested_at

        FROM gold.fact_alertas_incentivos AS f

        INNER JOIN gold.dim_ciudad AS c
            ON f.ciudad_id = c.ciudad_id

        INNER JOIN gold.dim_fecha AS d
            ON f.fecha_pronostico = d.fecha

        ORDER BY
            f.fecha_pronostico,
            c.ciudad;
    """

    with closing(conectar_warehouse()) as conexion:
        with conexion.cursor() as cursor:

            cursor.execute(sql)

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            registros = cursor.fetchall()

    df = pd.DataFrame(
        registros,
        columns=columnas
    )

    # Preparar las fechas para los filtros y gráficos

    df["fecha_pronostico"] = pd.to_datetime(
        df["fecha_pronostico"]
    )

    df["ingested_at"] = pd.to_datetime(
        df["ingested_at"],
        utc=True
    )

    # Convertir valores NUMERIC de PostgreSQL
    # a valores compatibles con los gráficos

    columnas_numericas = [
        "latitud",
        "longitud",
        "temperatura_max",
        "temperatura_min",
        "probabilidad_lluvia",
        "precipitacion_mm",
        "incentivo_lluvia",
        "incentivo_calor",
        "incentivo_recomendado"
    ]

    for columna in columnas_numericas:
        df[columna] = pd.to_numeric(
            df[columna],
            errors="raise"
        )

    return df
