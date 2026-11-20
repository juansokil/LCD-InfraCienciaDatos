"""
Conexion al warehouse, compartida por los tres DAGs.

Usamos psycopg2 directo (sin pandas ni SQLAlchemy): las transformaciones son
SQL que corre ADENTRO de Postgres, asi que Python solo manda el texto y lee
algun conteo para el log.
"""

import os
from contextlib import contextmanager

import psycopg2


def _params() -> dict:
    return {
        "host": os.getenv("SOURCE_DB_HOST", "data_warehouse"),
        "port": 5432,
        "user": os.getenv("SOURCE_DB_USER", "admin"),
        "password": os.getenv("SOURCE_DB_PASS", "admin"),
        "dbname": os.getenv("SOURCE_DB_NAME", "sismos"),
    }


@contextmanager
def transaccion():
    """Abre una conexion y devuelve un cursor dentro de UNA transaccion.

    Si algo falla adentro del `with`, se hace ROLLBACK de todo: nunca queda
    una capa a medio escribir. Si sale bien, COMMIT al final.
    """
    conn = psycopg2.connect(**_params())
    try:
        with conn:                 # commit al salir OK / rollback si hay excepcion
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


def ejecutar(sql: str) -> None:
    """Ejecuta un script SQL (puede tener varias sentencias) en una transaccion."""
    with transaccion() as cur:
        cur.execute(sql)


def valor(sql: str):
    """Devuelve el primer valor de la primera fila (para conteos y controles)."""
    with transaccion() as cur:
        cur.execute(sql)
        fila = cur.fetchone()
        return fila[0] if fila else None
