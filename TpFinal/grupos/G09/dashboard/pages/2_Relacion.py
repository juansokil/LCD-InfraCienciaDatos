import pandas as pd
import plotly.express as px
import streamlit as st

from constants import (
    CHART_HEIGHT,
    DEPTH_BAND_COLORS,
    DEPTH_BAND_ORDER,
    INTENSITY_COLORS,
    PLOT_MARGIN,
    SEVERITY_COLORS,
    SEVERITY_ORDER,
)
from data import require_gold

st.set_page_config(page_title="Relacion - USGS Earthquakes", layout="wide")
st.title("Magnitud, profundidad e intensidad")
st.caption("Que relacion hay entre la magnitud, la profundidad y la intensidad percibida (CDI / MMI).")

_, events = require_gold()

if events.empty:
    st.info("Sin eventos en la capa Gold todavia.")
    st.stop()

events_with_cdi = int(events["cdi"].notna().sum()) if "cdi" in events.columns else 0
events_with_mmi = int(events["mmi"].notna().sum()) if "mmi" in events.columns else 0
avg_depth = float(events["depth_km"].mean()) if "depth_km" in events.columns else 0.0

k1, k2, k3 = st.columns(3)
k1.metric("Eventos con CDI", events_with_cdi)
k2.metric("Eventos con MMI", events_with_mmi)
k3.metric("Profundidad prom.", f"{avg_depth:.0f} km")

st.divider()

col_depth, col_intensity = st.columns(2, gap="large")

with col_depth:
    st.markdown("**Magnitud vs profundidad**")
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
            opacity=0.85,
        )
        fig.update_traces(marker={"size": 9, "line": {"width": 0.6, "color": "#ffffff"}})
        fig.update_layout(
            height=CHART_HEIGHT,
            margin=PLOT_MARGIN,
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": ""},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de CDI/MMI en este periodo.")

st.divider()
st.markdown("**Magnitud vs intensidad percibida segun profundidad**")
st.caption(
    "A igual magnitud, los eventos mas superficiales tienden a registrar mayor intensidad. "
    "Se usa MMI cuando existe y, si falta, CDI como intensidad observada."
)

triple = events.dropna(subset=["mag", "depth_km"]).copy()
triple["intensidad_obs"] = triple["mmi"]
triple["intensidad_obs"] = triple["intensidad_obs"].fillna(triple["cdi"])
triple = triple.dropna(subset=["intensidad_obs"])
triple = triple[triple["intensidad_obs"] > 0]

if not triple.empty:
    triple["banda_profundidad"] = pd.cut(
        triple["depth_km"],
        bins=[-float("inf"), 35, 70, float("inf")],
        labels=DEPTH_BAND_ORDER,
    )
    fig = px.scatter(
        triple,
        x="mag",
        y="intensidad_obs",
        color="banda_profundidad",
        hover_data=["place", "depth_km", "mmi", "cdi", "sig"],
        labels={
            "mag": "Magnitud",
            "intensidad_obs": "Intensidad observada (MMI o CDI)",
            "banda_profundidad": "Profundidad",
        },
        category_orders={"banda_profundidad": DEPTH_BAND_ORDER},
        color_discrete_map=DEPTH_BAND_COLORS,
        opacity=0.85,
    )
    fig.update_traces(marker={"size": 9, "line": {"width": 0.6, "color": "#ffffff"}})
    fig.update_layout(
        height=CHART_HEIGHT,
        margin=PLOT_MARGIN,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": ""},
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sin datos suficientes de intensidad y profundidad para este grafico.")
