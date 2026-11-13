import plotly.express as px
import streamlit as st

from db import run_query


GAP_MAX_MINUTOS = 10

st.title("Uso estimado por estación")
st.caption(
    "Estima retiros y devoluciones comparando las bicicletas disponibles entre "
    "snapshots consecutivos de cada estación."
)

sql_cambios = f"""
    WITH secuencia AS (
        SELECT
            network_id,
            station_id,
            station_name,
            dia_semana,
            hora,
            snapshot_ts,
            snapshot_local,
            free_bikes,
            LAG(snapshot_ts) OVER (
                PARTITION BY network_id, station_id
                ORDER BY snapshot_ts
            ) AS snapshot_previo,
            LAG(free_bikes) OVER (
                PARTITION BY network_id, station_id
                ORDER BY snapshot_ts
            ) AS bicis_previas
        FROM gold.vw_citybikes_saturacion
    ),
    deltas AS (
        SELECT
            *,
            free_bikes - bicis_previas AS delta_bicis
        FROM secuencia
        WHERE bicis_previas IS NOT NULL
          AND snapshot_ts > snapshot_previo
          AND snapshot_ts - snapshot_previo <= INTERVAL '{GAP_MAX_MINUTOS} minutes'
    )
    SELECT
        network_id,
        station_id,
        station_name,
        dia_semana,
        hora,
        snapshot_ts,
        snapshot_local,
        bicis_previas,
        free_bikes AS bicis_actuales,
        delta_bicis,
        GREATEST(-delta_bicis, 0) AS retiros_estimados,
        GREATEST(delta_bicis, 0) AS devoluciones_estimadas,
        ABS(delta_bicis) AS movimientos_minimos
    FROM deltas
    ORDER BY snapshot_ts DESC
"""

df = run_query(sql_cambios)
if df.empty:
    st.info("Todavía no hay cambios observados entre snapshots consecutivos.")
    st.caption(
        f"Se comparan observaciones separadas por hasta {GAP_MAX_MINUTOS} minutos."
    )
    st.stop()

redes = sorted(df["network_id"].dropna().unique())
red = st.selectbox("Red", redes, key="red_uso_estaciones")
df_red = df[df["network_id"] == red].copy()

tipo_dia = st.selectbox(
    "Días incluidos",
    ["Todos", "Días hábiles", "Fin de semana"],
    key="tipo_dia_uso_estaciones",
)
if tipo_dia == "Días hábiles":
    df_red = df_red[df_red["dia_semana"].between(1, 5)]
elif tipo_dia == "Fin de semana":
    df_red = df_red[df_red["dia_semana"].isin([6, 7])]

if df_red.empty:
    st.info("No hay cambios para esta red y selección de días.")
    st.stop()

retiros = int(df_red["retiros_estimados"].sum())
devoluciones = int(df_red["devoluciones_estimadas"].sum())
movimientos = retiros + devoluciones

col_retiros, col_devoluciones, col_movimientos = st.columns(3)
col_retiros.metric("Retiros estimados", f"{retiros:,}".replace(",", "."))
col_devoluciones.metric("Devoluciones estimadas", f"{devoluciones:,}".replace(",", "."))
col_movimientos.metric("Cambios mínimos observados", f"{movimientos:,}".replace(",", "."))

# Perfil horario del flujo: se atribuye cada cambio a la hora del snapshot actual.
por_hora = (
    df_red.groupby("hora", as_index=False)[
        ["retiros_estimados", "devoluciones_estimadas"]
    ]
    .sum()
    .set_index("hora")
    .reindex(range(24))
    .rename_axis("hora")
    .reset_index()
)
por_hora_largo = por_hora.melt(
    id_vars="hora",
    value_vars=["retiros_estimados", "devoluciones_estimadas"],
    var_name="movimiento",
    value_name="bicicletas_estimadas",
)
por_hora_largo["movimiento"] = por_hora_largo["movimiento"].map({
    "retiros_estimados": "Retiros",
    "devoluciones_estimadas": "Devoluciones",
})
por_hora_largo["hora_etiqueta"] = por_hora_largo["hora"].map(
    lambda hora: f"{hora:02d}:00"
)

fig_horario = px.line(
    por_hora_largo,
    x="hora_etiqueta",
    y="bicicletas_estimadas",
    color="movimiento",
    markers=True,
    category_orders={"hora_etiqueta": [f"{hora:02d}:00" for hora in range(24)]},
    color_discrete_map={"Retiros": "#d62828", "Devoluciones": "#277da1"},
    labels={
        "hora_etiqueta": "Hora local del snapshot",
        "bicicletas_estimadas": "Cambios estimados en bicicletas",
        "movimiento": "Tipo de cambio",
    },
)
fig_horario.update_xaxes(tickangle=-45)
fig_horario.update_layout(legend_title_text="")
st.subheader("Retiros y devoluciones estimados por hora")
st.plotly_chart(fig_horario, use_container_width=True)

# Ranking por estación: barras apiladas para comparar ambos sentidos del flujo.
por_estacion = (
    df_red.groupby(["station_id", "station_name"], as_index=False)[
        ["retiros_estimados", "devoluciones_estimadas"]
    ]
    .sum()
)
por_estacion["movimientos_minimos"] = (
    por_estacion["retiros_estimados"] + por_estacion["devoluciones_estimadas"]
)
por_estacion["estacion"] = por_estacion["station_name"].fillna("Sin nombre")
repetidos = por_estacion["estacion"].duplicated(keep=False)
por_estacion.loc[repetidos, "estacion"] = (
    por_estacion.loc[repetidos, "estacion"]
    + " · "
    + por_estacion.loc[repetidos, "station_id"].str[-6:]
)
top_estaciones = (
    por_estacion.nlargest(15, "movimientos_minimos")
    .sort_values("movimientos_minimos", ascending=True)
)
top_largo = top_estaciones.melt(
    id_vars=["station_id", "estacion", "movimientos_minimos"],
    value_vars=["retiros_estimados", "devoluciones_estimadas"],
    var_name="movimiento",
    value_name="bicicletas_estimadas",
)
top_largo["movimiento"] = top_largo["movimiento"].map({
    "retiros_estimados": "Retiros",
    "devoluciones_estimadas": "Devoluciones",
})

fig_estaciones = px.bar(
    top_largo,
    x="bicicletas_estimadas",
    y="estacion",
    color="movimiento",
    barmode="stack",
    orientation="h",
    hover_data=["station_id", "movimientos_minimos"],
    color_discrete_map={"Retiros": "#d62828", "Devoluciones": "#277da1"},
    labels={
        "bicicletas_estimadas": "Cambios estimados en bicicletas",
        "estacion": "Estación",
        "movimiento": "Tipo de cambio",
        "station_id": "ID de estación",
        "movimientos_minimos": "Cambios mínimos observados",
    },
)
fig_estaciones.update_layout(legend_title_text="")
fig_estaciones.update_yaxes(
    categoryorder="array", categoryarray=top_estaciones["estacion"].tolist()
)
fig_estaciones.update_layout(height=max(450, 32 * len(top_estaciones)))
st.subheader("Estaciones con más cambios observados")
st.plotly_chart(fig_estaciones, use_container_width=True)

st.caption(
    f"Se excluyen pares de snapshots separados por más de {GAP_MAX_MINUTOS} minutos. "
    "Cada cambio se asigna a la hora local del snapshot más reciente. Son mínimos estimados: "
    "retiros y devoluciones que se compensan entre snapshots no se observan."
)
