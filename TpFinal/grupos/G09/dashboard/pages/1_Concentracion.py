import pandas as pd
import plotly.express as px
import streamlit as st

from constants import MAP_HEIGHT, PLOT_MARGIN, SEVERITY_COLORS, SEVERITY_ORDER
from data import require_gold

st.set_page_config(page_title="Concentracion - USGS Earthquakes", layout="wide")
st.title("Concentracion de actividad sismica")
st.caption("Donde se registran mas terremotos recientes y donde ocurren los de mayor magnitud.")

summary, events = require_gold()

total_events = int(summary["events_count"].sum()) if not summary.empty else 0
max_mag = float(summary["max_mag"].max()) if not summary.empty else 0.0
severe_events = int(summary["severe_events"].sum()) if not summary.empty else 0
tsunami_events = int(summary["tsunami_events"].sum()) if not summary.empty else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Eventos totales", total_events)
k2.metric("Magnitud max.", f"{max_mag:.1f}")
k3.metric("Fuertes / mayores", severe_events)
k4.metric("Flags tsunami", tsunami_events)

st.divider()

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
