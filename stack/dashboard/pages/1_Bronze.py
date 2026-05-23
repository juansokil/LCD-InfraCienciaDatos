"""
Bronze - Vista de datos crudos ingresados desde la API.
"""

import streamlit as st
from db import load_table, get_row_count, get_last_updated, get_table_list, show_last_updated_badge

st.header("Bronze Layer")
st.caption("Datos crudos tal como llegan desde la API de CoinGecko")

# --- Tablas disponibles ---
tables = get_table_list("bronze")

if not tables:
    st.warning("No hay tablas en bronze todavia. Ejecuta el DAG de ingesta desde Airflow.")
    st.stop()

# --- Resumen general ---
st.subheader("Estado de las tablas")

cols = st.columns(len(tables))
for i, table in enumerate(tables):
    with cols[i]:
        count = get_row_count("bronze", table)
        st.metric(table, f"{count:,} filas")
        show_last_updated_badge("bronze", table)

st.divider()

# --- Explorar tabla ---
st.subheader("Explorar datos")

selected = st.selectbox("Selecciona una tabla", tables)
df = load_table("bronze", selected)

if df.empty:
    st.info(f"La tabla `{selected}` esta vacia.")
    st.stop()

# Ultimos registros
st.caption(f"Mostrando ultimos 100 registros de **bronze.{selected}**")
show_last_updated_badge("bronze", selected)

if "ingested_at" in df.columns:
    df_sorted = df.sort_values("ingested_at", ascending=False).head(100)
else:
    df_sorted = df.tail(100)

st.dataframe(df_sorted, use_container_width=True, hide_index=True)

# Estadisticas basicas
with st.expander("Estadisticas de columnas"):
    st.dataframe(df.describe(include="all").T, use_container_width=True)
