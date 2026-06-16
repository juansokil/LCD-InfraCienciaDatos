import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

# 1. Configuración principal de la página
st.set_page_config(page_title="Dashboard Climático - G05", page_icon="🌤️", layout="wide")

st.title("🌤️ Pronóstico y Alertas Climáticas (Próximos 7 Días)")
st.markdown("Análisis comparativo de temperaturas extremas y precipitaciones para 4 puntos geográficos de Argentina.")

# 2. Función para conectarnos a nuestra base de datos Postgres y traer la tabla Gold
@st.cache_data
def cargar_datos():
    engine = create_engine('postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db')
    df = pd.read_sql("SELECT * FROM gold.clima_kpis", engine)
    return df

try:
    df = cargar_datos()
    
    # 3. Creamos un filtro para que el profesor pueda elegir qué ciudad mirar
    ciudades = df['ciudad'].unique()
    ciudad_seleccionada = st.selectbox("📌 Seleccionar Ciudad para analizar:", ciudades)
    
    # Filtramos la tabla solo para la ciudad elegida
    df_ciudad = df[df['ciudad'] == ciudad_seleccionada]
    
    st.divider()
    
    # 4. Creamos los KPIs (Tarjetitas con números grandes)
    st.subheader(f"Métricas Principales - {ciudad_seleccionada}")
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Temperatura Máxima Pico", f"{df_ciudad['temp_max'].max()} °C")
    col2.metric("Temperatura Mínima Pico", f"{df_ciudad['temp_min'].min()} °C")
    col3.metric("Lluvia Total Acumulada", f"{round(df_ciudad['lluvia_mm'].sum(), 1)} mm")
    col4.metric("Mayor Amplitud Térmica", f"{round(df_ciudad['amplitud_termica'].max(), 1)} °C")
    
    st.divider()
    
    # 5. Gráfico de Líneas: Temperaturas
    st.subheader("📈 Evolución de Temperaturas (Máxima y Mínima)")
    fig_temp = px.line(df_ciudad, x='fecha_pronostico', y=['temp_max', 'temp_min'], 
                       labels={'value': 'Temperatura (°C)', 'fecha_pronostico': 'Fecha', 'variable': 'Indicador'},
                       color_discrete_sequence=['#EF553B', '#636EFA'], # Rojo para max, azul para min
                       markers=True)
    st.plotly_chart(fig_temp, use_container_width=True)
    
    # 6. Gráfico de Barras: Lluvias
    col_graf, col_alerta = st.columns([2, 1])
    
    with col_graf:
        st.subheader("🌧️ Lluvia Esperada por Día")
        fig_lluvia = px.bar(df_ciudad, x='fecha_pronostico', y='lluvia_mm', 
                            labels={'lluvia_mm': 'Lluvia (mm)', 'fecha_pronostico': 'Fecha'},
                            color_discrete_sequence=['#00CC96'])
        st.plotly_chart(fig_lluvia, use_container_width=True)
        
    # 7. Tabla de Alertas Inteligentes
    with col_alerta:
        st.subheader("⚠️ Alertas Climáticas")
        alertas = df_ciudad[df_ciudad['alerta_climatica'] != 'Normal']
        
        if not alertas.empty:
            st.error("Se detectaron condiciones extremas:")
            # Mostramos solo las columnas relevantes
            st.dataframe(alertas[['fecha_pronostico', 'alerta_climatica']], hide_index=True)
        else:
            st.success("No hay alertas extremas de frío, calor o lluvia para esta ciudad en los próximos días.")

except Exception as e:
    st.error(f"Error al cargar los datos: {e}. Esperá un minuto a que Airflow termine de procesar los datos.")