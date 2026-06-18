import pandas as pd
import plotly.express as px
import streamlit as st

from db import load_table, run_query, table_exists

SEVERITY_ORDER = ["leve", "moderado", "fuerte", "mayor", "sin_magnitud"]
SEVERITY_COLORS = {
    "leve": "#a8d8ea",
    "moderado": "#f9ca24",
    "fuerte": "#f0932b",
    "mayor": "#eb4d4b",
    "sin_magnitud": "#bdc3c7",
}
INTENSITY_COLORS = {
    "CDI (reportada)": "#2980b9",
    "MMI (estimada)": "#e67e22",
}

MAP_HEIGHT = 460
CHART_HEIGHT = 380
PLOT_MARGIN = {"r": 10, "t": 10, "l": 10, "b": 10}

st.set_page_config(page_title="Gold - USGS Earthquakes", layout="wide")
st.title("Gold - Actividad sismica")
st.caption(
    "Que regiones concentran mayor frecuencia y severidad sismica reciente, "
    "y que relacion hay entre magnitud, profundidad e intensidad percibida."
)

if not table_exists("gold", "earthquake_risk_summary"):
    st.info("Todavia no existe la capa Gold. Ejecuta los DAGs Bronze, Silver y Gold.")
    st.stop()

summary = load_table("gold", "earthquake_risk_summary")
events = load_table("gold", "fact_earthquake_events")

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
st.subheader("Donde se concentra la actividad sismica?")

col_map, col_rank = st.columns([3, 2], gap="large")

with col_map:
    st.markdown("**Mapa de eventos** (tamano = magnitud)")
    if not events.empty and {"latitude", "longitude", "mag"}.issubset(events.columns):
        map_df = events.dropna(subset=["latitude", "longitude", "mag"]).copy()
        map_df[["mag", "latitude", "longitude"]] = (
            map_df[["mag", "latitude", "longitude"]].apply(pd.to_numeric, errors="coerce")
        )
        map_df = map_df.dropna(subset=["latitude", "longitude", "mag"])
        map_df = map_df.loc[map_df["mag"] > 0]
        if not map_df.empty:
            fig = px.scatter_geo(
                map_df,
                lat="latitude",
                lon="longitude",
                color="severity_class",
                size=map_df["mag"].astype("float64").tolist(),
                size_max=16,
                hover_data=["place", "mag", "depth_km", "alert"],
                projection="natural earth",
                category_orders={"severity_class": SEVERITY_ORDER},
                color_discrete_map=SEVERITY_COLORS,
                labels={"severity_class": "Severidad"},
            )
            fig.update_geos(
                fitbounds="locations",
                showland=True,
                landcolor="#f2f2f2",
                showcountries=True,
                countrycolor="#d9d9d9",
                showocean=True,
                oceancolor="#eaf2f8",
            )
            fig.update_layout(
                height=MAP_HEIGHT,
                margin={"r": 0, "t": 0, "l": 0, "b": 0},
                legend={"orientation": "h", "yanchor": "bottom", "y": -0.08, "x": 0},
            )
            st.plotly_chart(fig, use_container_width=True)

with col_rank:
    st.markdown("**Regiones con mas eventos** (color = magnitud max.)")
    top = summary.sort_values("events_count", ascending=False).head(15)
    if not top.empty:
        fig = px.bar(
            top,
            x="events_count",
            y="region",
            orientation="h",
            color="max_mag",
            color_continuous_scale="Reds",
            labels={"events_count": "Eventos", "region": "", "max_mag": "Mag. max."},
        )
        fig.update_layout(
            height=MAP_HEIGHT,
            margin=PLOT_MARGIN,
            yaxis={"categoryorder": "total ascending"},
            coloraxis_colorbar={"title": "Mag.", "thickness": 12},
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Relacion entre magnitud, profundidad e intensidad percibida")

col_depth, col_intensity = st.columns(2, gap="large")

with col_depth:
    st.markdown("**Magnitud vs profundidad**")
    if not events.empty:
        depth_df = events.dropna(subset=["depth_km", "mag"])
        fig = px.scatter(
            depth_df,
            x="depth_km",
            y="mag",
            color="severity_class",
            hover_data=["place", "event_time", "sig"],
            labels={"depth_km": "Profundidad (km)", "mag": "Magnitud", "severity_class": "Severidad"},
            category_orders={"severity_class": SEVERITY_ORDER},
            color_discrete_map=SEVERITY_COLORS,
            opacity=0.75,
        )
        fig.update_layout(
            height=CHART_HEIGHT,
            margin=PLOT_MARGIN,
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": ""},
        )
        st.plotly_chart(fig, use_container_width=True)

with col_intensity:
    st.markdown("**Magnitud vs intensidad** (CDI reportada y MMI estimada)")
    if not events.empty:
        intensity_long = (
            events.dropna(subset=["mag"])
            .melt(
                id_vars=["place", "mag", "depth_km", "sig", "severity_class"],
                value_vars=["cdi", "mmi"],
                var_name="tipo",
                value_name="intensidad",
            )
            .dropna(subset=["intensidad"])
        )
        intensity_long = intensity_long[intensity_long["intensidad"] > 0]
        if not intensity_long.empty:
            intensity_long["tipo"] = intensity_long["tipo"].map(
                {"cdi": "CDI (reportada)", "mmi": "MMI (estimada)"}
            )
            fig = px.scatter(
                intensity_long,
                x="mag",
                y="intensidad",
                color="tipo",
                hover_data=["place", "depth_km", "sig"],
                labels={
                    "mag": "Magnitud",
                    "intensidad": "Intensidad (escala MM)",
                    "tipo": "Metrica",
                },
                color_discrete_map=INTENSITY_COLORS,
                opacity=0.75,
            )
            fig.update_layout(
                height=CHART_HEIGHT,
                margin=PLOT_MARGIN,
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": ""},
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin datos de CDI/MMI en este periodo.")

st.divider()
st.subheader("Que eventos priorizar?")
st.caption("Eventos fuertes/mayores, con tsunami, con alerta o significancia >= 500.")
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
    st.dataframe(priority[cols_show], use_container_width=True, hide_index=True, height=320)

st.divider()

if table_exists("gold", "fact_region_daily"):
    daily_cols = set(run_query("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'fact_region_daily'
    """)["column_name"])
    if "region" in daily_cols:
        daily = run_query("""
            SELECT
                region,
                event_date,
                events_count,
                max_mag,
                avg_depth_km,
                severe_events
            FROM gold.fact_region_daily
            ORDER BY event_date DESC, events_count DESC
        """)
    else:
        daily = run_query("""
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
        """)
    if not daily.empty:
        st.subheader("Eventos diarios por region")
        st.dataframe(daily, use_container_width=True, hide_index=True, height=320)
