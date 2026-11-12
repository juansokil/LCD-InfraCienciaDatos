"""
DAG: citybikes_silver
Bronze -> Silver de CityBikes: limpieza, tipado, contrato y cuarentena.

    bronze.citybikes_stations -> silver.citybikes_stations             (validas, tipadas)
                              -> silver.quarantine_citybikes_stations  (rechazadas + motivo)
                              -> silver.quality_runs                   (una fila por regla y corrida)
    bronze.citybikes_networks -> silver.citybikes_networks
    coordenadas + data/geo    -> silver.citybikes_station_zone         (zona por estacion)

Sigue el molde de `crypto_silver` (clase 04): arranca cuando bronze emite su
asset, normaliza y deduplica en SQL, valida fila a fila con Pydantic generado
desde el contrato, aplica las `quality_rules` al lote (error -> cuarentena,
warning -> `_quality_flags`) y carga con DELETE + append.

Tres diferencias deliberadas con el DAG de clase:

1. La ventana es por SNAPSHOT, no por dia. Son ~489 estaciones cada 5 minutos
   (~141.000 filas por dia): reprocesar el dia entero en cada corrida no escala.
   Cada run procesa los snapshots PENDIENTES: los que estan en bronze y todavia
   no en silver ni en cuarentena.
2. Las filas no viajan por XCom. Entre tareas pasan solo la lista de snapshots
   y los conteos; los datos no salen de Postgres (como en bronze, que pasa
   rutas y no payloads).
3. Las tablas se crean con DDL explicito y tipado. Bronze guarda todo como
   texto, y una columna que llega siempre nula (ebikes) pandas la crearia mal.

Linaje hacia bronze: `_source_table` + `snapshot_ts` + `ingested_at`.

Reprocesar historia: borrar esos snapshots de silver y de cuarentena. La
corrida siguiente los vuelve a levantar (dentro de la ventana de 48 horas).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException, AirflowSkipException

try:  # Airflow 3.x
    from airflow.sdk import get_current_context
except ImportError:  # fallback Airflow 2.x
    from airflow.operators.python import get_current_context  # noqa: E402

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_CITYBIKES, SILVER_CITYBIKES  # noqa: E402
from common.contracts import (  # noqa: E402
    build_pydantic_from_contract,
    evaluar_reglas,
    load_contract,
    motivo_rechazo,
)
from common.derivadas import DERIVADAS, TZ_LOCAL, nombre_estacion, sql_derivadas  # noqa: E402
from common.zonas import cargar_capas, zona_de  # noqa: E402


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'CityBikes')}"
)

DATA_DIR = Path("/opt/airflow/data")
CONTRACT_PATH = DATA_DIR / "contracts" / "citybikes_stations.yaml"
GEO_DIR = DATA_DIR / "geo"  # capas de common/zonas.py

# Grano de silver: una fila por estacion y snapshot.
CLAVES = ["network_id", "station_id", "snapshot_ts"]

# Tipo del contrato -> tipo de Postgres.
PG_TYPES = {
    "string": "text",
    "integer": "integer",
    "numeric": "double precision",
    "float": "double precision",
    "boolean": "boolean",
    "timestamp": "timestamptz",
    "date": "date",
}

# Hasta cuanto para atras se buscan snapshots pendientes, y cuantos por corrida.
# Con tope, un atraso largo se drena de a poco en vez de llegar todo junto.
VENTANA_HORAS = 48
MAX_SNAPSHOTS = 12

# Filtro comun: los snapshots de este run. El CAST es obligatorio: psycopg2
# manda la lista como text[] y Postgres no sabe comparar timestamptz con text.
EN_SNAPSHOTS = "snapshot_ts = ANY(CAST(:snaps AS timestamptz[]))"

# Reparacion de timestamps. Viajan como PARAMETROS de la consulta y no pegados
# en el SQL: asi ningun escape de Python (\1, {2} en un f-string, %) los rompe.
#   re_offset_y_z: la API manda "...+00:00Z" (offset Y Z). Solo si el offset es
#                  cero se quita la Z; "-03:00Z" es ambiguo y lo decide Pydantic.
#   re_sin_zona:   `last_updated` viene sin zona y esta en UTC.
REPARACION = {
    "re_offset_y_z": "T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?[+-]00:?00Z$",
    "re_sin_zona": "^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?$",
    "utc": "+00:00",
}

# Snapshots pendientes: los de bronze cuyo ingested_at mas reciente no coincide
# con el de silver + cuarentena, o que tienen derivadas sin calcular. Casos:
#   - snapshot nuevo (no esta en silver),
#   - corrida de silver que fallo (nunca llego),
#   - bronze re-corrido (bronze reemplaza por run_id y cambia su ingested_at).
# Cuarentena cuenta como "procesado": si no, un snapshot rechazado entero se
# reprocesaria en cada corrida para siempre.
SQL_PENDIENTES = """
    WITH b AS (
        SELECT snapshot_ts, max(ingested_at) AS ing
        FROM bronze.citybikes_stations
        WHERE snapshot_ts >= now() - make_interval(hours => :horas)
        GROUP BY snapshot_ts
    ),
    s AS (
        SELECT snapshot_ts, max(ingested_at) AS ing
        FROM (
            SELECT snapshot_ts, ingested_at FROM silver.citybikes_stations
            WHERE snapshot_ts >= now() - make_interval(hours => :horas)
            UNION ALL
            SELECT snapshot_ts, ingested_at FROM silver.quarantine_citybikes_stations
            WHERE snapshot_ts >= now() - make_interval(hours => :horas)
        ) u
        GROUP BY snapshot_ts
    )
    SELECT b.snapshot_ts
    FROM b
    LEFT JOIN s USING (snapshot_ts)
    WHERE s.ing IS DISTINCT FROM b.ing
       -- Cuarto caso: snapshot cargado antes de que existieran las columnas
       -- derivadas (el ALTER las deja en NULL). Se reprocesa una sola vez.
       OR EXISTS (
            SELECT 1 FROM silver.citybikes_stations x
            WHERE x.snapshot_ts = b.snapshot_ts AND x.snapshot_local IS NULL
       )
    ORDER BY b.snapshot_ts DESC
    LIMIT :tope
"""


# =============================================================================
# Helpers (sin I/O: el contrato se lee adentro de las tareas, no al importar)
# =============================================================================

def _tipo_pg(col: dict) -> str:
    if col["type"] not in PG_TYPES:
        raise ValueError(f"tipo '{col['type']}' sin equivalente en Postgres ({col['name']})")
    return PG_TYPES[col["type"]]


def _limpio(columna: str) -> str:
    """trim + vacio -> NULL. No toca mayusculas: un nombre propio se respeta.

    Los identificadores van SIEMPRE entre comillas dobles: `returning` es
    palabra reservada en Postgres.
    """
    return f"""NULLIF(btrim(b."{columna}"), '')"""


def _expr_lectura(col: dict) -> str:
    """Como se lee UNA columna del contrato desde bronze, ya normalizada."""
    nombre = col["name"]
    if nombre in CLAVES:
        # Las claves van crudas. Si se limpiaran, DISTINCT ON juntaria todos los
        # ids vacios en una sola fila y el resto no llegaria ni a cuarentena.
        return f'b."{nombre}"'
    limpio = _limpio(nombre)
    if col["type"] == "timestamp":
        return (
            f"CASE WHEN {limpio} ~ :re_offset_y_z THEN left({limpio}, -1)"
            f" WHEN {limpio} ~ :re_sin_zona THEN {limpio} || :utc"
            f" ELSE {limpio} END"
        )
    return limpio


def _sql_lectura(contract: dict) -> str:
    """SELECT de bronze: normalizado y deduplicado en Postgres (pushdown).

    DISTINCT ON (clave) + ORDER BY ... ingested_at DESC = una fila por
    estacion y snapshot, la de carga mas reciente.
    """
    columnas = ",\n               ".join(
        f'{_expr_lectura(c)} AS "{c["name"]}"' for c in contract["schema"]
    )
    return f"""
        SELECT DISTINCT ON (b.network_id, b.station_id, b.snapshot_ts)
               {columnas},
               b.ingested_at AS "ingested_at"
        FROM bronze.citybikes_stations b
        WHERE b.{EN_SNAPSHOTS}
        ORDER BY b.network_id, b.station_id, b.snapshot_ts, b.ingested_at DESC
    """


def _a_utc(valor):
    """Fechas a UTC con zona. Una fecha sin zona, al insertarla en timestamptz,
    se interpretaria en la zona de la sesion."""
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)
    return valor


def _guardar_metricas(conn, run_ts, ds, contract: dict, mediciones: list) -> None:
    """Una fila por (corrida x regla) en silver.quality_runs. APPEND-ONLY.

    Recibe la conexion: escribe en la MISMA transaccion que los datos. Si la
    carga falla, las metricas tampoco quedan (y un reintento no las duplica).

    Una regla con 0 violaciones sobre 489 filas evaluadas ES informacion: sin
    esto, "la cuarentena esta vacia" no distingue "todo bien" de "no se valido".
    """
    import pandas as pd

    filas = [{
        "run_ts": run_ts,  # el mismo para todas las reglas de la corrida
        "ds": ds,
        "dataset": contract["dataset"],
        "contract_version": str(contract["version"]),
        "regla": m["nombre"],
        "tipo": m["rule"],
        "severidad": m["severidad"],
        "filas_evaluadas": m["filas"],
        "violaciones": m["violaciones"],
    } for m in mediciones]
    pd.DataFrame(filas).to_sql("quality_runs", conn, schema="silver",
                               if_exists="append", index=False)


# =============================================================================
# DAG
# =============================================================================

@dag(
    dag_id="citybikes_silver",
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    start_date=datetime(2026, 10, 1),
    # DATA-AWARE: sin cron. Arranca cuando cargar_bronze termina y emite su asset.
    # Si bronze falla, silver no corre.
    schedule=[BRONZE_CITYBIKES],
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["silver", "citybikes"],
    doc_md=__doc__,
)
def citybikes_silver():

    @task
    def crear_tablas():
        """DDL idempotente. Los schemas los crea init.sql; las tablas, el DAG.

        Las columnas salen del `schema` del contrato: en silver con su tipo, en
        cuarentena como texto (ahi la fila se guarda sin tipar).
        """
        import sqlalchemy

        contract = load_contract(CONTRACT_PATH)
        esquema = contract["schema"]

        tipadas = ",\n".join(f'"{c["name"]}" {_tipo_pg(c)}' for c in esquema)
        derivadas = ",\n".join(f'"{c}" {t}' for c, t in DERIVADAS.items())
        en_texto = ",\n".join(
            f'"{c["name"]}" ' + ("timestamptz NOT NULL" if c["name"] == "snapshot_ts" else "text")
            for c in esquema
        )

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(f"""
                CREATE TABLE IF NOT EXISTS silver.citybikes_stations (
                    {tipadas},
                    {derivadas},
                    ingested_at        timestamptz NOT NULL,
                    _quality_flags     text        NOT NULL DEFAULT '',
                    _processed_at      timestamptz NOT NULL,
                    _source_table      text        NOT NULL,
                    _contract_version  text        NOT NULL,
                    PRIMARY KEY (snapshot_ts, network_id, station_id)
                );
            """))
            conn.execute(sqlalchemy.text(f"""
                CREATE TABLE IF NOT EXISTS silver.quarantine_citybikes_stations (
                    {en_texto},
                    ingested_at        timestamptz NOT NULL,
                    quarantine_reason  text        NOT NULL,
                    _processed_at      timestamptz NOT NULL,
                    _source_table      text        NOT NULL,
                    _contract_version  text        NOT NULL
                );
            """))
            conn.execute(sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_silver_cb_q_snapshot "
                "ON silver.quarantine_citybikes_stations (snapshot_ts);"
            ))
            conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS silver.quality_runs (
                    run_ts            timestamptz NOT NULL,
                    ds                date        NOT NULL,
                    dataset           text        NOT NULL,
                    contract_version  text        NOT NULL,
                    regla             text        NOT NULL,
                    tipo              text        NOT NULL,
                    severidad         text        NOT NULL,
                    filas_evaluadas   integer     NOT NULL,
                    violaciones       integer     NOT NULL
                );
            """))
            conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS silver.citybikes_networks (
                    network_id     text             NOT NULL,
                    name           text,
                    city           text,
                    country        text,
                    latitude       double precision,
                    longitude      double precision,
                    company_json   text,
                    gbfs_href      text,
                    station_count  integer,
                    snapshot_ts    timestamptz      NOT NULL,
                    ingested_at    timestamptz      NOT NULL,
                    _processed_at  timestamptz      NOT NULL,
                    _source_table  text             NOT NULL,
                    PRIMARY KEY (snapshot_ts, network_id)
                );
            """))

            conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS silver.citybikes_station_zone (
                    network_id     text             NOT NULL,
                    station_id     text             NOT NULL,
                    latitude       double precision NOT NULL,
                    longitude      double precision NOT NULL,
                    ciudad         text,
                    zona           text             NOT NULL,
                    zona_padre     text,
                    zona_nivel     text             NOT NULL,
                    capa           text             NOT NULL,
                    snapshot_ts    timestamptz,
                    _processed_at  timestamptz      NOT NULL,
                    PRIMARY KEY (network_id, station_id)
                );
            """))
            # Agregada despues de la primera version de la tabla.
            conn.execute(sqlalchemy.text(
                "ALTER TABLE silver.citybikes_station_zone "
                "ADD COLUMN IF NOT EXISTS snapshot_ts timestamptz"
            ))

            # EVOLUCION DE ESQUEMA (el contrato permite allow_new_columns).
            # CREATE TABLE IF NOT EXISTS no agrega columnas a una tabla que ya
            # existe. Se mira el catalogo y se agregan SOLO las que faltan: un
            # ALTER en cada corrida pediria un lock exclusivo cada 5 minutos.
            for tabla, con_tipo in (("citybikes_stations", True),
                                    ("quarantine_citybikes_stations", False)):
                existentes = {fila[0] for fila in conn.execute(sqlalchemy.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'silver' AND table_name = :tabla"
                ), {"tabla": tabla})}
                columnas = [(c["name"], _tipo_pg(c) if con_tipo else "text") for c in esquema]
                if con_tipo:
                    # Las derivadas solo existen en silver: la cuarentena guarda
                    # la fila como llego, sin calculos.
                    columnas += list(DERIVADAS.items())
                for nombre, tipo in columnas:
                    if nombre in existentes:
                        continue
                    conn.execute(sqlalchemy.text(
                        f'ALTER TABLE silver.{tabla} ADD COLUMN "{nombre}" {tipo}'
                    ))
                    print(f"[schema] silver.{tabla}: + {nombre} {tipo}")

    @task
    def snapshots_del_run() -> list[str]:
        """Que procesa este run, resuelto UNA sola vez y pasado como parametro.

        No se usa "los eventos que dispararon el run": Airflow entrega cada
        evento de asset una sola vez, asi que si una corrida falla esos
        snapshots no vuelven a llegar. Aca se compara el ESTADO (lo que hay en
        bronze contra lo que hay en silver) y lo que falto se levanta solo.
        """
        import sqlalchemy

        ctx = get_current_context()
        # Solo informativo. En una corrida manual no hay eventos: se pregunta al
        # accesor de Airflow solo si trae algo (un dict comun no puede usar un
        # Asset como clave, no es hasheable).
        disparadores = ctx.get("triggering_asset_events")
        eventos = disparadores.get(BRONZE_CITYBIKES, []) if disparadores else []
        print(f"Disparado por {len(eventos)} evento(s) de bronze: "
              f"{sorted({e.source_run_id for e in eventos})}")

        tipo_run = getattr(ctx.get("dag_run"), "run_type", None)
        es_manual = getattr(tipo_run, "value", tipo_run) == "manual"

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.connect() as conn:
            hay_bronze = conn.execute(sqlalchemy.text(
                "SELECT to_regclass('bronze.citybikes_stations')"
            )).scalar()
            if hay_bronze is None:
                # Tarea salteada = no emite el asset = gold tampoco corre.
                raise AirflowSkipException("bronze todavia no cargo nada")

            pendientes = [fila[0] for fila in conn.execute(
                sqlalchemy.text(SQL_PENDIENTES),
                {"horas": VENTANA_HORAS, "tope": MAX_SNAPSHOTS},
            )]
            if not pendientes and es_manual:
                # Corrida manual sin nada pendiente: se reprocesa el ultimo
                # snapshot. Sirve para comprobar la idempotencia a mano.
                ultimo = conn.execute(sqlalchemy.text(
                    "SELECT max(snapshot_ts) FROM bronze.citybikes_stations"
                )).scalar()
                pendientes = [ultimo] if ultimo else []

        if not pendientes:
            raise AirflowSkipException("silver ya esta al dia con bronze")

        snapshots = sorted(ts.astimezone(timezone.utc).isoformat() for ts in pendientes)
        print(f"Snapshots de este run ({len(snapshots)}): {snapshots[0]} .. {snapshots[-1]}")
        return snapshots

    @task
    def evaluar_calidad(snapshots: list[str]):
        """Chequeo de bronze ANTES de limpiar. Solo reporta, no modifica ni frena.

        Se calcula en Postgres con un agregado: los duplicados se cuentan sobre
        bronze crudo (despues del DISTINCT ON siempre darian 0), y la
        completitud solo sobre las columnas obligatorias del contrato (ebikes
        llega siempre nula y es legitimo).
        """
        import sqlalchemy

        contract = load_contract(CONTRACT_PATH)
        obligatorias = [
            c["name"] for c in contract["schema"]
            if not c.get("nullable", False) and c["name"] != "snapshot_ts"
        ]
        completitud = ",\n                   ".join(
            f'100.0 * count({_limpio(c)}) / NULLIF(count(*), 0) AS "{c}"' for c in obligatorias
        )

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.connect() as conn:
            fila = conn.execute(sqlalchemy.text(f"""
                SELECT count(*) AS filas,
                       count(*) - count(DISTINCT (b.network_id, b.station_id, b.snapshot_ts)) AS duplicados,
                       {completitud}
                FROM bronze.citybikes_stations b
                WHERE b.{EN_SNAPSHOTS}
            """), {"snaps": snapshots}).mappings().one()
            redes = conn.execute(sqlalchemy.text(f"""
                SELECT b.snapshot_ts, array_agg(DISTINCT b.network_id) AS llegaron
                FROM bronze.citybikes_stations b
                WHERE b.{EN_SNAPSHOTS}
                GROUP BY b.snapshot_ts
                ORDER BY b.snapshot_ts
            """), {"snaps": snapshots}).all()

        por_columna = {c: float(fila[c] or 0) for c in obligatorias}
        score = sum(por_columna.values()) / max(len(por_columna), 1)

        print("=== Reporte de Calidad (bronze, antes de limpiar) ===")
        print(f"Filas: {fila['filas']} en {len(snapshots)} snapshot(s)")
        print(f"Completitud promedio: {score:.1f}%")
        for columna, pct in por_columna.items():
            if pct < 100:
                print(f"   {columna}: {pct:.1f}%")
        print(f"Duplicados: {fila['duplicados']}")

        esperadas = set(contract["delivery"]["networks"])
        for ts, llegaron in redes:
            faltan = sorted(esperadas - set(llegaron))
            if faltan:
                print(f"   {ts:%Y-%m-%d %H:%M} sin datos de: {faltan}")

        if score >= 95:
            print("-> PROCESS_TO_SILVER")
        elif score >= 85:
            print("-> PROCESS_WITH_WARNING")
        else:
            print("-> HALT_AND_ALERT")

    @task
    def cargar_redes(snapshots: list[str]):
        """bronze.citybikes_networks -> silver.citybikes_networks, en SQL puro.

        Las redes no tienen contrato: se tipan con un CAST protegido por regex,
        asi un valor raro queda en NULL en vez de voltear la tarea. Corre ANTES
        de limpiar_y_cargar para que gold encuentre las redes cuando llega el
        asset.
        """
        import sqlalchemy

        params = {
            "snaps": snapshots,
            "procesado": datetime.now(timezone.utc),
            "re_decimal": "^-?[0-9]+([.][0-9]+)?$",
            "re_entero": "^[0-9]+$",
        }
        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:  # todo o nada
            conn.execute(sqlalchemy.text(
                f"DELETE FROM silver.citybikes_networks WHERE {EN_SNAPSHOTS}"
            ), params)
            cargadas = conn.execute(sqlalchemy.text(f"""
                INSERT INTO silver.citybikes_networks (
                    network_id, name, city, country, latitude, longitude,
                    company_json, gbfs_href, station_count,
                    snapshot_ts, ingested_at, _processed_at, _source_table
                )
                SELECT DISTINCT ON (b.network_id, b.snapshot_ts)
                       b.network_id,
                       NULLIF(btrim(b.name), ''),
                       NULLIF(btrim(b.city), ''),
                       upper(NULLIF(btrim(b.country), '')),
                       CASE WHEN btrim(b.latitude) ~ :re_decimal
                            THEN CAST(btrim(b.latitude) AS double precision) END,
                       CASE WHEN btrim(b.longitude) ~ :re_decimal
                            THEN CAST(btrim(b.longitude) AS double precision) END,
                       NULLIF(btrim(b.company_json), ''),
                       NULLIF(btrim(b.gbfs_href), ''),
                       CASE WHEN btrim(b.station_count) ~ :re_entero
                            THEN CAST(btrim(b.station_count) AS integer) END,
                       b.snapshot_ts,
                       b.ingested_at,
                       :procesado,
                       'bronze.citybikes_networks'
                FROM bronze.citybikes_networks b
                WHERE b.{EN_SNAPSHOTS}
                  AND b.network_id IS NOT NULL
                ORDER BY b.network_id, b.snapshot_ts, b.ingested_at DESC
            """), params).rowcount
        print(f"silver.citybikes_networks: +{cargadas} redes en {len(snapshots)} snapshot(s)")

    @task
    def asignar_zonas(snapshots: list[str]):
        """Zona de cada estacion por coordenadas -> silver.citybikes_station_zone.

        Una fila por estacion (no por snapshot: las estaciones no se mueven).
        Se recalculan todas las del run, pero solo se escribe la que es nueva
        o cambio (se movio, o se agrego una capa para su red). Corre ANTES de
        limpiar_y_cargar, igual que cargar_redes, para que gold encuentre la
        zona de una estacion nueva cuando llega el asset.
        """
        import sqlalchemy

        params = {"snaps": snapshots, "re_decimal": "^-?[0-9]+([.][0-9]+)?$"}
        engine = sqlalchemy.create_engine(DB_URI)
        with engine.connect() as conn:
            # Ultima posicion conocida de cada estacion del run. Las coordenadas
            # que no son numeros no tienen zona posible y se saltean (esas filas
            # van a cuarentena en limpiar_y_cargar). Una coordenada numerica
            # pero absurda cae afuera de los poligonos y queda con la ciudad.
            estaciones = conn.execute(sqlalchemy.text(f"""
                SELECT DISTINCT ON (b.network_id, b.station_id)
                       b.network_id, b.station_id, b.snapshot_ts,
                       CAST(btrim(b.latitude) AS double precision)  AS latitude,
                       CAST(btrim(b.longitude) AS double precision) AS longitude,
                       (SELECT NULLIF(btrim(n.city), '') FROM bronze.citybikes_networks n
                         WHERE n.network_id = b.network_id
                         ORDER BY n.snapshot_ts DESC LIMIT 1)       AS ciudad
                FROM bronze.citybikes_stations b
                WHERE b.{EN_SNAPSHOTS}
                  AND btrim(b.latitude) ~ :re_decimal
                  AND btrim(b.longitude) ~ :re_decimal
                ORDER BY b.network_id, b.station_id, b.snapshot_ts DESC, b.ingested_at DESC
            """), params).mappings().all()

        capas = cargar_capas(GEO_DIR)
        procesado = datetime.now(timezone.utc)
        filas = [
            {**e, **zona_de(capas, e["network_id"], e["latitude"], e["longitude"], e["ciudad"]),
             "procesado": procesado}
            for e in estaciones
        ]
        sin_poligono = sum(f["capa"] == "fallback" and f["network_id"] in capas for f in filas)

        if not filas:
            print("[zonas] sin estaciones con coordenadas validas en este run")
            return

        with engine.begin() as conn:
            escritas = conn.execute(sqlalchemy.text("""
                INSERT INTO silver.citybikes_station_zone AS z (
                    network_id, station_id, latitude, longitude, ciudad,
                    zona, zona_padre, zona_nivel, capa, snapshot_ts, _processed_at
                ) VALUES (
                    :network_id, :station_id, :latitude, :longitude, :ciudad,
                    :zona, :zona_padre, :zona_nivel, :capa, :snapshot_ts, :procesado
                )
                ON CONFLICT (network_id, station_id) DO UPDATE SET
                    latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
                    ciudad = EXCLUDED.ciudad, zona = EXCLUDED.zona,
                    zona_padre = EXCLUDED.zona_padre, zona_nivel = EXCLUDED.zona_nivel,
                    capa = EXCLUDED.capa, snapshot_ts = EXCLUDED.snapshot_ts,
                    _processed_at = EXCLUDED._processed_at
                -- Solo si cambio algo Y la posicion no es mas vieja que la
                -- guardada: el atraso se drena del snapshot mas nuevo al mas
                -- viejo, y uno viejo no tiene que pisar una reubicacion.
                -- (snapshot_ts NULL = fila de antes de que existiera la columna).
                WHERE z.snapshot_ts IS NULL
                   OR EXCLUDED.snapshot_ts >= z.snapshot_ts
                  AND (z.latitude, z.longitude, z.ciudad, z.zona, z.zona_padre, z.zona_nivel, z.capa)
                      IS DISTINCT FROM
                      (EXCLUDED.latitude, EXCLUDED.longitude, EXCLUDED.ciudad, EXCLUDED.zona,
                       EXCLUDED.zona_padre, EXCLUDED.zona_nivel, EXCLUDED.capa)
            """), filas).rowcount

        print(f"[zonas] {len(filas)} estaciones evaluadas | {escritas} nuevas o cambiadas | "
              f"{sin_poligono} fuera de los poligonos de su red")

    @task(outlets=[SILVER_CITYBIKES])
    def limpiar_y_cargar(snapshots: list[str]) -> dict:
        """Lee bronze limpio, valida contra el contrato y carga silver + cuarentena.

        El asset se emite ACA, en la tarea que escribe el dato: lo que se
        publica es "silver tiene datos nuevos", no "el DAG termino".
        """
        import pandas as pd
        import sqlalchemy
        from pydantic import ValidationError

        contract = load_contract(CONTRACT_PATH)
        Contrato = build_pydantic_from_contract(contract)
        campos = list(Contrato.model_fields)
        version = str(contract["version"])
        procesado = datetime.now(timezone.utc)
        ds = datetime.fromisoformat(max(snapshots)).date()
        print(f"[contract] {contract['dataset']} v{version}: {len(campos)} columnas")

        engine = sqlalchemy.create_engine(DB_URI)

        # --- 1. LEER: normalizado y deduplicado en SQL ---
        # .mappings() devuelve tipos nativos (str, None, datetime con zona).
        with engine.connect() as conn:
            crudas = [dict(fila) for fila in conn.execute(
                sqlalchemy.text(_sql_lectura(contract)),
                {"snaps": snapshots, **REPARACION},
            ).mappings()]
        if not crudas:
            raise AirflowSkipException("bronze no tiene filas para estos snapshots")

        # --- 2. VALIDAR Y TIPAR fila a fila ---
        # Pydantic valida y convierte a la vez: de bronze llega "12" y sale 12.
        # La que pasa va tipada a silver. La que no, va a cuarentena EN TEXTO,
        # sin tipar: se ve el valor que no se pudo convertir ("abc", "123.4").
        # Es el texto ya recortado por el SELECT; el crudo exacto sigue en bronze.
        tipadas, origen, rechazadas = [], [], []
        for fila in crudas:
            try:
                modelo = Contrato(**{c: fila[c] for c in campos})
            except ValidationError as error:
                rechazadas.append({**fila, "quarantine_reason": motivo_rechazo(error)})
                continue
            valores = {c: _a_utc(v) for c, v in modelo.model_dump().items()}
            numero, nombre = nombre_estacion(valores["name"])
            tipadas.append({
                **valores,
                "ingested_at": fila["ingested_at"],
                # Derivadas que necesitan Python (regex). El resto las calcula
                # Postgres despues de cargar (paso 4).
                "station_number": numero,
                "station_name": nombre,
            })
            origen.append(fila)  # misma posicion que en `tipadas`
        rechazos_contrato = len(rechazadas)

        # --- 3. REGLAS DEL LOTE: lo que una fila sola no puede ver ---
        # Se evaluan sobre el lote YA TIPADO: sobre texto, in_set [true]
        # marcaria todas las filas. dtype=object evita que un entero con nulos
        # se convierta en float con NaN.
        df = pd.DataFrame(tipadas, columns=campos + ["ingested_at", "station_number",
                                                     "station_name"], dtype=object)
        resultados = evaluar_reglas(df, contract)

        rechaza = pd.Series(False, index=df.index, dtype=bool)
        motivos = pd.Series("", index=df.index, dtype=object)
        flags = pd.Series("", index=df.index, dtype=object)
        if not df.empty:
            for res in resultados:
                marca = res["nombre"] + ";"
                if res["severidad"] == "error":
                    # error -> cuarentena: el registro no sirve.
                    rechaza |= res["mask"]
                    motivos = motivos.where(~res["mask"], motivos + marca)
                else:
                    # warning -> pasa marcado: usable pero sospechoso.
                    flags = flags.where(~res["mask"], flags + marca)

        for i in df.index[rechaza]:
            rechazadas.append({
                **origen[i],
                "quarantine_reason": "QualityRule: " + motivos[i].rstrip(";"),
            })

        df_silver = df[~rechaza].copy()
        df_silver["_quality_flags"] = flags[~rechaza].str.rstrip(";")
        df_cuarentena = pd.DataFrame(
            rechazadas, columns=campos + ["ingested_at", "quarantine_reason"], dtype=object
        )
        for tabla in (df_silver, df_cuarentena):
            tabla["_processed_at"] = procesado
            tabla["_source_table"] = "bronze.citybikes_stations"
            tabla["_contract_version"] = version

        # Los rechazos de Pydantic tambien se miden, como una regla mas.
        mediciones = [{
            "nombre": "contrato_pydantic", "rule": "schema", "severidad": "error",
            "filas": len(crudas), "violaciones": rechazos_contrato,
        }, *resultados]

        # --- 4. CARGAR: una sola transaccion, todo o nada ---
        # DELETE de los snapshots del run + append = idempotente por snapshot:
        # correrlo 1 o 10 veces deja lo mismo y no toca los demas snapshots.
        with engine.begin() as conn:
            for tabla in ("silver.citybikes_stations", "silver.quarantine_citybikes_stations"):
                conn.execute(sqlalchemy.text(f"DELETE FROM {tabla} WHERE {EN_SNAPSHOTS}"),
                             {"snaps": snapshots})
            if not df_silver.empty:
                df_silver.to_sql("citybikes_stations", conn, schema="silver",
                                 if_exists="append", index=False, method="multi", chunksize=1000)
                # Derivadas aritmeticas: las calcula Postgres sobre lo recien
                # cargado, en la misma transaccion (nunca quedan filas sin ellas).
                conn.execute(sqlalchemy.text(sql_derivadas("silver.citybikes_stations",
                                                           EN_SNAPSHOTS)),
                             {"snaps": snapshots, "tz_local": TZ_LOCAL})
            if not df_cuarentena.empty:
                df_cuarentena.to_sql("quarantine_citybikes_stations", conn, schema="silver",
                                     if_exists="append", index=False, method="multi", chunksize=1000)
            _guardar_metricas(conn, procesado, ds, contract, mediciones)

        conteos = {
            "snapshots": len(snapshots),
            "leidas": len(crudas),
            "silver": int(len(df_silver)),
            "cuarentena": int(len(df_cuarentena)),
            "marcadas": int((df_silver["_quality_flags"] != "").sum()),
        }
        print(f"Silver: {conteos['silver']} | Quarantine: {conteos['cuarentena']} | "
              f"Marcadas: {conteos['marcadas']}")
        for m in mediciones:
            if m["violaciones"]:
                print(f"   [{m['severidad']:<7}] {m['nombre']}: {m['violaciones']} de {m['filas']}")

        # --- 5. CORTE DE SEGURIDAD ---
        # Si TODO fue a cuarentena, lo mas probable es que haya cambiado el
        # formato de la fuente. Los datos ya quedaron guardados (el commit fue
        # arriba), pero la corrida va en rojo y gold no se dispara.
        if conteos["silver"] == 0:
            raise AirflowFailException(
                f"ninguna fila paso el contrato: {conteos['cuarentena']} en cuarentena"
            )
        return conteos

    @task
    def resumen(conteos: dict):
        """Resumen final en los logs. No escribe nada."""
        total = conteos["silver"] + conteos["cuarentena"]
        tasa = conteos["silver"] / max(total, 1) * 100
        print("=== Resumen Pipeline Silver ===")
        print(f"Snapshots: {conteos['snapshots']} | Leidas de bronze: {conteos['leidas']}")
        print(f"Silver: {conteos['silver']} | Quarantine: {conteos['cuarentena']} | "
              f"Marcadas: {conteos['marcadas']} | Tasa de exito: {tasa:.1f}%")

    # crear_tablas va primero: snapshots_del_run lee las tablas de silver.
    snaps = snapshots_del_run()
    crear_tablas() >> snaps

    # evaluar_calidad, cargar_redes y asignar_zonas corren en paralelo; la carga
    # espera a las tres.
    conteos = limpiar_y_cargar(snaps)
    [evaluar_calidad(snaps), cargar_redes(snaps), asignar_zonas(snaps)] >> conteos
    resumen(conteos)


citybikes_silver()
