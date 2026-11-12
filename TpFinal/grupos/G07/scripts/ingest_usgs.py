import json
import os
from urllib.request import urlopen

import psycopg2

URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_month.geojson"

def obtener_sismos():
    with urlopen(URL, timeout=30) as respuesta:
        return json.load(respuesta)

def guardar_sismos(datos):
    dsn = os.environ["USGS_DB_DSN"]

    insertados = 0

    with psycopg2.connect(dsn) as conexion:
        with conexion.cursor() as cursor:
            for sismo in datos["features"]:
                event_id = sismo["id"]
                updated = sismo["properties"]["updated"]

                cursor.execute("""
                    INSERT INTO bronze.sismos_raw
                        (event_id, payload, source_updated_ms)
                    SELECT %s, %s::jsonb, %s
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM bronze.sismos_raw
                        WHERE event_id = %s
                          AND source_updated_ms = %s
                    )
                """, (
                    event_id,
                    json.dumps(sismo),
                    updated,
                    event_id,
                    updated
                ))

                insertados += cursor.rowcount

    return insertados

if __name__ == "__main__":
    datos = obtener_sismos()

    print("Sismos obtenidos:", len(datos["features"]))

    insertados = guardar_sismos(datos)

    print("Registros nuevos guardados en Bronze:", insertados)