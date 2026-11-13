"""
DAG: citybikes_gold
Silver -> Gold de CityBikes: modelo dimensional para las preguntas de negocio.

    silver.citybikes_stations     -> gold.fact_estacion_hora        (P1, P2, P4, P5, P6)
                                  -> gold.fact_episodio_sin_bicis   (P3)
    silver.citybikes_station_zone -> gold.dim_estacion
    silver.citybikes_networks     -> gold.dim_estacion (nombre de la red)
    gold.fact_estacion_hora       -> gold.dim_fecha
    gold.dim_estacion + silver    -> gold.fact_capacidad_actual     (P6)

Arranca cuando silver emite `silver_citybikes` y, al terminar, emite
`gold_citybikes`. Todo el calculo se hace en Postgres (SQL); los datos no pasan
por pandas ni por XCom.

Carga INCREMENTAL e idempotente: cada corrida recalcula solo los dias locales
desde `DIAS_RECALCULO` atras (silver procesa snapshots atrasados hasta 48 h) con
DELETE + INSERT en una transaccion por tabla. Si el modelo cambia, se sube
`VERSION_MODELO` y la corrida siguiente borra gold y lo reconstruye entero.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow.sdk import dag, task

sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_CITYBIKES, SILVER_CITYBIKES  # noqa: E402
from common.derivadas import TZ_LOCAL  # noqa: E402

DB_URI = (
    "postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'CityBikes')}"
)

# Cambiarla fuerza a reconstruir gold desde cero en la corrida siguiente.
VERSION_MODELO = "3"

# Dias locales que se recalculan en cada corrida (cubren las 48 h de silver).
DIAS_RECALCULO = 2

# Un episodio se carga cuando TERMINA. Para ver su inicio se lee silver hasta
# esta cantidad de dias antes de la ventana: episodios mas largos no se miden.
MAX_EPISODIO_DIAS = 7

# Dos snapshots consecutivos se comparan solo si estan a <= 10 min (dos ciclos
# de 5). Con huecos mas largos no se sabe que paso en el medio.
GAP_MAX_MINUTOS = 10

# Un cambio de >= 5 bicis entre dos snapshots se toma como camion de
# reposicion/retiro del operador, no como uso de los clientes (heuristica).
UMBRAL_REBALANCEO = 5

TABLAS = (
    "fact_capacidad_actual",
    "fact_episodio_sin_bicis",
    "fact_estacion_hora",
    "dim_fecha",
    "dim_estacion",
)

# Fila valida para medir saturacion (criterio comun del README): la estacion
# alquila, no rechaza devoluciones y no tiene flags de calidad. Una estacion
# caida no es una estacion saturada.
VALIDA = (
    "(renting IS TRUE AND \"returning\" IS NOT FALSE "
    "AND COALESCE(_quality_flags, '') = '')"
)

# Inicio (UTC) del primer dia local que se recalcula.
DESDE_TS = "(CAST(:desde AS date)::timestamp AT TIME ZONE :tz)"

PARAMS_BASE = {"tz": TZ_LOCAL, "gap": GAP_MAX_MINUTOS, "umbral": UMBRAL_REBALANCEO,
               "max_episodio": MAX_EPISODIO_DIAS}


DDL = """
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold._modelo (
    version        text        NOT NULL,
    actualizado_at timestamptz NOT NULL
);

-- Una fila por estacion. Atributos del ultimo snapshot + zona + red.
CREATE TABLE IF NOT EXISTS gold.dim_estacion (
    network_id      text NOT NULL,
    station_id      text NOT NULL,
    red_nombre      text,
    ciudad          text,
    station_number  integer,
    station_name    text,
    latitude        double precision,
    longitude       double precision,
    slots           integer,
    zona            text,
    zona_padre      text,
    zona_nivel      text,
    primera_obs     timestamptz,
    ultima_obs      timestamptz,
    PRIMARY KEY (network_id, station_id)
);

-- Una fila por dia local con datos.
CREATE TABLE IF NOT EXISTS gold.dim_fecha (
    fecha       date     PRIMARY KEY,
    dia_semana  smallint NOT NULL,  -- ISO: 1 = lunes ... 7 = domingo
    nombre_dia  text     NOT NULL,
    tipo_dia    text     NOT NULL   -- 'Habil' / 'Fin de semana'
);

-- Grano: estacion x dia local x hora local. Conteos de snapshots (no
-- porcentajes): el dashboard suma numeradores y denominadores y recien ahi
-- divide, asi cualquier agregacion (zona, red, dia) da la tasa correcta.
CREATE TABLE IF NOT EXISTS gold.fact_estacion_hora (
    network_id               text     NOT NULL,
    station_id               text     NOT NULL,
    fecha                    date     NOT NULL,
    hora                     smallint NOT NULL,
    snapshots_total          integer  NOT NULL,  -- todo lo que llego de silver
    snapshots_validos        integer  NOT NULL,  -- base de P1-P5
    snapshots_sin_bicis      integer  NOT NULL,  -- validos con free_bikes = 0
    snapshots_sin_anclajes   integer  NOT NULL,  -- validos con empty_slots = 0
    snapshots_no_alquila     integer  NOT NULL,  -- renting = false (P6)
    snapshots_no_recibe      integer  NOT NULL,  -- returning = false (P6)
    snapshots_estado_desconocido integer NOT NULL,  -- renting nulo (P6)
    snapshots_operador_viejo integer  NOT NULL,  -- flag operador_fresco (P6)
    bicis_promedio           double precision,
    ocupacion_promedio       double precision,
    docks_fuera_servicio_promedio double precision,
    pares_comparados         integer  NOT NULL,  -- pares validos a <= GAP_MAX_MINUTOS
    retiros_estimados        integer  NOT NULL,  -- bajas de bicis < UMBRAL_REBALANCEO
    devoluciones_estimadas   integer  NOT NULL,  -- subas de bicis < UMBRAL_REBALANCEO
    rebalanceo_bicis         integer  NOT NULL,  -- |cambios| >= UMBRAL_REBALANCEO
    PRIMARY KEY (network_id, station_id, fecha, hora)
);
CREATE INDEX IF NOT EXISTS ix_gold_feh_fecha ON gold.fact_estacion_hora (fecha);

-- Grano: episodio cerrado sin bicis. Empieza en el primer snapshot con
-- free_bikes = 0 (precedido por uno con bicis a <= GAP_MAX_MINUTOS) y termina en
-- el primer snapshot con bicis (a <= GAP_MAX_MINUTOS del ultimo vacio).
CREATE TABLE IF NOT EXISTS gold.fact_episodio_sin_bicis (
    network_id        text        NOT NULL,
    station_id        text        NOT NULL,
    inicio_ts         timestamptz NOT NULL,
    fin_ts            timestamptz NOT NULL,
    inicio_local      timestamp   NOT NULL,
    fecha_inicio      date        NOT NULL,
    hora_inicio       smallint    NOT NULL,
    snapshots_vacios  integer     NOT NULL,
    duracion_minutos  double precision NOT NULL,
    PRIMARY KEY (network_id, station_id, inicio_ts)
);
CREATE INDEX IF NOT EXISTS ix_gold_fes_fin ON gold.fact_episodio_sin_bicis (fin_ts);

-- Grano: estacion (foto de su ultimo snapshot). Se reemplaza en cada corrida.
CREATE TABLE IF NOT EXISTS gold.fact_capacidad_actual (
    network_id            text        NOT NULL,
    station_id            text        NOT NULL,
    snapshot_ts           timestamptz NOT NULL,
    source_last_updated   timestamptz,
    free_bikes            integer,
    empty_slots           integer,
    slots                 integer,
    docks_fuera_servicio  integer,
    alquila               boolean,
    recibe                boolean,
    operador_viejo        boolean     NOT NULL,
    sin_dato_operador     boolean     NOT NULL,
    PRIMARY KEY (network_id, station_id)
);
"""


SQL_DIM_ESTACION = f"""
    WITH ventana AS (
        SELECT *
        FROM silver.citybikes_stations
        WHERE snapshot_ts >= {DESDE_TS}
          AND snapshot_local IS NOT NULL
    ),
    ultima AS (
        SELECT DISTINCT ON (network_id, station_id)
            network_id, station_id,
            COALESCE(station_name, name) AS station_name,
            station_number, latitude, longitude, slots,
            snapshot_ts AS ultima_obs
        FROM ventana
        ORDER BY network_id, station_id, snapshot_ts DESC
    ),
    primera AS (
        SELECT network_id, station_id, min(snapshot_ts) AS primera_obs
        FROM ventana
        GROUP BY network_id, station_id
    )
    INSERT INTO gold.dim_estacion AS d (
        network_id, station_id, station_number, station_name,
        latitude, longitude, slots, primera_obs, ultima_obs
    )
    SELECT u.network_id, u.station_id, u.station_number, u.station_name,
           u.latitude, u.longitude, u.slots, p.primera_obs, u.ultima_obs
    FROM ultima u
    JOIN primera p USING (network_id, station_id)
    ON CONFLICT (network_id, station_id) DO UPDATE SET
        station_number = EXCLUDED.station_number,
        station_name   = EXCLUDED.station_name,
        latitude       = EXCLUDED.latitude,
        longitude      = EXCLUDED.longitude,
        slots          = EXCLUDED.slots,
        primera_obs    = LEAST(d.primera_obs, EXCLUDED.primera_obs),
        ultima_obs     = EXCLUDED.ultima_obs
    WHERE d.ultima_obs IS NULL OR d.ultima_obs <= EXCLUDED.ultima_obs
"""

# Zona y red para TODAS las estaciones (la zona puede cambiar si se suma una
# capa nueva en silver). Sin fila de zona, la estacion cae a la ciudad de la red.
# zona_padre ya llega etiquetada desde silver ("Comuna 1").
SQL_DIM_ESTACION_ZONA = """
    WITH redes AS (
        SELECT DISTINCT ON (network_id) network_id, name, city
        FROM silver.citybikes_networks
        ORDER BY network_id, snapshot_ts DESC
    ),
    atributos AS (
        SELECT
            d.network_id,
            d.station_id,
            COALESCE(r.name, d.network_id) AS red_nombre,
            COALESCE(z.ciudad, r.city, d.network_id) AS ciudad,
            COALESCE(z.zona, z.ciudad, r.city, d.network_id) AS zona,
            z.zona_padre,
            COALESCE(z.zona_nivel, 'ciudad') AS zona_nivel
        FROM gold.dim_estacion d
        LEFT JOIN silver.citybikes_station_zone z
               ON z.network_id = d.network_id AND z.station_id = d.station_id
        LEFT JOIN redes r ON r.network_id = d.network_id
    )
    UPDATE gold.dim_estacion d
    SET red_nombre = a.red_nombre,
        ciudad     = a.ciudad,
        zona       = a.zona,
        zona_padre = a.zona_padre,
        zona_nivel = a.zona_nivel
    FROM atributos a
    WHERE a.network_id = d.network_id
      AND a.station_id = d.station_id
      AND (d.red_nombre, d.ciudad, d.zona, d.zona_padre, d.zona_nivel)
          IS DISTINCT FROM (a.red_nombre, a.ciudad, a.zona, a.zona_padre, a.zona_nivel)
"""

# Se lee un dia extra antes de :desde para que el LAG del primer snapshot de la
# ventana encuentre a su anterior; solo se insertan las horas >= :desde.
SQL_FACT_ESTACION_HORA = f"""
    WITH base AS (
        SELECT
            network_id, station_id, snapshot_ts, snapshot_local,
            free_bikes, empty_slots, ocupacion, docks_fuera_servicio,
            renting, "returning",
            COALESCE(_quality_flags, '') AS flags,
            {VALIDA} AS valida
        FROM silver.citybikes_stations
        WHERE snapshot_ts >= {DESDE_TS} - INTERVAL '1 day'
          AND snapshot_local IS NOT NULL
    ),
    pares AS (
        SELECT
            network_id, station_id, snapshot_ts,
            free_bikes - LAG(free_bikes) OVER w AS delta,
            snapshot_ts - LAG(snapshot_ts) OVER w <= make_interval(mins => :gap)
                AS comparable
        FROM base
        WHERE valida
        WINDOW w AS (PARTITION BY network_id, station_id ORDER BY snapshot_ts)
    )
    INSERT INTO gold.fact_estacion_hora
    SELECT
        b.network_id,
        b.station_id,
        b.snapshot_local::date AS fecha,
        EXTRACT(HOUR FROM b.snapshot_local)::smallint AS hora,
        count(*) AS snapshots_total,
        count(*) FILTER (WHERE b.valida) AS snapshots_validos,
        count(*) FILTER (WHERE b.valida AND b.free_bikes = 0) AS snapshots_sin_bicis,
        count(*) FILTER (WHERE b.valida AND b.empty_slots = 0) AS snapshots_sin_anclajes,
        count(*) FILTER (WHERE b.renting IS FALSE) AS snapshots_no_alquila,
        count(*) FILTER (WHERE b."returning" IS FALSE) AS snapshots_no_recibe,
        count(*) FILTER (WHERE b.renting IS NULL) AS snapshots_estado_desconocido,
        count(*) FILTER (WHERE position('operador_fresco' IN b.flags) > 0) AS snapshots_operador_viejo,
        avg(b.free_bikes) FILTER (WHERE b.valida) AS bicis_promedio,
        avg(b.ocupacion) FILTER (WHERE b.valida) AS ocupacion_promedio,
        avg(b.docks_fuera_servicio) AS docks_fuera_servicio_promedio,
        count(*) FILTER (WHERE p.comparable) AS pares_comparados,
        COALESCE(sum(-p.delta) FILTER (
            WHERE p.comparable AND p.delta < 0 AND -p.delta < :umbral), 0) AS retiros_estimados,
        COALESCE(sum(p.delta) FILTER (
            WHERE p.comparable AND p.delta > 0 AND p.delta < :umbral), 0) AS devoluciones_estimadas,
        COALESCE(sum(abs(p.delta)) FILTER (
            WHERE p.comparable AND abs(p.delta) >= :umbral), 0) AS rebalanceo_bicis
    FROM base b
    LEFT JOIN pares p USING (network_id, station_id, snapshot_ts)
    WHERE b.snapshot_ts >= {DESDE_TS}
    GROUP BY 1, 2, 3, 4
"""

# Islas: cada corte (cambio entre "vacia" y "con bicis", o hueco > gap) abre un
# tramo. Un tramo vacio es un episodio si el snapshot anterior tenia bicis y el
# siguiente tambien, ambos a <= gap. Los episodios abiertos no se cargan: la
# corrida que vea la reposicion los agrega. Por eso la ventana es por FIN del
# episodio (fin_ts >= desde) y se lee silver MAX_EPISODIO_DIAS antes, para que
# una estacion vacia todo un fin de semana tambien tenga su inicio a la vista.
SQL_FACT_EPISODIOS = f"""
    WITH validas AS (
        SELECT network_id, station_id, snapshot_ts, snapshot_local, free_bikes
        FROM silver.citybikes_stations
        WHERE snapshot_ts >= {DESDE_TS} - make_interval(days => :max_episodio)
          AND snapshot_local IS NOT NULL
          AND {VALIDA}
    ),
    secuencia AS (
        SELECT
            *,
            LAG(free_bikes)  OVER w AS bicis_previas,
            LAG(snapshot_ts) OVER w AS ts_previo,
            LEAD(free_bikes)  OVER w AS bicis_siguientes,
            LEAD(snapshot_ts) OVER w AS ts_siguiente
        FROM validas
        WINDOW w AS (PARTITION BY network_id, station_id ORDER BY snapshot_ts)
    ),
    cortes AS (
        SELECT
            *,
            CASE
                WHEN ts_previo IS NULL
                  OR snapshot_ts - ts_previo > make_interval(mins => :gap)
                  OR (free_bikes = 0) <> (bicis_previas = 0)
                THEN 1 ELSE 0
            END AS corte
        FROM secuencia
    ),
    tramos AS (
        SELECT
            *,
            sum(corte) OVER (
                PARTITION BY network_id, station_id ORDER BY snapshot_ts
            ) AS tramo
        FROM cortes
    ),
    episodios AS (
        SELECT
            network_id,
            station_id,
            min(snapshot_ts)    AS inicio_ts,
            max(snapshot_ts)    AS ultimo_vacio_ts,
            min(snapshot_local) AS inicio_local,
            count(*)            AS snapshots_vacios,
            (array_agg(bicis_previas    ORDER BY snapshot_ts))[1]      AS bicis_previas,
            (array_agg(ts_previo        ORDER BY snapshot_ts))[1]      AS ts_previo,
            (array_agg(bicis_siguientes ORDER BY snapshot_ts DESC))[1] AS bicis_siguientes,
            (array_agg(ts_siguiente     ORDER BY snapshot_ts DESC))[1] AS ts_siguiente
        FROM tramos
        WHERE free_bikes = 0
        GROUP BY network_id, station_id, tramo
    )
    INSERT INTO gold.fact_episodio_sin_bicis
    SELECT
        network_id,
        station_id,
        inicio_ts,
        ts_siguiente AS fin_ts,
        inicio_local,
        inicio_local::date AS fecha_inicio,
        EXTRACT(HOUR FROM inicio_local)::smallint AS hora_inicio,
        snapshots_vacios,
        EXTRACT(EPOCH FROM (ts_siguiente - inicio_ts)) / 60.0 AS duracion_minutos
    FROM episodios
    WHERE ts_siguiente >= {DESDE_TS}
      AND bicis_previas > 0
      AND inicio_ts - ts_previo <= make_interval(mins => :gap)
      AND bicis_siguientes > 0
      AND ts_siguiente - ultimo_vacio_ts <= make_interval(mins => :gap)
"""

SQL_DIM_FECHA = """
    INSERT INTO gold.dim_fecha (fecha, dia_semana, nombre_dia, tipo_dia)
    SELECT
        f::date,
        EXTRACT(ISODOW FROM f)::smallint,
        (ARRAY['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes',
               'Sábado', 'Domingo'])[EXTRACT(ISODOW FROM f)::int],
        CASE WHEN EXTRACT(ISODOW FROM f) >= 6 THEN 'Fin de semana' ELSE 'Hábil' END
    FROM (SELECT DISTINCT fecha::timestamp AS f FROM gold.fact_estacion_hora) AS dias
"""

# Ultimo snapshot de cada estacion: lookup por la PK de silver usando
# dim_estacion.ultima_obs (sin recorrer todo el historico).
SQL_FACT_CAPACIDAD = """
    INSERT INTO gold.fact_capacidad_actual
    SELECT
        d.network_id,
        d.station_id,
        s.snapshot_ts,
        s.source_last_updated,
        s.free_bikes,
        s.empty_slots,
        s.slots,
        s.docks_fuera_servicio,
        s.renting,
        s."returning",
        position('operador_fresco' IN COALESCE(s._quality_flags, '')) > 0,
        s.source_last_updated IS NULL
    FROM gold.dim_estacion d
    JOIN silver.citybikes_stations s
      ON s.snapshot_ts = d.ultima_obs
     AND s.network_id = d.network_id
     AND s.station_id = d.station_id
"""


def _engine():
    import sqlalchemy

    return sqlalchemy.create_engine(DB_URI)


def _ejecutar(sentencias: list[tuple[str, dict]]) -> list[int]:
    """Corre las sentencias en UNA transaccion y devuelve las filas afectadas."""
    import sqlalchemy

    with _engine().begin() as conn:
        return [conn.execute(sqlalchemy.text(sql), params).rowcount
                for sql, params in sentencias]


@dag(
    dag_id="citybikes_gold",
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    start_date=datetime(2026, 10, 1),
    schedule=[SILVER_CITYBIKES],
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["gold", "citybikes"],
    doc_md=__doc__,
)
def citybikes_gold():
    @task
    def preparar_modelo() -> str:
        """Crea las tablas y decide desde que dia local se recalcula.

        Devuelve la fecha `desde` (ISO). Si gold esta vacio o cambio
        VERSION_MODELO, recalcula todo el historico de silver.
        """
        import sqlalchemy

        with _engine().begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS gold"))
            # Version anterior de gold: una vista que el dashboard ya no usa.
            conn.execute(sqlalchemy.text("DROP VIEW IF EXISTS gold.vw_citybikes_saturacion"))
            conn.execute(sqlalchemy.text(
                "CREATE TABLE IF NOT EXISTS gold._modelo "
                "(version text NOT NULL, actualizado_at timestamptz NOT NULL)"
            ))
            version = conn.execute(sqlalchemy.text(
                "SELECT version FROM gold._modelo LIMIT 1"
            )).scalar()
            if version != VERSION_MODELO:
                print(f"Modelo gold {version} -> {VERSION_MODELO}: se reconstruye entero")
                for tabla in TABLAS:
                    conn.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS gold.{tabla} CASCADE"))
                conn.execute(sqlalchemy.text("DELETE FROM gold._modelo"))
                conn.execute(sqlalchemy.text(
                    "INSERT INTO gold._modelo VALUES (:v, now())"
                ), {"v": VERSION_MODELO})
            conn.execute(sqlalchemy.text(DDL))

            vacio = conn.execute(sqlalchemy.text(
                "SELECT NOT EXISTS (SELECT 1 FROM gold.fact_estacion_hora)"
            )).scalar()
            hoy = conn.execute(sqlalchemy.text(
                "SELECT (now() AT TIME ZONE :tz)::date"
            ), {"tz": TZ_LOCAL}).scalar()
            desde = hoy - timedelta(days=DIAS_RECALCULO)
            # Si gold estuvo parado mas que la ventana, retoma desde el ultimo
            # dia cargado (puede estar incompleto): no quedan dias sin calcular.
            ultimo = conn.execute(sqlalchemy.text(
                "SELECT max(fecha) FROM gold.fact_estacion_hora"
            )).scalar()
            if ultimo:
                desde = min(desde, ultimo)
            if vacio:
                primero = conn.execute(sqlalchemy.text(
                    "SELECT min(snapshot_local)::date FROM silver.citybikes_stations"
                )).scalar()
                desde = min(desde, primero) if primero else desde
        print(f"Gold recalcula desde {desde} ({'carga completa' if vacio else 'incremental'})")
        return desde.isoformat()

    @task
    def cargar_dim_estacion(desde: str):
        params = {**PARAMS_BASE, "desde": desde}
        nuevas, rezonificadas = _ejecutar([
            (SQL_DIM_ESTACION, params),
            (SQL_DIM_ESTACION_ZONA, {}),
        ])
        print(f"dim_estacion: {nuevas} altas/actualizaciones, {rezonificadas} con zona o red nueva")

    @task
    def cargar_fact_estacion_hora(desde: str):
        params = {**PARAMS_BASE, "desde": desde}
        borradas, insertadas = _ejecutar([
            ("DELETE FROM gold.fact_estacion_hora WHERE fecha >= CAST(:desde AS date)", params),
            (SQL_FACT_ESTACION_HORA, params),
        ])
        print(f"fact_estacion_hora: -{borradas} +{insertadas}")

    @task
    def cargar_fact_episodios(desde: str):
        params = {**PARAMS_BASE, "desde": desde}
        borradas, insertadas = _ejecutar([
            (f"DELETE FROM gold.fact_episodio_sin_bicis WHERE fin_ts >= {DESDE_TS}", params),
            (SQL_FACT_EPISODIOS, params),
        ])
        print(f"fact_episodio_sin_bicis: -{borradas} +{insertadas}")

    @task
    def cargar_dim_fecha():
        _, insertadas = _ejecutar([
            ("DELETE FROM gold.dim_fecha", {}),
            (SQL_DIM_FECHA, {}),
        ])
        print(f"dim_fecha: {insertadas} dias")

    @task
    def cargar_fact_capacidad():
        _, insertadas = _ejecutar([
            ("DELETE FROM gold.fact_capacidad_actual", {}),
            (SQL_FACT_CAPACIDAD, {}),
        ])
        print(f"fact_capacidad_actual: {insertadas} estaciones")

    @task(outlets=[GOLD_CITYBIKES])
    def resumen():
        """Conteos finales en los logs; emite el asset gold_citybikes."""
        import sqlalchemy

        with _engine().connect() as conn:
            for tabla in TABLAS:
                n = conn.execute(sqlalchemy.text(f"SELECT count(*) FROM gold.{tabla}")).scalar()
                print(f"gold.{tabla}: {n} filas")

    desde = preparar_modelo()
    dim = cargar_dim_estacion(desde)
    hechos = cargar_fact_estacion_hora(desde)
    episodios = cargar_fact_episodios(desde)
    fechas = cargar_dim_fecha()
    capacidad = cargar_fact_capacidad()

    hechos >> fechas
    dim >> capacidad
    [fechas, capacidad, episodios] >> resumen()


citybikes_gold()
