import pandas as pd
import streamlit as st

from db import load_weather_daily_summary


st.set_page_config(page_title="Gold Clima", layout="wide")

st.title("Gold Clima")
st.caption("Indicadores diarios desde gold.weather_daily_summary")

df = load_weather_daily_summary()

if df.empty:
    st.warning(
        "No hay datos disponibles en gold.weather_daily_summary. "
        "Ejecutar los DAGs Bronze, Silver y Gold antes de abrir el dashboard."
    )
    st.stop()

df["forecast_date"] = pd.to_datetime(df["forecast_date"]).dt.date

cities = sorted(df["city"].dropna().unique())
selected_cities = st.multiselect("Ciudades", cities, default=cities)

min_date = df["forecast_date"].min()
max_date = df["forecast_date"].max()
date_range = st.date_input(
    "Rango de fechas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

filtered = df[df["city"].isin(selected_cities)].copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        (filtered["forecast_date"] >= start_date)
        & (filtered["forecast_date"] <= end_date)
    ]

if filtered.empty:
    st.info("No hay filas para los filtros seleccionados.")
    st.stop()

kpi_cols = st.columns(5)
kpi_cols[0].metric("Temperatura promedio", f"{filtered['avg_temperature'].mean():.2f} C")
kpi_cols[1].metric("Temperatura maxima", f"{filtered['max_temperature'].max():.2f} C")
kpi_cols[2].metric("Temperatura minima", f"{filtered['min_temperature'].min():.2f} C")
kpi_cols[3].metric("Precipitacion total", f"{filtered['total_precipitation'].sum():.2f} mm")
kpi_cols[4].metric("Viento promedio", f"{filtered['avg_wind_speed'].mean():.2f} km/h")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Temperatura promedio por fecha")
    temp_chart = filtered.pivot_table(
        index="forecast_date",
        columns="city",
        values="avg_temperature",
        aggfunc="mean",
    ).sort_index()
    st.line_chart(temp_chart)

with right:
    st.subheader("Precipitacion total por fecha")
    rain_chart = filtered.pivot_table(
        index="forecast_date",
        columns="city",
        values="total_precipitation",
        aggfunc="sum",
    ).sort_index()
    st.bar_chart(rain_chart)

left, right = st.columns(2)

with left:
    st.subheader("Viento promedio por ciudad")
    wind_chart = (
        filtered.groupby("city", as_index=True)["avg_wind_speed"]
        .mean()
        .sort_values(ascending=False)
    )
    st.bar_chart(wind_chart)

with right:
    st.subheader("Score outdoor promedio")
    score_chart = (
        filtered.groupby("city", as_index=True)["outdoor_score"]
        .mean()
        .sort_values(ascending=False)
    )
    st.bar_chart(score_chart)

st.subheader("Resumen Gold")
st.dataframe(
    filtered[
        [
            "city",
            "forecast_date",
            "avg_temperature",
            "max_temperature",
            "min_temperature",
            "temperature_range",
            "total_precipitation",
            "rainy_hours",
            "avg_wind_speed",
            "max_wind_speed",
            "weather_category",
            "outdoor_score",
            "outdoor_recommendation",
        ]
    ].sort_values(["forecast_date", "city"]),
    use_container_width=True,
    hide_index=True,
)
