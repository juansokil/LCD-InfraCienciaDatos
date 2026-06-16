import pandas as pd
import plotly.express as px
import streamlit as st

from db import coerce_numeric, load_table, run_query, table_exists

SUMMARY_NUM = [
    "events_count", "max_mag", "avg_mag", "avg_depth_km",
    "avg_ingestion_latency_minutes", "severe_events", "tsunami_events", "max_significance",
]
EVENTS_NUM = [
    "mag", "depth_km", "latitude", "longitude", "felt", "cdi", "mmi",
    "tsunami", "sig", "latency_update_minutes", "latency_ingestion_minutes",
]
DAILY_NUM = ["events_count", "max_mag", "avg_depth_km", "severe_events"]

SEVERITY_ORDER = ["leve", "moderado", "fuerte", "mayor", "sin_magnitud"]
SEVERITY_COLORS = {
    "leve": "#a8d8ea",
    "moderado": "#f9ca24",
    "fuerte": "#f0932b",
    "mayor": "#eb4d4b",
    "sin_magnitud": "#bdc3c7",
}

st.set_page_config(page_title="Gold - USGS Earthquakes", layout="wide")
st.title("Gold - Actividad sismica")

if not table_exists("gold", "earthquake_risk_summary"):
    st.info("Todavia no existe la capa Gold. Ejecuta los DAGs Bronze, Silver y Gold.")
    st.stop()

summary = coerce_numeric(load_table("gold", "earthquake_risk_summary"), SUMMARY_NUM)
events = coerce_numeric(load_table("gold", "fact_earthquake_events"), EVENTS_NUM)

# --- KPIs ---
total_events = int(summary["events_count"].sum()) if not summary.empty else 0
max_mag = float(summary["max_mag"].max()) if not summary.empty else 0.0
severe_events = int(summary["severe_events"].sum()) if not summary.empty else 0
tsunami_events = int(summary["tsunami_events"].sum()) if not summary.empty else 0
avg_latency = float(summary["avg_ingestion_latency_minutes"].mean()) if not summary.empty else 0.0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Eventos totales", total_events)
k2.metric("Magnitud max.", f"{max_mag:.1f}")
k3.metric("Fuertes / mayores", severe_events)
k4.metric("Flags tsunami", tsunami_events)
k5.metric("Latencia prom. ingesta", f"{avg_latency:.0f} min")

st.divider()

# --- Mapa + ranking ---
col_map, col_rank = st.columns([2, 1])

with col_map:
    st.subheader("Mapa de eventos")
    if not events.empty and {"latitude", "longitude", "mag"}.issubset(events.columns):
        map_df = events.dropna(subset=["latitude", "longitude", "mag"]).copy()
        for col in ("mag", "latitude", "longitude"):
            map_df[col] = pd.to_numeric(map_df[col], errors="coerce")
        map_df = map_df.dropna(subset=["latitude", "longitude", "mag"])
        map_df = map_df.loc[map_df["mag"] > 0]
        if not map_df.empty:
            fig = px.scatter_geo(
                map_df,
                lat="latitude",
                lon="longitude",
                color="severity_class",
                size=map_df["mag"].astype("float64").tolist(),
                size_max=14,
                hover_data=["place", "mag", "depth_km", "alert"],
                projection="natural earth",
                category_orders={"severity_class": SEVERITY_ORDER},
                color_discrete_map=SEVERITY_COLORS,
            )
            fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
            st.plotly_chart(fig, use_container_width=True)

with col_rank:
    st.subheader("Regiones con mas eventos")
    top = summary.sort_values("events_count", ascending=False).head(15)
    if not top.empty:
        fig = px.bar(
            top,
            x="events_count",
            y="region",
            orientation="h",
            color="max_mag",
            color_continuous_scale="Reds",
            labels={"events_count": "Eventos", "region": "Region", "max_mag": "Mag. max."},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin={"l": 0})
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Magnitud vs profundidad + magnitud vs intensidad percibida ---
col_depth, col_intensity = st.columns(2)

with col_depth:
    st.subheader("Magnitud vs profundidad")
    if not events.empty:
        fig = px.scatter(
            events.dropna(subset=["depth_km", "mag"]),
            x="depth_km",
            y="mag",
            color="severity_class",
            hover_data=["place", "event_time", "sig"],
            labels={"depth_km": "Profundidad (km)", "mag": "Magnitud", "severity_class": "Severidad"},
            category_orders={"severity_class": SEVERITY_ORDER},
            color_discrete_map=SEVERITY_COLORS,
        )
        st.plotly_chart(fig, use_container_width=True)

with col_intensity:
    st.subheader("Magnitud vs intensidad percibida (CDI / MMI)")
    if not events.empty:
        intensity_df = events.dropna(subset=["mag"])
        intensity_df = intensity_df[intensity_df["cdi"].notna() | intensity_df["mmi"].notna()]
        if not intensity_df.empty:
            fig = px.scatter(
                intensity_df,
                x="mag",
                y="cdi",
                color="mmi",
                hover_data=["place", "depth_km", "sig"],
                labels={
                    "mag": "Magnitud",
                    "cdi": "CDI (intensidad reportada)",
                    "mmi": "MMI (estimada)",
                },
                color_continuous_scale="YlOrRd",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin datos de CDI/MMI en este periodo.")

st.divider()

# --- Eventos prioritarios ---
st.subheader("Eventos prioritarios")
if not events.empty:
    priority = events[
        events["severity_class"].isin(["fuerte", "mayor"])
        | (events["tsunami"] == 1)
        | events["alert"].notna()
        | (events["sig"].fillna(0) >= 500)
    ].sort_values("sig", ascending=False, na_position="last")

    cols_show = [c for c in [
        "event_time", "place", "mag", "depth_km",
        "severity_class", "alert", "tsunami", "sig", "cdi", "mmi",
    ] if c in priority.columns]
    st.dataframe(priority[cols_show], use_container_width=True)

st.divider()

# --- Evolucion diaria por region ---
if table_exists("gold", "fact_region_daily"):
    daily = coerce_numeric(run_query("""
        SELECT
            d.region,
            f.event_date,
            f.events_count,
            f.max_mag,
            f.avg_depth_km,
            f.severe_events
        FROM gold.fact_region_daily f
        LEFT JOIN gold.dim_region d ON f.region_id = d.region_id
        ORDER BY f.event_date DESC, f.events_count DESC
    """), DAILY_NUM)
    if not daily.empty:
        st.subheader("Eventos diarios por region")
        st.dataframe(daily, use_container_width=True)
