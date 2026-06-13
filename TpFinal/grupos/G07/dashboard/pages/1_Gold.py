"""
Dashboard Gold - CityBikes / EcoBici

Primera versión exploratoria para visualizar las tablas Gold.
Muestra KPIs generales, estado actual de estaciones y patrón horario de ocupación.
"""

import plotly.express as px
import streamlit as st
from db import run_query


# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(
    page_title="Gold - CityBikes",
    page_icon="🥇",
    layout="wide",
)

st.title("🥇 Capa Gold - CityBikes / EcoBici")
st.caption("Dashboard operativo para monitorear disponibilidad, ocupación y estaciones críticas.")


def mostrar_error_tablas(error: Exception):
    st.error("No pude leer las tablas Gold todavía.")
    st.info(
        "Verificá que el contenedor de Postgres esté corriendo, que el DAG Gold haya ejecutado "
        "correctamente y que existan las tablas en el schema `gold`."
    )
    st.exception(error)


# =====================================================
# CARGA DE DATOS
# =====================================================

try:
    df_actual = run_query(
        """
        SELECT
            fa.station_id,
            fa.network_id,
            fa.time_id,
            fa.ts,
            fa.timestamp_api,
            fa.free_bikes_actuales,
            fa.empty_slots_actuales,
            fa.occupancy_pct_actual,
            fa.estado_critico_actual,
            de.name,
            de.latitude,
            de.longitude,
            de.barrio,
            de.comuna,
            de.zona_id
        FROM gold.fact_estado_actual_estacion fa
        LEFT JOIN gold.dim_estacion de
            ON fa.station_id = de.station_id
           AND fa.network_id = de.network_id;
        """
    )

    df_hora = run_query(
        """
        SELECT
            f.time_id,
            dt.fecha,
            dt.hora,
            f.station_id,
            f.network_id,
            f.zona_id,
            f.free_bikes_promedio,
            f.empty_slots_promedio,
            f.occupancy_pct_promedio,
            f.occupancy_pct_maxima,
            f.occupancy_pct_minima,
            f.cantidad_observaciones,
            f.porcentaje_tiempo_critico,
            de.name,
            de.barrio,
            de.comuna
        FROM gold.fact_ocupacion_por_hora f
        LEFT JOIN gold.dim_time dt
            ON f.time_id = dt.time_id
        LEFT JOIN gold.dim_estacion de
            ON f.station_id = de.station_id
           AND f.network_id = de.network_id;
        """
    )
except Exception as error:
    mostrar_error_tablas(error)
    st.stop()


# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.header("Filtros")

zonas = sorted(df_hora["zona_id"].dropna().unique()) if not df_hora.empty else []
zona_seleccionada = st.sidebar.multiselect(
    "Zona",
    options=zonas,
    default=zonas,
)

if zona_seleccionada:
    df_hora_filtrado = df_hora[df_hora["zona_id"].isin(zona_seleccionada)]
    df_actual_filtrado = df_actual[df_actual["zona_id"].isin(zona_seleccionada)]
else:
    df_hora_filtrado = df_hora.copy()
    df_actual_filtrado = df_actual.copy()


# =====================================================
# KPIS
# =====================================================

st.subheader("Estado actual de la red")

col1, col2, col3, col4 = st.columns(4)

estaciones_activas = df_actual_filtrado["station_id"].nunique()
free_bikes_total = df_actual_filtrado["free_bikes_actuales"].sum()
empty_slots_total = df_actual_filtrado["empty_slots_actuales"].sum()
estaciones_criticas = df_actual_filtrado["estado_critico_actual"].sum()

col1.metric("Estaciones monitoreadas", int(estaciones_activas))
col2.metric("Bicicletas disponibles", int(free_bikes_total))
col3.metric("Slots libres", int(empty_slots_total))
col4.metric("Estaciones críticas", int(estaciones_criticas))

st.divider()


# =====================================================
# PATRÓN HORARIO
# =====================================================

st.subheader("Ocupación promedio por hora del día")

ocupacion_por_hora = (
    df_hora_filtrado
    .groupby("hora", as_index=False)["occupancy_pct_promedio"]
    .mean()
    .sort_values("hora")
)

if ocupacion_por_hora.empty:
    st.warning("Todavía no hay datos horarios para mostrar.")
else:
    fig_hora = px.line(
        ocupacion_por_hora,
        x="hora",
        y="occupancy_pct_promedio",
        markers=True,
        labels={
            "hora": "Hora del día",
            "occupancy_pct_promedio": "Ocupación promedio (%)",
        },
        title="Patrón horario de ocupación",
    )
    st.plotly_chart(fig_hora, use_container_width=True)


# =====================================================
# RANKING DE ESTACIONES CRÍTICAS
# =====================================================

st.subheader("Top estaciones críticas")

ranking_criticas = (
    df_hora_filtrado
    .groupby(["station_id", "name", "barrio"], dropna=False, as_index=False)
    .agg(
        porcentaje_tiempo_critico=("porcentaje_tiempo_critico", "mean"),
        occupancy_pct_promedio=("occupancy_pct_promedio", "mean"),
        free_bikes_promedio=("free_bikes_promedio", "mean"),
        empty_slots_promedio=("empty_slots_promedio", "mean"),
    )
    .sort_values("porcentaje_tiempo_critico", ascending=False)
    .head(10)
)

if ranking_criticas.empty:
    st.warning("Todavía no hay datos suficientes para calcular el ranking.")
else:
    fig_ranking = px.bar(
        ranking_criticas,
        x="porcentaje_tiempo_critico",
        y="name",
        orientation="h",
        labels={
            "porcentaje_tiempo_critico": "Proporción de tiempo crítico",
            "name": "Estación",
        },
        title="Top 10 estaciones con mayor proporción de tiempo crítico",
    )
    fig_ranking.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_ranking, use_container_width=True)


# =====================================================
# MAPA
# =====================================================

st.subheader("Mapa de disponibilidad actual")

mapa = df_actual_filtrado.dropna(subset=["latitude", "longitude"])

if mapa.empty:
    st.warning("No hay coordenadas disponibles para mostrar el mapa.")
else:
    fig_mapa = px.scatter_mapbox(
        mapa,
        lat="latitude",
        lon="longitude",
        size="free_bikes_actuales",
        color="occupancy_pct_actual",
        hover_name="name",
        hover_data={
            "free_bikes_actuales": True,
            "empty_slots_actuales": True,
            "occupancy_pct_actual": True,
            "estado_critico_actual": True,
            "latitude": False,
            "longitude": False,
        },
        zoom=11,
        height=600,
        title="Estado actual de estaciones",
    )
    fig_mapa.update_layout(mapbox_style="open-street-map")
    st.plotly_chart(fig_mapa, use_container_width=True)


# =====================================================
# TABLAS DE APOYO
# =====================================================

with st.expander("Ver datos actuales"):
    st.dataframe(df_actual_filtrado, use_container_width=True)

with st.expander("Ver datos horarios agregados"):
    st.dataframe(df_hora_filtrado, use_container_width=True)