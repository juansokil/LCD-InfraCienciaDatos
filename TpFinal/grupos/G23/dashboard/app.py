import streamlit as st

st.set_page_config(
    page_title="EcoBici Buenos Aires",
    layout="wide"
)

st.title("EcoBici Buenos Aires")
st.subheader("Pipeline de Datos y Sistema Analítico")

st.markdown("---")

st.markdown("""
## Descripción del Proyecto

Este proyecto implementa una arquitectura de datos basada en el paradigma **Medallion Architecture**
(Bronze, Silver y Gold) para el procesamiento y análisis de información proveniente de la red
de bicicletas públicas EcoBici de la Ciudad Autónoma de Buenos Aires.

El objetivo principal es automatizar la captura, transformación y modelado de los datos para
generar indicadores analíticos que permitan comprender el comportamiento operativo de las estaciones.

""")

st.markdown("""
## Arquitectura Implementada

### Capa Bronze
- Extracción automática desde la API de EcoBici.
- Almacenamiento de datos crudos sin transformaciones.
- Conservación de la información original para auditoría y trazabilidad.

### Capa Silver
- Limpieza y validación de registros.
- Estandarización de tipos de datos.
- Eliminación de inconsistencias.
- Preparación de datos para análisis.

### Capa Gold
- Construcción de un modelo dimensional tipo Star Schema.
- Generación de tablas de dimensiones y hechos.
- Optimización para consultas analíticas y visualización.

""")

st.markdown("""
## Tecnologías Utilizadas

- Apache Airflow
- PostgreSQL
- Docker
- Python
- Streamlit
- Plotly

""")

st.markdown("""
## Flujo de Procesamiento

1. Obtención de datos desde la API de EcoBici.
2. Carga de datos en Bronze.
3. Transformación y validación en Silver.
4. Construcción del modelo analítico en Gold.
5. Visualización mediante dashboard interactivo.

""")

st.markdown("---")

st.info(
    "Utilice el menú lateral para acceder al Dashboard Analítico construido sobre la capa Gold."
)