"""
Vistas de negocio sobre las tablas GOLD.
KPIs · mapa en vivo · patrón por hora · ranking de estaciones críticas · comparación de ciudades.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query

st.set_page_config(page_title="Gold — CityBikes", page_icon="🥇", layout="wide")
st.title("🥇 Vistas de negocio (Gold)")

# ---- Filtro por red / ciudad ----
networks = run_query("SELECT network_id, name, city FROM gold.dim_network ORDER BY name")
if networks.empty:
    st.info("Aún no hay datos en Gold. Esperá unos minutos a que el pipeline complete su primera vuelta.")
    st.stop()

networks["label"] = networks["name"].fillna(networks["network_id"]) + " (" + networks["city"].fillna("?") + ")"
opciones = dict(zip(networks["label"], networks["network_id"]))
seleccion = st.multiselect(
    "Redes a mostrar",
    options=list(opciones.keys()),
    default=list(opciones.keys()),
)
ids = [opciones[s] for s in seleccion] or list(opciones.values())

# ============================================================
# 1. KPIs (foto actual)
# ============================================================
cur = run_query(
    """
    SELECT * FROM gold.station_current
    WHERE network_id = ANY(:ids)
    """,
    {"ids": ids},
)

st.subheader("Estado actual")
if cur.empty:
    st.info("Sin foto actual todavía.")
else:
    total_est = len(cur)
    total_bikes = int(cur["free_bikes"].fillna(0).sum())
    pct_vacias = round(100 * (cur["free_bikes"].fillna(0) == 0).mean(), 1)
    pct_llenas = round(100 * (cur["empty_slots"].fillna(0) == 0).mean(), 1)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Estaciones", total_est)
    k2.metric("Bicis disponibles", total_bikes)
    k3.metric("% estaciones vacías", f"{pct_vacias}%")
    k4.metric("% estaciones llenas", f"{pct_llenas}%")

    # ---- Mapa de disponibilidad (color = ocupación) ----
    mapa = cur.dropna(subset=["latitude", "longitude"]).copy()
    if not mapa.empty:
        mapa["occupancy_rate"] = mapa["occupancy_rate"].astype(float).fillna(0)
        fig_map = px.scatter_map(
            mapa,
            lat="latitude",
            lon="longitude",
            color="occupancy_rate",
            size=mapa["total_slots"].fillna(1).clip(lower=1),
            color_continuous_scale="RdYlGn",
            range_color=(0, 1),
            hover_name="station_name",
            hover_data={"free_bikes": True, "empty_slots": True, "latitude": False, "longitude": False},
            zoom=10,
            height=520,
            map_style="open-street-map",
        )
        fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_map, use_container_width=True)
        st.caption("Verde = muchas bicis disponibles · Rojo = estación vacía. Tamaño = capacidad de la estación.")

# ============================================================
# 2. Patrón de disponibilidad por hora del día
# ============================================================
st.subheader("Patrón por hora del día")
patron = run_query(
    """
    SELECT
        EXTRACT(HOUR FROM hour_bucket)::int AS hora,
        ROUND(AVG(avg_occupancy), 3)        AS ocupacion_promedio,
        ROUND(AVG(pct_time_empty), 3)       AS pct_vacias
    FROM gold.fact_station_hourly
    WHERE network_id = ANY(:ids)
    GROUP BY 1
    ORDER BY 1
    """,
    {"ids": ids},
)
if patron.empty:
    st.info("Todavía no hay suficientes horas acumuladas para ver el patrón. Volvé en un rato.")
else:
    fig_h = px.line(
        patron,
        x="hora",
        y=["ocupacion_promedio", "pct_vacias"],
        markers=True,
        labels={"value": "proporción", "hora": "hora del día", "variable": "métrica"},
    )
    st.plotly_chart(fig_h, use_container_width=True)
    st.caption("Ocupación promedio y proporción de estaciones vacías según la hora.")

# ============================================================
# 3. Ranking de estaciones críticas
# ============================================================
st.subheader("Estaciones más críticas")
col_a, col_b = st.columns(2)

vacias = run_query(
    """
    SELECT d.station_name AS estacion, d.city AS ciudad,
           ROUND(AVG(f.pct_time_empty), 3) AS pct_tiempo_vacia
    FROM gold.fact_station_hourly f
    JOIN gold.dim_station d USING (station_id)
    WHERE f.network_id = ANY(:ids)
    GROUP BY d.station_name, d.city
    ORDER BY pct_tiempo_vacia DESC
    LIMIT 10
    """,
    {"ids": ids},
)
with col_a:
    st.markdown("**Top 10 más tiempo SIN bicis**")
    st.dataframe(vacias, use_container_width=True, hide_index=True)

llenas = run_query(
    """
    SELECT d.station_name AS estacion, d.city AS ciudad,
           ROUND(AVG(f.pct_time_full), 3) AS pct_tiempo_llena
    FROM gold.fact_station_hourly f
    JOIN gold.dim_station d USING (station_id)
    WHERE f.network_id = ANY(:ids)
    GROUP BY d.station_name, d.city
    ORDER BY pct_tiempo_llena DESC
    LIMIT 10
    """,
    {"ids": ids},
)
with col_b:
    st.markdown("**Top 10 más tiempo SATURADAS (sin lugar)**")
    st.dataframe(llenas, use_container_width=True, hide_index=True)

# ============================================================
# 4. Comparación entre ciudades
# ============================================================
st.subheader("Comparación entre ciudades")
comp = run_query(
    """
    SELECT n.city AS ciudad,
           ROUND(AVG(f.avg_occupancy), 3) AS ocupacion_promedio
    FROM gold.fact_station_hourly f
    JOIN gold.dim_network n USING (network_id)
    WHERE f.network_id = ANY(:ids)
    GROUP BY n.city
    ORDER BY ocupacion_promedio DESC
    """,
    {"ids": ids},
)
if not comp.empty:
    fig_c = px.bar(comp, x="ciudad", y="ocupacion_promedio", text="ocupacion_promedio")
    fig_c.update_traces(textposition="outside")
    st.plotly_chart(fig_c, use_container_width=True)
