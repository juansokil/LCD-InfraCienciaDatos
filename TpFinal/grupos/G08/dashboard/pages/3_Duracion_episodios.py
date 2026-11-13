import plotly.express as px
import pandas as pd
import streamlit as st

from db import run_query


GAP_MAX_MINUTOS = 10  # Dos ciclos de muestreo; gaps mayores vuelven incierto el episodio.

st.title("Duración de episodios sin bicicletas")
st.caption(
    "Un episodio comienza cuando una estación pasa a cero bicicletas y termina "
    "en el primer snapshot posterior con bicicletas disponibles."
)

sql_episodios = f"""
    WITH ordenados AS (
        SELECT
            network_id,
            station_id,
            station_name,
            ciudad,
            zona,
            zona_padre,
            zona_nivel,
            snapshot_ts,
            snapshot_local,
            free_bikes,
            LAG(free_bikes) OVER (
                PARTITION BY network_id, station_id
                ORDER BY snapshot_ts
            ) AS bicis_previas,
            LAG(snapshot_ts) OVER (
                PARTITION BY network_id, station_id
                ORDER BY snapshot_ts
            ) AS snapshot_previo
        FROM gold.vw_citybikes_saturacion
    ),
    marcados AS (
        SELECT
            *,
            CASE
                WHEN free_bikes = 0 AND (
                    bicis_previas IS DISTINCT FROM 0
                    OR snapshot_ts - snapshot_previo > INTERVAL '{GAP_MAX_MINUTOS} minutes'
                ) THEN 1
                ELSE 0
            END AS nuevo_episodio,
            (
                free_bikes = 0
                AND bicis_previas > 0
                AND snapshot_ts - snapshot_previo <= INTERVAL '{GAP_MAX_MINUTOS} minutes'
            ) AS inicio_confirmado
        FROM ordenados
    ),
    numerados AS (
        SELECT
            *,
            SUM(nuevo_episodio) OVER (
                PARTITION BY network_id, station_id
                ORDER BY snapshot_ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS episodio_numero
        FROM marcados
    ),
    episodios_vacios AS (
        SELECT
            network_id,
            station_id,
            station_name,
            ciudad,
            zona,
            zona_padre,
            zona_nivel,
            episodio_numero,
            MIN(snapshot_ts) AS inicio_ts,
            MIN(snapshot_local) AS inicio_local,
            MAX(snapshot_ts) AS ultimo_vacio_ts,
            BOOL_OR(inicio_confirmado) AS inicio_confirmado,
            COUNT(*) AS snapshots_vacios
        FROM numerados
        WHERE free_bikes = 0
        GROUP BY
            network_id,
            station_id,
            station_name,
            ciudad,
            zona,
            zona_padre,
            zona_nivel,
            episodio_numero
    ),
    episodios_con_reposicion AS (
        SELECT
            e.*,
            reposicion.snapshot_ts AS reposicion_ts
        FROM episodios_vacios e
        LEFT JOIN LATERAL (
            SELECT s.snapshot_ts
            FROM gold.vw_citybikes_saturacion s
            WHERE s.network_id = e.network_id
              AND s.station_id = e.station_id
              AND s.snapshot_ts > e.ultimo_vacio_ts
              AND s.free_bikes > 0
            ORDER BY s.snapshot_ts
            LIMIT 1
        ) reposicion ON TRUE
    )
    SELECT
        network_id,
        station_id,
        station_name,
        ciudad,
        zona,
        zona_padre,
        zona_nivel,
        inicio_ts,
        inicio_local,
        EXTRACT(ISODOW FROM inicio_local)::integer AS dia_semana_inicio,
        EXTRACT(HOUR FROM inicio_local)::integer AS hora_inicio,
        snapshots_vacios,
        EXTRACT(EPOCH FROM (reposicion_ts - inicio_ts)) / 60.0 AS duracion_minutos
    FROM episodios_con_reposicion
    WHERE inicio_confirmado IS TRUE
      AND reposicion_ts IS NOT NULL
      AND reposicion_ts <= ultimo_vacio_ts + INTERVAL '{GAP_MAX_MINUTOS} minutes'
    ORDER BY inicio_local DESC
"""

df = run_query(sql_episodios)
if df.empty:
    st.info(
        "Todavía no hay episodios completos con observaciones suficientes "
        "para medir su duración."
    )
    st.caption(
        f"Se requieren snapshots antes y después del episodio, sin huecos mayores "
        f"a {GAP_MAX_MINUTOS} minutos."
    )
    st.stop()

# PostgreSQL EXTRACT devuelve NUMERIC, que SQLAlchemy expone como Decimal.
# Plotly y el cálculo del percentil 90 necesitan valores float consistentes.
df["duracion_minutos"] = pd.to_numeric(
    df["duracion_minutos"], errors="coerce"
).astype(float)
df = df.dropna(subset=["duracion_minutos"])
if df.empty:
    st.info("No hay duraciones numéricas para graficar.")
    st.stop()

redes = sorted(df["network_id"].dropna().unique())
red = st.selectbox("Red", redes, key="red_duracion_episodios")
df_red = df[df["network_id"] == red].copy()

if red == "ecobici-buenos-aires":
    nivel = st.selectbox(
        "Agrupar zonas por",
        ["Barrio", "Comuna"],
        key="nivel_zona_duracion",
    )
    if nivel == "Barrio":
        df_red["zona_grafico"] = df_red["zona"].where(
            df_red["zona_nivel"] == "barrio", "Sin barrio asignado"
        ).fillna("Sin barrio asignado")
    else:
        df_red["zona_grafico"] = df_red["zona_padre"].where(
            df_red["zona_nivel"] == "barrio", "Sin comuna asignada"
        ).fillna("Sin comuna asignada")
else:
    nivel = "Ciudad"
    df_red["zona_grafico"] = (
        df_red["ciudad"].fillna(df_red["zona"]).fillna("Sin ciudad asignada")
    )

episodios, mediana = st.columns(2)
episodios.metric("Episodios completos", f"{len(df_red):,}".replace(",", "."))
mediana.metric(
    "Duración mediana",
    f"{df_red['duracion_minutos'].median():.1f} min",
)

# Mediana por zona: es menos sensible que el promedio a episodios muy largos.
por_zona = (
    df_red.groupby("zona_grafico", as_index=False)
    .agg(
        episodios=("duracion_minutos", "size"),
        mediana_minutos=("duracion_minutos", "median"),
        p90_minutos=("duracion_minutos", lambda valores: valores.quantile(0.90)),
    )
    .nlargest(10, "mediana_minutos")
    .sort_values("mediana_minutos")
)

fig_zonas = px.bar(
    por_zona,
    x="mediana_minutos",
    y="zona_grafico",
    orientation="h",
    hover_data=["episodios", "p90_minutos"],
    labels={
        "mediana_minutos": "Duración mediana (minutos)",
        "zona_grafico": nivel,
        "episodios": "Episodios completos",
        "p90_minutos": "Percentil 90 (minutos)",
    },
)
st.subheader(f"Duración mediana por {nivel.lower()}")
st.plotly_chart(fig_zonas, use_container_width=True)

# Distribución por hora local de inicio: muestra mediana y dispersión.
df_red["hora_etiqueta"] = df_red["hora_inicio"].map(lambda hora: f"{hora:02d}:00")
orden_horas = sorted(df_red["hora_etiqueta"].unique())
fig_horas = px.box(
    df_red,
    x="hora_etiqueta",
    y="duracion_minutos",
    points="all",
    category_orders={"hora_etiqueta": orden_horas},
    hover_data=["station_name", "zona_grafico", "snapshots_vacios"],
    labels={
        "hora_etiqueta": "Hora local de inicio",
        "duracion_minutos": "Duración (minutos)",
        "station_name": "Estación",
        "zona_grafico": nivel,
        "snapshots_vacios": "Snapshots sin bicicletas",
    },
)
st.subheader("Duración según la hora en que empieza el episodio")
st.plotly_chart(fig_horas, use_container_width=True)

# Tabla de detalle para poder revisar cada episodio y su estación.
st.subheader("Episodios completos observados")
st.dataframe(
    df_red[
        [
            "station_name",
            "zona_grafico",
            "inicio_local",
            "hora_inicio",
            "duracion_minutos",
            "snapshots_vacios",
        ]
    ].sort_values("duracion_minutos", ascending=False),
    use_container_width=True,
    hide_index=True,
)

st.caption(
    f"Se incluyen episodios cerrados con inicio confirmado y una reposición observada "
    f"dentro de {GAP_MAX_MINUTOS} minutos del último snapshot vacío. "
    "Los episodios aún abiertos y los afectados por huecos largos no entran en estas estadísticas."
)
