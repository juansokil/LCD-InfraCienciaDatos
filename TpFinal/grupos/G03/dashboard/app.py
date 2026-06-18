import streamlit as st

# Configuración de la página (Debe ser la primera línea de Streamlit)
st.set_page_config(
    page_title="Análisis del Pronóstico - Grupo 03",
    page_icon="☀️",
    layout="wide"
)

# Título
st.title("☀️ Sistema de Asesoramiento Turístico Inteligente")
st.markdown("---")

# Introducción de negocio
st.subheader("¿Cómo mejorar el asesoramiento de viajes en base al clima?")
st.write("""
Bienvenido al panel de analítica climática para nuestra **Empresa de Turismo**. 
Este sistema procesa datos meteorológicos históricos de los últimos 3 meses 
para identificar patrones climáticos clave en los principales destinos internacionales.
""")

st.info("👈 Seleccioná **Analisis Turismo** en la barra lateral para ver los reportes y gráficos de negocio.")

# Tarjetas informativas sobre los objetivos
col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    ### 🎯 Objetivos Estratégicos
    * **Optimizar recomendaciones:** Sugerir los mejores meses según las actividades a desarrollar.
    * **Cuidado del viajero:** Dar tips sobre ropa adecuada analizando la variabilidad térmica y así evitar malas experiencias.
    """)
with col2:
    st.markdown("""
    ### 📊 Datos Analizados
    * **Temporalidad:** Últimos 90 días (Ventana temporal).
    * **Capa Origen:** `gold.fact_clima_real` y `gold.dim_ciudad`.
    """)