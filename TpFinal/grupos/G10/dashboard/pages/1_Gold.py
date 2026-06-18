import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import run_query

st.set_page_config(page_title="Gold Analytics", layout="centered")

st.title("🏆 Gold Layer Analytics - Weather Summary")

# ----------------------------
# CARGA DE DATOS
# ----------------------------
@st.cache_data
def load_data():
    query = "SELECT * FROM gold.weather_summary"
    return run_query(query)

df = load_data()

st.subheader("📊 Datos Gold")
st.dataframe(df)

# ----------------------------
# KPI BÁSICOS (ARREGLADOS)
# ----------------------------
st.subheader("📌 KPIs generales")

col1, col2, col3 = st.columns(3)

# promedio real de temperaturas máximas
col1.metric(
    "Temp máxima promedio",
    f"{df['avg_temp_max'].mean():.2f} °C"
)

# lluvia total correcta
col2.metric(
    "Precipitación total",
    f"{df['total_precipitation'].sum():.2f} mm"
)

# ciudades
col3.metric(
    "Ciudades analizadas",
    df['city'].nunique()
)

# ----------------------------
# KPI EXTRA (valor agregado)
# ----------------------------
st.subheader("📌 Insights adicionales")

col4, col5 = st.columns(2)

col4.metric(
    "Día más lluvioso (ciudad)",
    df.loc[df['rainy_days'].idxmax(), 'city']
)

col5.metric(
    "Mayor temp máxima registrada",
    f"{df['max_temp_max'].max():.2f} °C"
)

st.subheader("📊 Visualizaciones")

col1, col2 = st.columns(2)

with col1:
    fig, ax = plt.subplots(figsize=(6, 3))
    df.plot(x="city", y="avg_temp_max", kind="bar", ax=ax)
    ax.set_title("Temp máxima promedio")
    st.pyplot(fig)

with col2:
    fig2, ax2 = plt.subplots(figsize=(6, 3))
    df.plot(x="city", y="total_precipitation", kind="bar", ax=ax2, color="skyblue")
    ax2.set_title("Precipitación total")
    st.pyplot(fig2)

st.divider()

col3, col4 = st.columns(2)

with col3:
    fig3, ax3 = plt.subplots(figsize=(6, 3))
    df.plot(x="city", y="rainy_days", kind="bar", ax=ax3, color="green")
    ax3.set_title("Días de lluvia")
    st.pyplot(fig3)

with col4:
    st.metric("Ciudad más lluviosa", df.loc[df['rainy_days'].idxmax(), 'city'])