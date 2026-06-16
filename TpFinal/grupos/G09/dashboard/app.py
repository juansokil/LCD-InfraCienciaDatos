import plotly.express as px
import streamlit as st

from db import load_table

SEVERITY_ORDER = ["leve", "moderado", "fuerte", "mayor", "sin_magnitud"]
SEVERITY_COLORS = {
    "leve": "#a8d8ea",
    "moderado": "#f9ca24",
    "fuerte": "#f0932b",
    "mayor": "#eb4d4b",
    "sin_magnitud": "#bdc3c7",
}

st.set_page_config(page_title="G09 - USGS Earthquakes", layout="wide")
st.title("Gold - Actividad sismica")
st.caption("Pipeline Bronze -> Silver -> Gold sobre datos sismicos de la USGS")

summary = load_table("gold", "earthquake_risk_summary")

if summary.empty:
    st.info("Todavia no hay datos Gold. Ejecuta los DAGs Bronze, Silver y Gold desde Airflow.")
    st.stop()

events = load_table("gold", "fact_earthquake_events")
events_with_intensity = (
    int((events["cdi"].notna() | events["mmi"].notna()).sum())
    if not events.empty and {"cdi", "mmi"}.issubset(events.columns)
    else 0
)

total_events = int(summary["events_count"].sum())
max_mag = float(summary["max_mag"].max())
severe_events = int(summary["severe_events"].sum())
tsunami_events = int(summary["tsunami_events"].sum())
avg_latency = float(summary["avg_ingestion_latency_minutes"].mean())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Eventos totales", total_events)
k2.metric("Magnitud max.", f"{max_mag:.1f}")
k3.metric("Fuertes / mayores", severe_events)
k4.metric("Flags tsunami", tsunami_events)
k5.metric("Latencia prom. ingesta", f"{avg_latency:.0f} min")
st.caption(f"CDI/MMI disponibles en {events_with_intensity} eventos; USGS no informa intensidad percibida para todos los registros.")

st.divider()

col_map, col_rank = st.columns([2, 1])

with col_map:
    st.subheader("Mapa de eventos")
    if not events.empty and {"latitude", "longitude", "mag"}.issubset(events.columns):
        map_df = events.dropna(subset=["latitude", "longitude", "mag"])
        if map_df.empty:
            st.info("Sin eventos con coordenadas para mapear.")
        else:
            fig = px.scatter_geo(
                map_df,
                lat="latitude",
                lon="longitude",
                color="severity_class",
                size="mag",
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

col_depth, col_intensity = st.columns(2)

with col_depth:
    st.subheader("Magnitud vs profundidad")
    if not events.empty:
        depth_df = events.dropna(subset=["depth_km", "mag"])
        if depth_df.empty:
            st.info("Sin datos suficientes de magnitud y profundidad.")
        else:
            fig = px.scatter(
                depth_df,
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
            st.info("Sin CDI/MMI en este periodo. USGS deja esos campos nulos cuando no hay reportes o estimaciones de intensidad.")

st.divider()

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
    if priority.empty:
        st.info("Sin eventos prioritarios en este periodo.")
    else:
        st.dataframe(priority[cols_show], use_container_width=True)

daily = load_table("gold", "fact_region_daily")
if not daily.empty:
    st.divider()
    st.subheader("Eventos diarios por region")
    st.dataframe(
        daily.sort_values(["event_date", "events_count"], ascending=[False, False]),
        use_container_width=True,
    )
