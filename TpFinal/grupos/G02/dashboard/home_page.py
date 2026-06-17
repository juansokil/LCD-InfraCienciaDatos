import streamlit as st


st.title("Bienvenidos al Proyecto ARS Exchange Monitor - Grupo 02")
st.write("---")

st.markdown(
    """
### Sobre este desarrollo
Este sistema es un pipeline de datos *end-to-end* que automatiza la extracción, transformación y carga (ETL)
de datos de divisas globales utilizando la arquitectura **Medallion** (Bronze -> Silver -> Gold).

* **Fuente:** Open Exchange Rates API.
* **Orquestación:** Apache Airflow.
* **Almacenamiento:** PostgreSQL Warehouse.

### ¿Cómo ver las métricas?
Para explorar el monitor de cotizaciones y las alertas de variación respecto al **Peso Argentino (ARS)**,
seleccioná la pestaña **"Dashboard"** en la barra lateral izquierda.
"""
)
